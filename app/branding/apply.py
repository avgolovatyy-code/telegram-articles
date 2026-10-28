"""Apply approved Telegram channel branding via Bot API.

Does **not** touch Max. Requires human approval and
``Settings.channel_branding_apply_enabled`` (or an explicit CLI ``--yes``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.branding.proposal import (
    CHANNEL_BRANDING_VERSION,
    ChannelBrandingDraft,
    proposed_branding_for,
    validate_branding_lengths,
)
from app.config import Market, Settings, get_settings
from app.logging_setup import get_logger
from app.telegram.api import TelegramBotClient, build_telegram_client

log = get_logger("branding.apply")


@dataclass(slots=True)
class ChannelApplyResult:
    market: Market
    username: str
    before: dict[str, Any]
    after: dict[str, Any]
    steps: dict[str, Any] = field(default_factory=dict)
    pinned_message_id: int | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class BrandingApplyReport:
    branding_version: str
    results: list[ChannelApplyResult]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.results)


def _snapshot(chat: dict[str, Any]) -> dict[str, Any]:
    pinned: dict[str, Any] = {}
    raw_pinned = chat.get("pinned_message")
    if isinstance(raw_pinned, dict):
        pinned = dict(raw_pinned)
    return {
        "id": chat.get("id"),
        "username": chat.get("username"),
        "title": chat.get("title"),
        "description": chat.get("description"),
        "pinned_message_id": pinned.get("message_id"),
        "pinned_text_preview": str(pinned.get("text") or "")[:160],
    }


def _check_bot_can_change(client: TelegramBotClient, chat_id: str) -> list[str]:
    errors: list[str] = []
    me = client.get_me()
    member = client.call("getChatMember", {"chat_id": chat_id, "user_id": me["id"]})
    status = member.get("status")
    if status not in {"administrator", "creator"}:
        errors.append(f"bot is not admin in {chat_id} (status={status})")
        return errors
    if status == "administrator" and member.get("can_change_info") is False:
        errors.append(f"bot lacks can_change_info in {chat_id}")
    if status == "administrator" and member.get("can_post_messages") is False:
        errors.append(f"bot lacks can_post_messages in {chat_id}")
    return errors


def apply_channel_branding(
    market: Market,
    *,
    settings: Settings | None = None,
    client: TelegramBotClient | None = None,
    draft: ChannelBrandingDraft | None = None,
    pin_welcome: bool = True,
) -> ChannelApplyResult:
    """Apply approved title/description/pin for one market."""
    settings = settings or get_settings()
    draft = draft or proposed_branding_for(market)
    length_errors = validate_branding_lengths(draft)
    if length_errors:
        return ChannelApplyResult(
            market=market,
            username=draft.username,
            before={},
            after={},
            errors=length_errors,
        )

    owns = client is None
    client = client or TelegramBotClient(settings)
    chat_id = draft.username
    try:
        before_chat = client.get_chat(chat_id)
        before = _snapshot(before_chat)
        result = ChannelApplyResult(
            market=market,
            username=draft.username,
            before=before,
            after={},
        )
        perm_errors = _check_bot_can_change(client, chat_id)
        if perm_errors:
            result.errors.extend(perm_errors)
            result.after = before
            return result

        existing_pin = before.get("pinned_message_id")
        if existing_pin:
            result.steps["existing_pin"] = {
                "message_id": existing_pin,
                "preview": before.get("pinned_text_preview"),
                "note": "will pin new welcome; Telegram keeps multipin when supported",
            }

        if draft.title_action == "rename" and before.get("title") != draft.title:
            client.call("setChatTitle", {"chat_id": chat_id, "title": draft.title})
            result.steps["setChatTitle"] = {"ok": True, "title": draft.title}
        else:
            result.steps["setChatTitle"] = {"ok": True, "skipped": True, "title": draft.title}

        if (before.get("description") or "") != draft.description:
            client.call(
                "setChatDescription",
                {"chat_id": chat_id, "description": draft.description},
            )
            result.steps["setChatDescription"] = {"ok": True}
        else:
            result.steps["setChatDescription"] = {"ok": True, "skipped": True}

        if pin_welcome:
            sent = client.send_message(chat_id, draft.pinned_welcome_text)
            result.pinned_message_id = sent.message_id
            result.steps["sendMessage"] = {"ok": True, "message_id": sent.message_id}
            client.call(
                "pinChatMessage",
                {
                    "chat_id": chat_id,
                    "message_id": sent.message_id,
                    "disable_notification": True,
                },
            )
            result.steps["pinChatMessage"] = {"ok": True, "message_id": sent.message_id}

        after_chat = client.get_chat(chat_id)
        result.after = _snapshot(after_chat)
        log.info(
            "branding.applied",
            market=market,
            username=draft.username,
            version=CHANNEL_BRANDING_VERSION,
        )
        return result
    except Exception as exc:
        log.error("branding.apply_failed", market=market, error=str(exc))
        return ChannelApplyResult(
            market=market,
            username=draft.username,
            before={},
            after={},
            errors=[str(exc)],
        )
    finally:
        if owns:
            client.close()


def apply_approved_branding(
    *,
    settings: Settings | None = None,
    markets: tuple[Market, ...] = ("ru", "en"),
    pin_welcome: bool = True,
    force: bool = False,
) -> BrandingApplyReport:
    settings = settings or get_settings()
    if not force and not settings.channel_branding_apply_enabled:
        raise RuntimeError(
            "CHANNEL_BRANDING_APPLY_ENABLED is false; pass force=True only after "
            "explicit owner approval (see CHANNEL_BRANDING_PROPOSAL.md)"
        )
    client = build_telegram_client(settings)
    if not isinstance(client, TelegramBotClient):
        raise RuntimeError("Telegram dry-run client cannot apply live branding")
    results: list[ChannelApplyResult] = []
    try:
        for market in markets:
            results.append(
                apply_channel_branding(
                    market,
                    settings=settings,
                    client=client,
                    pin_welcome=pin_welcome,
                )
            )
    finally:
        client.close()
    return BrandingApplyReport(branding_version=CHANNEL_BRANDING_VERSION, results=results)


__all__ = [
    "BrandingApplyReport",
    "ChannelApplyResult",
    "apply_approved_branding",
    "apply_channel_branding",
]
