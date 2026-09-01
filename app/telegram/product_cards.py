"""Native WeGoTrip product cards for Telegram rich messages (spec §24).

Three shapes:

* **Hero** — image, title, one or two sentences of why, the facts the API actually
  returns, and a CTA button.
* **Compact** — title, benefit, price, button. For a mid-article recommendation.
* **Collection** — 2-5 products in one block with a single CTA.

Rating, duration and price are rendered only when the Affiliate API returned them.
Every URL comes from :class:`AffiliateLinkBuilder`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Market, Settings, get_settings
from app.db.models import Product
from app.links.affiliate import AffiliateLinkBuilder, LinkContext
from app.telegram import blocks as tb

CTA_TEXT = {
    "en": {
        "hero": "Get ticket & audio tour",
        "compact": "View on WeGoTrip",
        "collection": "See tours",
    },
    "ru": {
        "hero": "Билет и аудиогид",
        "compact": "Смотреть на WeGoTrip",
        "collection": "Все экскурсии",
    },
}

COLLECTION_TITLE = {
    "en": "Explore {entity} with WeGoTrip",
    "ru": "Посмотреть {entity} с WeGoTrip",
}

_FROM_LABEL = {"en": "from", "ru": "от"}
_DURATION_LABEL = {"en": "min", "ru": "мин"}
_REVIEWS_LABEL = {"en": "reviews", "ru": "отзывов"}


@dataclass(slots=True)
class RenderedProductCard:
    blocks: list[dict[str, Any]]
    product_external_id: str
    url: str
    placement: str


class TelegramProductCardRenderer:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        link_builder: AffiliateLinkBuilder | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.links = link_builder or AffiliateLinkBuilder(self.settings)

    # ------------------------------------------------------------------ urls
    def product_url(self, product: Product, market: Market, context: LinkContext) -> str:
        return self.links.product_url(
            market,
            product_slug=product.slug,
            product_id=product.external_id,
            city_slug=(product.raw or {}).get("city", {}).get("slug"),
            city_id=product.city_external_id,
            canonical_url=product.canonical_url,
            context=context,
        )

    # ----------------------------------------------------------------- cards
    def hero(
        self,
        product: Product,
        market: Market,
        context: LinkContext,
        *,
        pitch: str | None = None,
        url_override: str | None = None,
        used_image_urls: set[str] | None = None,
    ) -> RenderedProductCard:
        url = url_override or self.product_url(product, market, context)
        blocks: list[dict[str, Any]] = [tb.divider()]
        image = product.cover or product.preview
        already_shown = bool(image and used_image_urls and image in used_image_urls)
        # Skip the hero photo when the same URL already appeared as cover/media —
        # otherwise Telegram shows duplicate image+caption blocks.
        if image and not already_shown:
            # No caption on the photo: the 🎧 title line below is the label.
            blocks.append(tb.photo(image))
        blocks.append(tb.paragraph([{"type": "bold", "text": f"🎧 {product.title}"}]))
        summary = pitch or self._auto_pitch(product, market)
        if summary:
            blocks.append(tb.paragraph(summary))
        facts = self._fact_line(product, market)
        if facts:
            blocks.append(tb.paragraph([{"type": "italic", "text": facts}]))
        blocks.append(tb.buttons([tb.url_button(CTA_TEXT[market]["hero"], url, style="success")]))
        return RenderedProductCard(blocks, product.external_id, url, "hero")

    def compact(
        self,
        product: Product,
        market: Market,
        context: LinkContext,
        *,
        pitch: str | None = None,
        url_override: str | None = None,
    ) -> RenderedProductCard:
        url = url_override or self.product_url(product, market, context)
        blocks: list[dict[str, Any]] = [
            tb.paragraph([{"type": "bold", "text": product.title}]),
        ]
        summary = pitch or self._auto_pitch(product, market)
        if summary:
            blocks.append(tb.paragraph(summary))
        facts = self._fact_line(product, market)
        if facts:
            blocks.append(tb.paragraph([{"type": "italic", "text": facts}]))
        blocks.append(
            tb.buttons([tb.url_button(CTA_TEXT[market]["compact"], url, style="primary")])
        )
        return RenderedProductCard([tb.blockquote(blocks)], product.external_id, url, "compact")

    def collection(
        self,
        products: list[Product],
        market: Market,
        context: LinkContext,
        *,
        entity_name: str,
        landing_url: str | None = None,
        url_overrides: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[RenderedProductCard]]:
        overrides = url_overrides or {}
        cards: list[RenderedProductCard] = []
        items: list[Any] = []
        for product in products[:5]:
            url = overrides.get(product.external_id) or self.product_url(product, market, context)
            cards.append(RenderedProductCard([], product.external_id, url, "collection"))
            label = product.title
            price = self._price_text(product, market)
            if price:
                label = f"{label} — {price}"
            items.append(tb.link(label, url))

        title = COLLECTION_TITLE[market].format(entity=entity_name)
        blocks: list[dict[str, Any]] = [
            tb.divider(),
            tb.paragraph([{"type": "bold", "text": title}]),
            tb.bullet_list(items),
        ]
        cta_url = landing_url or (cards[0].url if cards else None)
        if cta_url:
            blocks.append(
                tb.buttons(
                    [tb.url_button(CTA_TEXT[market]["collection"], cta_url, style="primary")]
                )
            )
        return blocks, cards

    # ----------------------------------------------------------------- facts
    def _fact_line(self, product: Product, market: Market) -> str:
        parts: list[str] = []
        if product.rating is not None:
            rating = f"⭐ {product.rating:.1f}".rstrip("0").rstrip(".")
            if product.reviews_count:
                rating += f" ({product.reviews_count} {_REVIEWS_LABEL[market]})"
            parts.append(rating)
        duration = self._duration_text(product, market)
        if duration:
            parts.append(duration)
        price = self._price_text(product, market)
        if price:
            parts.append(price)
        return " · ".join(parts)

    def _duration_text(self, product: Product, market: Market) -> str | None:
        if product.duration_min is None and product.duration_max is None:
            return None
        label = _DURATION_LABEL[market]
        if (
            product.duration_min
            and product.duration_max
            and product.duration_min != product.duration_max
        ):
            return f"⏱ {product.duration_min}–{product.duration_max} {label}"
        value = product.duration_min or product.duration_max
        return f"⏱ {value} {label}"

    def _price_text(self, product: Product, market: Market) -> str | None:
        if product.price is None:
            return None
        symbol = product.currency_symbol or product.currency_code or ""
        amount = (
            f"{product.price:.0f}" if float(product.price).is_integer() else f"{product.price:.2f}"
        )
        return f"{_FROM_LABEL[market]} {amount} {symbol}".strip()

    def _auto_pitch(self, product: Product, market: Market) -> str | None:
        """Fallback copy built only from API fields — never invented."""
        highlights = product.highlights or []
        if highlights:
            return highlights[0]
        text = product.short_description or product.description
        if not text:
            return None
        sentence = text.strip().split(". ")[0].strip()
        if len(sentence) > 220:
            sentence = sentence[:217].rsplit(" ", 1)[0] + "…"
        _ = market
        return sentence


__all__ = ["CTA_TEXT", "RenderedProductCard", "TelegramProductCardRenderer"]
