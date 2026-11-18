"""Deterministic Dzen gates. Passing them means ready_for_handoff, not published."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.dzen.links import coupon_count, image_url_is_clean
from app.dzen.products import DzenProductPick, place_tokens
from app.dzen.schemas import DzenArticleAST

AI_CLICHES = (
    "погрузитесь в удивительный мир",
    "жемчужина, которую нельзя пропустить",
    "незабываемое путешествие",
    "скрытые жемчужины",
)
GENERIC_FLUFF = (
    "погуляйте",
    "посетите музей",
    "зайдите в кафе",
    "прогуляйтесь по центру",
    "обязательно посетите",
    "откройте для себя",
)
GENERIC_HEADINGS = {
    "зачем это читать",
    "как спланировать день",
    "на что смотреть",
}
FIRST_PERSON = (
    "я там был",
    "мы проверили на месте",
    "нашим редактором обнаружено",
)
UNSAFE_PAYMENT = (
    "любой билет в иностранный музей российской картой",
    "можно оплатить любой билет",
)


@dataclass(slots=True)
class GateResult:
    ok: bool
    issues: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.issues.append(message)


def body_text(ast: DzenArticleAST) -> str:
    parts = [ast.headline, ast.lead, ast.practical_takeaway]
    for block in ast.blocks:
        if block.text:
            parts.append(block.text)
        parts.extend(block.items)
    return "\n".join(parts)


OPS_LEAKS = (
    "проверьте карточку",
    "карточка товара",
    "уточните, входит ли входной билет",
    "входной билет может быть отдельно",
    "product_id",
    "media_asset_id",
)
WARM_INTERVAL = (
    "полтора-два часа",
    "каждые полтора",
    "тепловые интервалы",
    "точками восстановления",
    "блоками по 1,5",
    "блоками по 1,5–2",
)
SIDE_TRIPS = ("свияж", "петергоф", "иннополис")
TWO_DAY = re.compile(r"два(?:\s+\w+){0,2}\s+дн|двухдневн|2\s*дн|уикенд|выходн", re.I)
DAY_ONE = re.compile(r"день первый|первый день", re.I)
DAY_TWO = re.compile(r"день второй|второй день", re.I)
APP_ONLY = re.compile(r"только в приложении|нужно приложение|обязательно.+приложени", re.I)
STORY_HINTS = (
    "легенд",
    "сююмбик",
    "привид",
    "алабрыс",
    "джек",
    "екатерин",
    "марджан",
    "кул-шариф",
    "кул шариф",
    "юнусов",
)


def _sections(ast: DzenArticleAST) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current = ast.headline
    buf: list[str] = [ast.lead]
    for block in ast.blocks:
        if block.type == "heading" and block.text:
            sections.append((current, "\n".join(buf)))
            current = block.text
            buf = []
            continue
        if block.text:
            buf.append(block.text)
        buf.extend(block.items)
    sections.append((current, "\n".join(buf)))
    return sections


def run_gates(
    ast: DzenArticleAST,
    *,
    products: list[DzenProductPick],
    image_urls: list[str],
    cover_url: str | None,
    first_person_evidence: bool = False,
) -> GateResult:
    result = GateResult(ok=True)
    text = body_text(ast)
    folded = text.casefold()
    if len(ast.headline) < 20:
        result.fail("headline too short")
    if not (200 <= len(ast.lead) <= 600):
        result.fail("lead must explain why to read (200–600 chars)")
    if not (2500 <= len(text) <= 16000):
        result.fail(f"body length {len(text)} outside 2500–16000")
    headings = [b for b in ast.blocks if b.type == "heading"]
    if not (3 <= len(headings) <= 7):
        result.fail("need 3–7 section headings")
    for phrase in AI_CLICHES:
        if phrase in folded:
            result.fail(f"AI cliché: {phrase}")
    if not first_person_evidence:
        for phrase in FIRST_PERSON:
            if phrase in folded:
                result.fail(f"unverified first-person: {phrase}")
    for phrase in UNSAFE_PAYMENT:
        if phrase in folded:
            result.fail("unqualified payment claim")
    if len(products) > 3:
        result.fail("more than 3 product mentions")
    for product in products:
        if coupon_count(product.affiliate_url) != 1:
            result.fail(f"bad coupon on {product.external_id}")
        if "utm_source=dzen" not in product.affiliate_url:
            result.fail(f"missing dzen utm on {product.external_id}")
    for url in image_urls:
        if not image_url_is_clean(url):
            result.fail("image URL must be https without coupon")
    if cover_url is None:
        result.fail("cover image missing")
    high_risk = [c for c in ast.claims if c.risk == "high" and c.verification_status != "verified"]
    if high_risk:
        result.fail("unverified high-risk claims must be omitted")
    if re.search(r"\{\{|\}\}", text):
        result.fail("template placeholders in article text")
    fluff_hits = [phrase for phrase in GENERIC_FLUFF if phrase in folded]
    if len(fluff_hits) >= 2:
        result.fail("generic any-city fluff")
    named = place_tokens(text)
    if ast.destination_city:
        named.add(ast.destination_city.casefold())
    if len(named) < 4:
        result.fail("need named places, not a universal stroll-museum-cafe outline")
    specific_headings = [
        b.text for b in headings if b.text and b.text.strip().casefold() not in GENERIC_HEADINGS
    ]
    if len(specific_headings) < 2:
        result.fail("headings must name real places or problems, not generic labels")
    for leak in OPS_LEAKS:
        if leak in folded:
            result.fail(f"ops note leaked into copy: {leak}")
    warm_hits = sum(folded.count(phrase) for phrase in WARM_INTERVAL)
    if warm_hits > 1:
        result.fail("repeated warming-interval advice")
    dest = (ast.destination_city or "").casefold()
    for stem in SIDE_TRIPS:
        if stem in folded and stem not in dest and stem not in ast.headline.casefold():
            result.fail(f"side-trip {stem} stuffed into {ast.destination_city or 'article'}")
    if TWO_DAY.search(ast.headline):
        if not DAY_ONE.search(text) or not DAY_TWO.search(text):
            result.fail("headline promises two days but the days are not both written")
        day_two_places = 0
        for title, body in _sections(ast):
            if DAY_TWO.search(title) or DAY_TWO.search(body[:80]):
                day_two_places = len(place_tokens(title, body))
                break
        if day_two_places < 2:
            result.fail("day two needs named places, not a vague leftover slot")
    if not any(hint in folded for hint in STORY_HINTS) and len(named) < 6:
        result.fail("needs a local story or unusual detail, not only tourist advice")
    for product in products:
        pitch_space = folded + " " + (product.reader_pitch or "").casefold()
        if product.duration_label and not any(token in folded for token in ("час", "мин", "км")):
            result.fail(f"product {product.external_id} duration missing from article")
        if (
            product.distance_label
            and product.distance_label.casefold() not in folded
            and "км" not in folded
        ):
            result.fail(f"product {product.external_id} distance missing from article")
        if product.listen_in_browser and APP_ONLY.search(text) and "браузер" not in folded:
            result.fail("web player exists; do not describe the tour as app-only")
        if product.is_free and "проверьте карточку" in pitch_space:
            result.fail("free product described with a checkout ops note")
    return result


__all__ = ["GateResult", "body_text", "run_gates"]
