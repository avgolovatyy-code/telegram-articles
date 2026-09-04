"""Editorial workflow.

    draft → preview → approve / reject / regenerate → schedule → publish

Auto-publish is opt-in per market (``AUTO_PUBLISH_EN`` / ``AUTO_PUBLISH_RU``) and even
then every automatic gate still has to pass.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.router import LLMGateway
from app.config import Settings, get_settings
from app.db.enums import ArticleStatus, PublicationTarget
from app.db.models import Article, TelegramPublication
from app.db.types import utcnow
from app.errors import ConfigurationError, EngineError, ValidationFailed
from app.generation.pipeline import GenerationOutcome, GenerationPipeline
from app.logging_setup import get_logger
from app.max.publisher import maybe_publish_ru_to_max
from app.services.rendering import render_stored_article
from app.telegram.api import build_telegram_client
from app.telegram.publisher import TelegramPublisher

log = get_logger("services.workflow")

APPROVABLE_STATUSES = {
    ArticleStatus.DRAFT,
    ArticleStatus.NEEDS_REVIEW,
    ArticleStatus.VALIDATION_FAILED,
}


@dataclass(slots=True)
class WorkflowResult:
    ok: bool
    message: str
    article: Article | None = None


class ArticleWorkflow:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # -------------------------------------------------------------- review
    def approve(self, article: Article, *, by: str = "admin") -> WorkflowResult:
        if article.status not in APPROVABLE_STATUSES:
            return WorkflowResult(False, f"cannot approve an article in status {article.status}")
        if article.status == ArticleStatus.VALIDATION_FAILED and article.validation_issues:
            return WorkflowResult(
                False,
                "article failed automatic validation; regenerate or edit it first",
            )
        article.status = ArticleStatus.APPROVED
        article.approved_at = utcnow()
        article.approved_by = by
        article.status_reason = None
        self.session.flush()
        return WorkflowResult(True, "approved", article)

    def reject(self, article: Article, *, reason: str, by: str = "admin") -> WorkflowResult:
        article.status = ArticleStatus.REJECTED
        article.status_reason = reason
        article.approved_by = by
        self.session.flush()
        return WorkflowResult(True, "rejected", article)

    def archive(self, article: Article) -> WorkflowResult:
        article.status = ArticleStatus.ARCHIVED
        self.session.flush()
        return WorkflowResult(True, "archived", article)

    def regenerate(self, article: Article) -> GenerationOutcome:
        """Rewrite the article in place under current prompts; edit live Telegram posts."""
        if article.topic is None:
            raise ValidationFailed("article has no topic to regenerate from")
        gateway = LLMGateway(self.session, settings=self.settings)
        pipeline = GenerationPipeline(self.session, gateway, settings=self.settings)
        had_publications = bool(article.publications)
        outcome = pipeline.rewrite(article)
        if (
            outcome.ok
            and had_publications
            and article.rendered_message
            and article.status == ArticleStatus.PUBLISHED
        ):
            edit = self._edit_all_publications(
                article, reason="rewritten under current editorial rules"
            )
            if not edit.ok:
                log.warning(
                    "workflow.rewrite_telegram_edit_failed",
                    article_id=article.id,
                    reason=edit.message,
                )
        return outcome

    def _edit_all_publications(self, article: Article, *, reason: str) -> WorkflowResult:
        if not article.rendered_message:
            return WorkflowResult(False, "article has no rendered message to push")
        client = build_telegram_client(self.settings)
        publisher = TelegramPublisher(self.session, client, settings=self.settings)
        errors: list[str] = []
        try:
            for publication in list(article.publications):
                if not publication.message_id:
                    continue
                try:
                    publisher.edit(publication, article.rendered_message, reason=reason)
                except EngineError as exc:
                    errors.append(f"{publication.target}:{publication.message_id}: {exc}")
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        if errors:
            return WorkflowResult(False, "; ".join(errors), article)
        return WorkflowResult(True, "telegram messages updated", article)

    # ------------------------------------------------------------ scheduling
    def schedule(self, article: Article, when: dt.datetime) -> WorkflowResult:
        if article.status not in {ArticleStatus.APPROVED, ArticleStatus.SCHEDULED}:
            return WorkflowResult(False, "approve the article before scheduling it")
        article.scheduled_for = when
        article.status = ArticleStatus.SCHEDULED
        client = build_telegram_client(self.settings)
        try:
            TelegramPublisher(self.session, client, settings=self.settings).enqueue(
                article, target=PublicationTarget.PRODUCTION, scheduled_for=when
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        self.session.flush()
        return WorkflowResult(True, f"scheduled for {when.isoformat()}", article)

    # ------------------------------------------------------------ publishing
    def publish_test(self, article: Article) -> WorkflowResult:
        if not self.settings.telegram_test_channel:
            raise ConfigurationError(
                "TELEGRAM_TEST_CHANNEL is not configured; rendering must be verified on the "
                "test channel before production"
            )
        return self._publish(article, PublicationTarget.TEST)

    def publish_now(self, article: Article, *, require_test: bool = True) -> WorkflowResult:
        if require_test and not self._has_test_publication(article):
            return WorkflowResult(
                False,
                "publish to the test channel first — production is not a preview mechanism",
            )
        if article.status not in {
            ArticleStatus.APPROVED,
            ArticleStatus.SCHEDULED,
            ArticleStatus.NEEDS_REVIEW,
        }:
            return WorkflowResult(False, f"cannot publish an article in status {article.status}")
        if article.status == ArticleStatus.NEEDS_REVIEW and not self.settings.auto_publish(
            article.market  # type: ignore[arg-type]
        ):
            return WorkflowResult(False, "article is awaiting human review")
        return self._publish(article, PublicationTarget.PRODUCTION)

    def _publish(self, article: Article, target: PublicationTarget) -> WorkflowResult:
        rendered = render_stored_article(self.session, article, settings=self.settings)
        article.rendered_message = rendered.message
        client = build_telegram_client(self.settings)
        publisher = TelegramPublisher(self.session, client, settings=self.settings)
        try:
            if target == PublicationTarget.PRODUCTION:
                article.status = ArticleStatus.PUBLISHING
                self.session.flush()
            result = publisher.publish(article, rendered.message, target=target)
        except EngineError as exc:
            if target == PublicationTarget.PRODUCTION:
                article.status = ArticleStatus.FAILED
                article.status_reason = str(exc)
                self.session.flush()
            return WorkflowResult(False, str(exc), article)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        url = result.publication.message_url or "(no public URL)"
        if not result.created:
            return WorkflowResult(True, f"already published: {url}", article)
        if (
            target == PublicationTarget.PRODUCTION
            and article.market == "ru"
            and result.created
        ):
            max_result = maybe_publish_ru_to_max(article, settings=self.settings)
            if max_result.error:
                return WorkflowResult(
                    True,
                    f"published to {target}: {url} (Max fan-out failed: {max_result.error})",
                    article,
                )
            if max_result.sent is not None:
                return WorkflowResult(
                    True,
                    f"published to {target}: {url}; Max chat_id={max_result.sent.chat_id}",
                    article,
                )
        return WorkflowResult(True, f"published to {target}: {url}", article)

    def _has_test_publication(self, article: Article) -> bool:
        return any(
            publication.target == PublicationTarget.TEST for publication in article.publications
        )

    # ---------------------------------------------------------------- edits
    def republish_correction(self, article: Article, *, reason: str) -> WorkflowResult:
        publication: TelegramPublication | None = next(
            (
                p
                for p in sorted(article.publications, key=lambda p: p.published_at, reverse=True)
                if p.target == PublicationTarget.PRODUCTION
            ),
            None,
        )
        if publication is None:
            return WorkflowResult(False, "article has no production publication to edit")
        rendered = render_stored_article(self.session, article, settings=self.settings)
        article.rendered_message = rendered.message
        client = build_telegram_client(self.settings)
        try:
            TelegramPublisher(self.session, client, settings=self.settings).edit(
                publication, rendered.message, reason=reason
            )
        except EngineError as exc:
            return WorkflowResult(False, str(exc), article)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        return WorkflowResult(True, "message updated", article)


__all__ = ["APPROVABLE_STATUSES", "ArticleWorkflow", "WorkflowResult"]
