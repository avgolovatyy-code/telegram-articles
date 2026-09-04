"""Slack Block Kit payloads for editorial control."""

from __future__ import annotations

from typing import Any

from app.db.models import Article
from app.topics.coverage import CoverageReport

MARKET_FLAG = {"en": "🇬🇧", "ru": "🇷🇺"}

ACTION_PUBLISH = "article_publish"
ACTION_REJECT = "article_reject"
ACTION_REGENERATE = "article_regenerate"
ACTION_PUBLISH_TEST = "article_publish_test"
ACTION_HOLD = "article_hold"


def _text(markdown: str) -> dict[str, Any]:
    return {"type": "mrkdwn", "text": markdown}


def _section(markdown: str) -> dict[str, Any]:
    return {"type": "section", "text": _text(markdown)}


def _button(label: str, action_id: str, value: str, style: str | None = None) -> dict[str, Any]:
    button: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": label, "emoji": True},
        "action_id": action_id,
        "value": value,
    }
    if style:
        button["style"] = style
    return button


def _preview(article: Article, limit: int = 420) -> str:
    body = article.body or {}
    intro = str(body.get("intro") or "")
    if len(intro) > limit:
        intro = intro[: limit - 1].rsplit(" ", 1)[0] + "…"
    return intro or "_нет вступления_"


def article_card(
    article: Article, *, auto_publish: bool, admin_url: str | None = None
) -> list[dict[str, Any]]:
    """Card shown when an article is written and waiting for its slot.

    Control is Slack-first: buttons act here. ``admin_url`` is accepted for
    backward compatibility but no longer linked from the card.
    """
    del admin_url  # Slack is the control plane; admin is optional and unlinked.
    flag = MARKET_FLAG.get(article.market, article.market)
    quality = f"{article.quality_score:.2f}" if article.quality_score else "—"
    factuality = f"{article.factuality_score:.2f}" if article.factuality_score else "—"
    scheduled = (
        article.scheduled_for.strftime("%d.%m %H:%M UTC")
        if article.scheduled_for
        else "не назначена"
    )

    headline = (
        "Публикуется автоматически, вмешательство не требуется"
        if auto_publish
        else "Ожидает вашего решения"
    )

    blocks: list[dict[str, Any]] = [
        _section(f"{flag} *{article.title or article.primary_query}*"),
        _section(_preview(article)),
        {
            "type": "context",
            "elements": [
                _text(
                    f"#{article.id} · запрос: `{article.primary_query}` · "
                    f"{article.entity_type} {article.entity_name} · {article.char_count} знаков"
                )
            ],
        },
        {
            "type": "context",
            "elements": [
                _text(
                    f"качество {quality} · факты {factuality} · товаров "
                    f"{len(article.products)} · стоимость ${article.actual_cost_usd:.4f} · "
                    f"публикация {scheduled}"
                )
            ],
        },
        {"type": "context", "elements": [_text(f"_{headline}_")]},
        {
            "type": "actions",
            "block_id": f"article:{article.id}",
            "elements": (
                [
                    _button("Перегенерировать", ACTION_REGENERATE, str(article.id)),
                    _button("Снять", ACTION_REJECT, str(article.id), "danger"),
                ]
                if auto_publish
                else [
                    _button("Опубликовать сейчас", ACTION_PUBLISH, str(article.id), "primary"),
                    _button("В тест-канал", ACTION_PUBLISH_TEST, str(article.id)),
                    _button("Перегенерировать", ACTION_REGENERATE, str(article.id)),
                    _button("Снять", ACTION_REJECT, str(article.id), "danger"),
                ]
            ),
        },
        {"type": "divider"},
    ]
    return blocks


def published_card(
    article: Article, *, message_url: str | None, channel: str
) -> list[dict[str, Any]]:
    flag = MARKET_FLAG.get(article.market, article.market)
    link = f"<{message_url}|посмотреть в Telegram>" if message_url else "ссылка недоступна"
    return [
        _section(f"{flag} *Опубликовано:* {article.title or article.primary_query}"),
        {
            "type": "context",
            "elements": [
                _text(
                    f"{channel} · {link} · стоимость ${article.actual_cost_usd:.4f} · "
                    f"запрос `{article.primary_query}`"
                )
            ],
        },
    ]


def result_card(message: str, *, ok: bool = True) -> list[dict[str, Any]]:
    icon = "✅" if ok else "⚠️"
    return [_section(f"{icon} {message}")]


def digest_card(
    *,
    budget: Any,
    coverage: dict[str, CoverageReport],
    published_today: dict[str, int],
    admin_url: str | None = None,
) -> list[dict[str, Any]]:
    del admin_url
    spent_bar = min(1.0, budget.spent_usd / budget.budget_usd) if budget.budget_usd else 0.0
    filled = int(spent_bar * 20)
    bar = "█" * filled + "░" * (20 - filled)

    lines = [
        f"*Бюджет* `{bar}` ${budget.spent_usd:.2f} из ${budget.budget_usd:.2f}",
        f"*Сгенерировано:* EN {budget.generated.get('en', 0)} · RU {budget.generated.get('ru', 0)}",
        f"*Опубликовано:* EN {published_today.get('en', 0)} · RU {published_today.get('ru', 0)}",
        f"*Средняя стоимость статьи:* ${budget.average_article_cost_usd:.4f}",
    ]

    for market, report in coverage.items():
        flag = MARKET_FLAG.get(market, market)
        if report.exhausted:
            lines.append(f"{flag} материал закончился — {report.reason}")
        else:
            lines.append(f"{flag} осталось тем: {report.usable_candidates}")

    return [
        _section("*Сводка за день*"),
        _section("\n".join(lines)),
        {
            "type": "context",
            "elements": [_text("Управление: `/wegotrip status` · `coverage` · `pending`")],
        },
        {"type": "divider"},
    ]


def alert_card(title: str, detail: str) -> list[dict[str, Any]]:
    return [
        _section(f"🚨 *{title}*"),
        {"type": "context", "elements": [_text(detail[:2500])]},
    ]


def connected_card(
    *, bot_name: str, team: str, admin_url: str | None = None
) -> list[dict[str, Any]]:
    """Posted by ``wgt slack-check --post`` so the owner can see the bot is live."""
    del admin_url
    return [
        _section(f"*WeGoTrip Content Engine подключён* · {bot_name} @ {team}"),
        _section(
            "Публикация идёт автоматически. Здесь будут карточки статей, сводка "
            "за день и алерты. Кнопки нужны только если захотите вмешаться."
        ),
        {
            "type": "context",
            "elements": [
                _text("Управление через Slack: `/wegotrip status` · кнопки на карточках")
            ],
        },
    ]


__all__ = [
    "ACTION_HOLD",
    "ACTION_PUBLISH",
    "ACTION_PUBLISH_TEST",
    "ACTION_REGENERATE",
    "ACTION_REJECT",
    "alert_card",
    "article_card",
    "connected_card",
    "digest_card",
    "published_card",
    "result_card",
]
