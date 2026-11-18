from __future__ import annotations

from pathlib import Path

from app.dzen.kit import clipboard_html, sanitize_for_dzen_editor
from app.dzen.products import DzenProductPick
from app.dzen.schemas import DzenArticleAST, DzenBlock


def _ast() -> DzenArticleAST:
    return DzenArticleAST(
        headline="Казань без спешки: маршрут между Кремлём и слободой",
        lead="x" * 220,
        format="dzen_city_guide",
        pillar="city_guides",
        audience="russian_speaking_global",
        blocks=[
            DzenBlock(type="heading", text="Кремль: с чего начать"),
            DzenBlock(type="paragraph", text="Начните с Кремля, не с соседнего острова."),
            DzenBlock(type="list", items=["Кремль утром", "Баумана днём"]),
            DzenBlock(type="product_mention", product_id="1526"),
        ],
        practical_takeaway="Сверяйте часы на официальной странице Кремля.",
    )


def _product() -> DzenProductPick:
    return DzenProductPick(
        external_id="1526",
        title="Городские легенды Казани",
        slug="legendy",
        affiliate_url=(
            "https://wegotrip.ru/kazan-d551487/gorodskie-legendy-kazani-p1526/"
            "?coupon=435&utm_source=dzen&utm_medium=editorial&utm_campaign=dzen_ru"
        ),
        inclusions=["аудиогид"],
        exclusions=[],
        ticket_included=False,
        cover=None,
        city_name="Казань",
        snapshot={},
        is_free=True,
        duration_label="1 ч 30 мин–2 ч",
        distance_label="4 км",
        listen_in_browser=True,
        reader_pitch=(
            "Городские легенды Казани — бесплатная аудиоэкскурсия, 1 ч 30 мин–2 ч, "
            "маршрут около 4 км, слушать можно в браузере, приложение ставить не обязательно"
        ),
    )


def test_dzen_sanitizer_keeps_headings_lists_and_https_links():
    raw = clipboard_html(_ast(), [_product()])
    cleaned = sanitize_for_dzen_editor(raw)
    assert "<h2>" in cleaned
    assert "<h3>" in cleaned
    assert "<ul>" in cleaned and "<li>" in cleaned
    assert 'href="https://wegotrip.ru/' in cleaned
    assert "coupon=435" in cleaned
    assert "<script" not in cleaned
    assert "<img" not in cleaned
    assert "бесплатн" in cleaned.casefold()
    assert "браузер" in cleaned.casefold()
    assert "проверьте карточку" not in cleaned.casefold()


def test_clipboard_wraps_start_fragment_for_editors():
    html = clipboard_html(_ast(), [_product()])
    assert html.startswith("<!--StartFragment-->")
    assert html.endswith("<!--EndFragment-->")
    assert "<h2>" in html


def test_kit_css_uses_full_phone_width():
    css = Path("app/admin/static/admin.css").read_text(encoding="utf-8")
    assert "body.dzen-handoff { overflow-x: clip; }" in css
    assert "body.dzen-handoff main" in css
    assert "max-width: none" in css
    assert "@media (max-width: 640px)" in css
