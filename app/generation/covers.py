"""Generated cover images — a controlled exception, off by default.

Inline illustrations and product imagery always come from the WeGoTrip API. A generated
image is allowed only as the hero cover, only when ``ALLOW_GENERATED_COVERS=true``, only
when the API has no suitable cover, and only when the daily budget still allows it.

The prompt is deliberately abstract: it never depicts a specific museum, exhibit or
landmark, because a plausible-looking fake photograph of a real place would mislead the
reader. That is also why a generated cover never replaces an available API photo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.ai.budget import BudgetManager
from app.ai.pricing import IMAGE_GENERATION_USD
from app.ai.provider import LLMProvider
from app.config import Market, Settings, get_settings
from app.db.enums import CostKind
from app.logging_setup import get_logger
from app.media_assets import MediaCandidate

log = get_logger("generation.covers")

GENERATED_DIR = Path("var/generated")

_PROMPT = {
    "en": (
        "A tasteful, abstract editorial illustration for a travel article about {entity}. "
        "Flat vector style, soft muted palette, generous negative space, no text, no logos. "
        "Do not depict any identifiable building, monument, artwork or person — suggest the "
        "mood of the destination through colour, light and simple geometry only."
    ),
    "ru": (
        "Аккуратная абстрактная редакционная иллюстрация для travel-статьи про {entity}. "
        "Плоский векторный стиль, приглушённая палитра, много воздуха, без текста и логотипов. "
        "Не изображай узнаваемые здания, памятники, произведения искусства и людей — "
        "передай настроение места только цветом, светом и простой геометрией."
    ),
}


@dataclass(slots=True)
class CoverDecision:
    allowed: bool
    reason: str


class GeneratedCoverService:
    def __init__(
        self,
        provider: LLMProvider,
        budget: BudgetManager,
        *,
        settings: Settings | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.provider = provider
        self.budget = budget
        self.settings = settings or get_settings()
        self.output_dir = output_dir or GENERATED_DIR

    def evaluate(self, *, api_media_available: bool) -> CoverDecision:
        if not self.settings.allow_generated_covers:
            return CoverDecision(False, "generated covers are disabled")
        if api_media_available:
            return CoverDecision(False, "the API provides a suitable cover")
        decision = self.budget.can_start_article("en", estimated_cost_usd=IMAGE_GENERATION_USD)
        if not decision.allowed:
            return CoverDecision(False, f"budget: {decision.reason}")
        return CoverDecision(True, "no API cover available")

    def generate(
        self,
        *,
        market: Market,
        entity_name: str,
        article_id: int | None = None,
        api_media_available: bool = False,
    ) -> MediaCandidate | None:
        decision = self.evaluate(api_media_available=api_media_available)
        if not decision.allowed:
            log.info("cover.skipped", reason=decision.reason, entity=entity_name)
            return None

        prompt = _PROMPT[market].format(entity=entity_name)
        image = self.provider.generate_image(prompt)
        if not image:
            log.warning("cover.generation_failed", entity=entity_name)
            return None

        self.budget.record(
            amount_usd=IMAGE_GENERATION_USD,
            market=market,
            article_id=article_id,
            kind=CostKind.IMAGE,
            task="image_generation",
            model=self.settings.openai_image_model,
            note=f"generated cover for {entity_name}",
        )

        digest = hashlib.sha256(image).hexdigest()[:24]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{digest}.png"
        path.write_bytes(image)

        url = f"{self.settings.tracking_root}/media/generated/{digest}.png"
        log.info("cover.generated", entity=entity_name, url=url)
        return MediaCandidate(
            id="gen1",
            url=url,
            kind="photo",
            source_entity_type="generated",
            caption=None,
            role="cover",
        )


__all__ = ["GENERATED_DIR", "CoverDecision", "GeneratedCoverService"]
