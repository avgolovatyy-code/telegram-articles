"""Max adapt_for_max + publication persistence / quotas."""

from __future__ import annotations

from sqlalchemy import select

from app.db.enums import ArticleStatus
from app.db.models import Article, MaxPublication
from app.max.adapter import adapt_for_max
from app.max.publisher import MaxPublisher, max_idempotency_key
from app.max.quota import max_quota_decision


def _make_article(session, *, market: str = "ru", **overrides) -> Article:
    article = Article(
        public_id=overrides.pop("public_id", f"max-persist-{session.query(Article).count()}"),
        market=market,
        topic_slug="kazan",
        entity_type="city",
        entity_external_id="kazan",
        entity_name="Казань",
        intent="weekend",
        primary_query="куда сходить в Казани",
        status=overrides.pop("status", ArticleStatus.PUBLISHED),
        current_version=1,
        title=overrides.pop("title", "Казань на выходные"),
        body=overrides.pop(
            "body",
            {
                "title": "Казань на выходные",
                "intro": "Короткий план.",
                "sections": [
                    {
                        "heading": "Кремль",
                        "level": 2,
                        "blocks": [
                            {"type": "paragraph", "text": "Прогулка по кремлю. " * 200}
                        ],
                    }
                ],
                "product_placements": [],
                "media_placements": [],
                "audio_placements": [],
                "faq": [],
                "hashtags": [],
                "claims": [],
                "closing": "Хороших выходных.",
            },
        ),
        **overrides,
    )
    session.add(article)
    session.flush()
    return article


def test_adapt_for_max_shortens_long_body(session):
    article = _make_article(session)
    adapted = adapt_for_max(article)
    assert adapted.adapted is True
    assert adapted.char_estimate < 4000
    assert adapted.document.intro
    assert isinstance(adapted.document.claims, list)


def test_max_publisher_persists_success(session, settings, monkeypatch):
    class FakeClient:
        def send_message(self, **kwargs):
            from app.max.client import SentMaxMessage

            return SentMaxMessage(
                message_id="mid.abc",
                chat_id=-1,
                raw={"message": {"body": {"mid": "mid.abc"}, "stat": {"url": "https://max.ru/x"}}},
            )

        def close(self):
            return None

    monkeypatch.setattr(settings, "max_bot_token", "token")
    monkeypatch.setattr(settings, "max_ru_channel_id", "-1")
    article = _make_article(
        session,
        title="Казань на выходные",
        body={
            "title": "Казань на выходные",
            "intro": "Короткий план.",
            "sections": [],
            "product_placements": [],
            "media_placements": [],
            "audio_placements": [],
            "faq": [],
            "hashtags": [],
            "claims": [],
            "closing": "",
        },
    )

    publisher = MaxPublisher(settings=settings, client=FakeClient(), session=session)  # type: ignore[arg-type]
    result = publisher.publish_ru(article)
    assert result.ok
    assert result.sent is not None
    assert result.publication is not None
    assert result.publication.message_id == "mid.abc"
    assert result.publication.skipped is False
    key = max_idempotency_key(article.id, article.current_version)
    again = MaxPublisher(settings=settings, client=FakeClient(), session=session).publish_ru(  # type: ignore[arg-type]
        article
    )
    assert again.skip_reason == "already_published"
    rows = list(
        session.scalars(select(MaxPublication).where(MaxPublication.idempotency_key == key))
    )
    assert len(rows) == 1


def test_max_quota_blocks_when_day_full(session, settings):
    article = _make_article(session)
    session.add(
        MaxPublication(
            article_id=article.id,
            idempotency_key="k1",
            market="ru",
            target="production",
            channel_ref="channel_wegotrip",
            skipped=False,
            audience_country="RU",
        )
    )
    session.flush()
    settings.maxapp_max_posts_per_day = 1
    settings.maxapp_posts_per_week_max = 10
    allowed, reason = max_quota_decision(session, settings)
    assert allowed is False
    assert reason == "max_daily_quota"
