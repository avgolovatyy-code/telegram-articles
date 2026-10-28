"""RussiaTravelPracticality vs EditorialInterestScore (spec 3.0 §4 / §8)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.editorial.mechanics import CULTURE_AXES, CULTURE_MECHANICS, PRACTICAL_TRAVEL_AXES

PracticalityStatus = Literal[
    "not_applicable",
    "verification_required",
    "verified",
    "unverified",
    "hold",
]


@dataclass(slots=True)
class EditorialInterestScore:
    interest: float = 0.0
    usefulness: float = 0.0
    original_angle: float = 0.0
    shareability: float = 0.0
    timeliness: float = 0.0
    market_fit: float = 0.0
    diversity_bonus: float = 0.0
    risk_penalty: float = 0.0
    commercial_fit: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        # Hypothesis weights from spec 3.0 §8 — one input, not the final editor.
        return (
            0.30 * (self.interest + self.usefulness) / 2
            + 0.20 * (self.original_angle + self.shareability) / 2
            + 0.15 * self.timeliness
            + 0.15 * self.market_fit
            + 0.15 * self.diversity_bonus
            + 0.05 * self.commercial_fit
            - self.risk_penalty
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total"] = round(self.total, 4)
        return payload


@dataclass(slots=True)
class RussiaTravelPracticality:
    status: PracticalityStatus = "not_applicable"
    origin_context: str = "Russia (do not claim access from every city)"
    entry_rules: str | None = None
    transport_feasibility: str | None = None
    payment_feasibility: str | None = None
    safety_and_access: str | None = None
    seasonality: str | None = None
    source_urls: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


FORBIDDEN_BARE_CLAIMS = (
    "без визы",
    "visa-free",
    "можно оплатить картой рф",
    "есть прямой рейс",
    "пускают всех",
    "english audio guide",
)


def requires_practicality_gate(
    *,
    audience_axis: str | None,
    editorial_mechanic: str | None,
    product_recommendation: str | None = None,
    recommends_travel: bool | None = None,
) -> bool:
    if recommends_travel is True:
        return True
    if product_recommendation == "required":
        return True
    if audience_axis in CULTURE_AXES or editorial_mechanic in CULTURE_MECHANICS:
        return False
    if audience_axis in PRACTICAL_TRAVEL_AXES:
        return True
    return editorial_mechanic == "practical_from_russia"


def evaluate_practicality(
    *,
    audience_axis: str | None,
    editorial_mechanic: str | None,
    claims: list[str] | None = None,
    verified_entry_rules: bool = False,
    product_recommendation: str | None = None,
    recommends_travel: bool | None = None,
) -> RussiaTravelPracticality:
    if not requires_practicality_gate(
        audience_axis=audience_axis,
        editorial_mechanic=editorial_mechanic,
        product_recommendation=product_recommendation,
        recommends_travel=recommends_travel,
    ):
        return RussiaTravelPracticality(
            status="not_applicable",
            reason="inspiration/culture/curiosity — no travel-accessibility penalty",
        )
    claims = claims or []
    lowered = " ".join(claims).casefold()
    if any(phrase in lowered for phrase in FORBIDDEN_BARE_CLAIMS) and not verified_entry_rules:
        return RussiaTravelPracticality(
            status="hold",
            unknowns=["unverified_practical_claim"],
            reason="категоричный практический совет без первичного источника",
        )
    if not verified_entry_rules:
        return RussiaTravelPracticality(
            status="verification_required",
            unknowns=["entry_or_transport_unverified"],
            reason="практическая поездка требует проверки до публикации совета",
        )
    return RussiaTravelPracticality(
        status="verified",
        reason="практические утверждения подтверждены",
    )


def hold_unverified_practical_advice(practicality: RussiaTravelPracticality) -> bool:
    return practicality.status in {"hold", "unverified"}


__all__ = [
    "FORBIDDEN_BARE_CLAIMS",
    "EditorialInterestScore",
    "RussiaTravelPracticality",
    "evaluate_practicality",
    "hold_unverified_practical_advice",
    "requires_practicality_gate",
]
