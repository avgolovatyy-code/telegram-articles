"""Max channel id resolution and RU fan-out helpers."""

from __future__ import annotations

from app.db.enums import ArticleStatus
from app.db.models import Article, ArticleProduct
from app.max.chat_id import (
    chat_id_from_public_html,
    normalize_channel_ref,
    parse_numeric_chat_id,
    resolve_max_chat_id,
)
from app.max.publisher import MaxPublisher
from app.max.renderer import MAX_TEXT_CHARS, render_max_payload


def make_article(session, *, market: str = "ru", **overrides) -> Article:
    article = Article(
        public_id=overrides.pop("public_id", f"max-{market}-{session.query(Article).count()}"),
        market=market,
        topic_slug="barcelona",
        entity_type="city",
        entity_external_id="1",
        entity_name="Barcelona" if market == "en" else "Барселона",
        intent="things_to_do",
        primary_query="что посмотреть в Барселоне",
        status=overrides.pop("status", ArticleStatus.PUBLISHED),
        current_version=1,
        title=overrides.pop("title", "Барселона за выходные"),
        body=overrides.pop(
            "body",
            {
                "title": "Барселона за выходные",
                "intro": "Короткий план.",
                "sections": [
                    {
                        "heading": "Саграда Фамилия",
                        "level": 2,
                        "blocks": [
                            {"type": "paragraph", "text": "Билет лучше брать заранее. " * 200}
                        ],
                    }
                ],
                "product_placements": [],
                "media_placements": [],
                "audio_placements": [],
                "faq": [],
                "hashtags": [],
                "claims": [],
                "closing": "Приятной поездки.",
            },
        ),
        **overrides,
    )
    session.add(article)
    session.flush()
    return article


def test_parse_numeric_and_slug_refs():
    assert parse_numeric_chat_id("-71234567890123") == -71234567890123
    assert parse_numeric_chat_id("71234567890123") == 71234567890123
    assert parse_numeric_chat_id("NNNNNNNN_biz") is None
    assert normalize_channel_ref("https://max.ru/idNNNNNNNN_biz") == "idNNNNNNNN_biz"
    assert normalize_channel_ref("NNNNNNNN_biz") == "NNNNNNNN_biz"


def test_chat_id_from_public_html_negates_channel_id():
    html = 'canonical:"https://max.ru/idNNNNNNNN_biz"},channelId:71234567890123}},isBot:true'
    assert chat_id_from_public_html(html) == -71234567890123


def test_resolve_numeric_without_network():
    assert resolve_max_chat_id("-71234567890123") == -71234567890123


def test_render_max_payload_fits_limit_and_adds_product_buttons(session, settings):
    article = make_article(session)
    session.add(
        ArticleProduct(
            article_id=article.id,
            product_external_id="p1",
            placement="compact",
            position=0,
            snapshot={"title": "Аудиогид по Готическому кварталу"},
            affiliate_url="https://wegotrip.ru/product/1?coupon=435",
            active=True,
        )
    )
    session.flush()
    session.refresh(article)

    payload = render_max_payload(article)
    assert len(payload["text"]) <= MAX_TEXT_CHARS
    assert "Барселона" in payload["text"]
    assert payload["format"] == "markdown"
    assert payload["attachments"][0]["type"] == "inline_keyboard"
    assert payload["attachments"][0]["payload"]["buttons"][0][0]["url"].startswith("https://")


def test_max_publisher_skips_when_unconfigured(session, settings):
    article = make_article(session, body={"title": "x", "intro": "y", "sections": []})
    result = MaxPublisher(settings=settings).publish_ru(article)
    assert result.skipped is True
    assert result.ok


def test_max_publisher_skips_en_market(session, settings, monkeypatch):
    monkeypatch.setattr(settings, "max_bot_token", "token")
    monkeypatch.setattr(settings, "max_ru_channel_id", "-1")
    article = make_article(
        session,
        market="en",
        title="x",
        body={"title": "x", "intro": "y", "sections": []},
    )
    result = MaxPublisher(settings=settings).publish_ru(article)
    assert result.skipped is True


def test_max_publisher_failure_does_not_raise(session, settings, monkeypatch):
    class BoomClient:
        def send_message(self, **kwargs):
            raise RuntimeError("max down")

    monkeypatch.setattr(settings, "max_bot_token", "token")
    monkeypatch.setattr(settings, "max_ru_channel_id", "-1")
    article = make_article(
        session,
        title="Заголовок",
        body={"title": "Заголовок", "intro": "Текст", "sections": []},
    )
    result = MaxPublisher(settings=settings, client=BoomClient()).publish_ru(article)  # type: ignore[arg-type]
    assert result.skipped is False
    assert result.ok is False
    assert "max down" in (result.error or "")
