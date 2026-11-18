"""Deterministic Dzen gates. Passing them means ready_for_handoff, not published."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.dzen.links import coupon_count, image_url_is_clean
from app.dzen.products import DzenProductPick
from app.dzen.schemas import DzenArticleAST

AI_CLICHES = (
    "погрузитесь в удивительный мир",
    "жемчужина, которую нельзя пропустить",
    "незабываемое путешествие",
    "скрытые жемчужины",
)
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
    return result


__all__ = ["GateResult", "body_text", "run_gates"]
