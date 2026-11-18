from __future__ import annotations

import json

from app.dzen.editorial_ast import kazan_winter_weekend_ast
from app.dzen.kit import clipboard_html
from app.dzen.products import DzenProductPick
from app.dzen.quality import body_text, run_gates
from app.dzen.schemas import DzenArticleAST, DzenBlock
from app.dzen.slack_digest import send_dzen_digest
from tests.test_dzen_pipeline import ready_article
from tests.test_dzen_slack import RecordingSlack, _now


def _product(**overrides: object) -> DzenProductPick:
    payload = {
        "external_id": "1526",
        "title": "Городские легенды Казани",
        "slug": "legendy",
        "affiliate_url": (
            "https://wegotrip.ru/kazan-d551487/gorodskie-legendy-kazani-p1526/"
            "?coupon=435&utm_source=dzen&utm_medium=editorial&utm_campaign=dzen_ru"
        ),
        "inclusions": ["аудиогид"],
        "exclusions": [],
        "ticket_included": False,
        "cover": None,
        "city_name": "Казань",
        "snapshot": {},
        "is_free": True,
        "duration_label": "1 ч 30 мин–2 ч",
        "distance_label": "4 км",
        "listen_in_browser": True,
        "reader_pitch": (
            "Городские легенды Казани — бесплатная аудиоэкскурсия, 1 ч 30 мин–2 ч, "
            "маршрут около 4 км, слушать можно в браузере, приложение ставить не обязательно"
        ),
    }
    payload.update(overrides)
    return DzenProductPick(**payload)  # type: ignore[arg-type]


def _gates(ast: DzenArticleAST, product: DzenProductPick | None = None):
    products = [] if product is None else [product]
    return run_gates(
        ast,
        products=products,
        image_urls=["https://cdn.example/a.jpg"],
        cover_url="https://cdn.example/a.jpg",
    )


def test_hollow_two_day_headline_fails_gate():
    filler = (
        "Казань, Кремль, улица Баумана и Старо-Татарская слобода. "
        "Это конкретные места, а не универсальный каркас. "
    ) * 20
    ast = DzenArticleAST(
        headline="Казань за два дня: готовый маршрут без спешки",
        lead=(
            "Зимой Казань кажется компактной, но Кремль, Баумана и слобода — разные скорости. " * 4
        )[:400],
        format="dzen_weekend_itinerary",
        pillar="weekend_events",
        audience="russian_speaking_global",
        destination_city="Казань",
        blocks=[
            DzenBlock(type="heading", text="День первый: Кремль и Баумана"),
            DzenBlock(type="paragraph", text=filler),
            DzenBlock(type="heading", text="День второй: как получится"),
            DzenBlock(type="paragraph", text="Выберите что-нибудь тёплое и спокойное."),
            DzenBlock(type="heading", text="Короткий список"),
            DzenBlock(type="list", items=["Кремль", "Баумана", "слобода"]),
        ],
        practical_takeaway="Не пытайтесь закрыть весь город за один проход.",
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("headline_promise_gap" in issue or "day 2" in issue for issue in result.issues)


def test_warming_refrain_and_ops_note_fail():
    filler = (
        "Казань, Кремль, Баумана, слобода и озеро Кабан. Легенда Сююмбике здесь к месту. "
    ) * 25
    ast = DzenArticleAST(
        headline="Казань без спешки: слобода и Кремль за один световой день",
        lead=(
            "Слобода, Баумана и Кремль — три разные скорости, даже если на карте они рядом. " * 4
        )[:400],
        format="dzen_city_guide",
        pillar="city_guides",
        audience="russian_speaking_global",
        destination_city="Казань",
        blocks=[
            DzenBlock(type="heading", text="Кремль и слобода"),
            DzenBlock(
                type="paragraph",
                text=filler
                + "Мечеть Кул-Шариф здесь как бесплатная комната для согревания туристов.",
            ),
            DzenBlock(type="heading", text="Баумана"),
            DzenBlock(
                type="paragraph",
                text="Входной билет может быть отдельно — проверьте карточку товара. " + filler,
            ),
            DzenBlock(type="heading", text="Кабан"),
            DzenBlock(type="paragraph", text=filler),
        ],
        practical_takeaway="Сверяйте правила входа на месте.",
    )
    result = _gates(ast, _product())
    assert result.ok is False
    blob = " ".join(result.issues)
    assert "unsuitable_venue" in blob
    assert "ops note" in blob


def test_app_only_copy_fails_when_web_player_exists():
    filler = (
        "Казань, Кремль, Баумана, слобода, Сююмбике. Городская легенда про Алабрыса уместна. "
    ) * 22
    ast = DzenArticleAST(
        headline="Казань: слобода, Баумана и Кремль за светлый день",
        lead=(
            "Маршрут короткий: слобода, Баумана, Кремль. Слушать удобно с улицы, без гонки. " * 4
        )[:400],
        format="dzen_city_guide",
        pillar="city_guides",
        audience="russian_speaking_global",
        destination_city="Казань",
        blocks=[
            DzenBlock(type="heading", text="Слобода"),
            DzenBlock(type="paragraph", text=filler),
            DzenBlock(type="heading", text="Баумана"),
            DzenBlock(
                type="paragraph",
                text="Аудиогид доступен только в приложении, нужно приложение WeGoTrip. " + filler,
            ),
            DzenBlock(type="heading", text="Кремль"),
            DzenBlock(type="paragraph", text=filler),
        ],
        practical_takeaway="Наушники свои, маршрут около четырёх километров.",
    )
    result = _gates(ast, _product())
    assert result.ok is False
    assert any("web player" in issue or "app-only" in issue for issue in result.issues)


def test_kazan_weekend_ast_passes_and_matches_live_card():
    ast = kazan_winter_weekend_ast()
    product = _product()
    result = _gates(ast, product)
    assert result.ok, result.issues
    text = body_text(ast)
    assert "День первый" in text and "День второй" in text
    assert "Старо-Татарская слобода" in text
    assert "Баумана" in text
    assert "Кремл" in text
    assert "Кабан" in text
    assert "Чёрн" in text
    assert "4 км" in text
    assert "1,5–2 часа" in text or "1,5–2" in text
    assert "ставить не обязательно" not in text
    assert "это и есть весь первый день" not in text.casefold()
    assert text.casefold().count("полтора-два часа") <= 1
    assert "свияж" not in text.casefold()
    assert "проверьте карточку" not in text.casefold()
    html = clipboard_html(ast, [product])
    assert "бесплатн" in html.casefold()
    assert "проверьте карточку" not in html.casefold()
    assert "входной билет может быть отдельно" not in html.casefold()


def test_digest_holds_weak_copy_instead_of_pinging_staff(synced_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "dzen_slack_channel_id", "C0BTME6R546")
    article, _kit = ready_article(synced_session, settings)
    ast = DzenArticleAST.model_validate(article.body_ast)
    ast.headline = "Казань за два дня: готовый маршрут без спешки"
    article.headline = ast.headline
    article.body_ast = json.loads(ast.model_dump_json())
    synced_session.flush()
    client = RecordingSlack(settings)
    report = send_dzen_digest(
        synced_session, settings=settings, client=client, now=_now(19), force_hour=True
    )
    assert report.sent is False
    assert report.reason == "empty_queue"
    assert client.sent == []
    assert article.status == "needs_revision"
