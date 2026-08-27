"""Article JSON → Telegram ``InputRichMessage``.

The LLM never produces Telegram markup. This renderer owns every heading, list,
divider, media block, product card and — critically — every URL.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.config import Market, Settings, get_settings
from app.db.models import Product
from app.generation.quality import normalize_hashtags
from app.generation.schemas import ArticleBlock, ArticleDocument
from app.links.affiliate import AffiliateLinkBuilder, LinkContext
from app.media_assets import MediaCandidate
from app.telegram import blocks as tb
from app.telegram.product_cards import RenderedProductCard, TelegramProductCardRenderer

FAQ_TITLE = {"en": "FAQ", "ru": "Частые вопросы"}
SOURCES_TITLE = {"en": "Sources", "ru": "Источники"}

#: Resolves a product id + placement to the URL that should be used in the card.
UrlResolver = Callable[[str, str], str]


@dataclass(slots=True)
class RenderedArticle:
    message: dict[str, Any]
    product_cards: list[RenderedProductCard] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)
    used_media_ids: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    @property
    def urls(self) -> list[str]:
        return tb.collect_urls(self.message)


class RichMessageRenderer:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        link_builder: AffiliateLinkBuilder | None = None,
        card_renderer: TelegramProductCardRenderer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.links = link_builder or AffiliateLinkBuilder(self.settings)
        self.cards = card_renderer or TelegramProductCardRenderer(
            settings=self.settings, link_builder=self.links
        )

    def render(
        self,
        document: ArticleDocument,
        *,
        market: Market,
        products: dict[str, Product],
        media: dict[str, MediaCandidate],
        link_context: LinkContext,
        entity_name: str,
        audio_urls: dict[str, str] | None = None,
        url_resolver: UrlResolver | None = None,
        blocked_media_ids: set[str] | None = None,
    ) -> RenderedArticle:
        audio_urls = audio_urls or {}
        blocked_media_ids = blocked_media_ids or set()
        out: list[dict[str, Any]] = []
        cards: list[RenderedProductCard] = []
        used_media: list[str] = []

        def resolve(product: Product, placement: str) -> str:
            if url_resolver is not None:
                return url_resolver(product.external_id, placement)
            return self.cards.product_url(product, market, link_context)

        cover = self._cover(media, blocked_media_ids)
        if cover is not None:
            out.append(tb.photo(cover.url, caption=cover.caption))
            used_media.append(cover.id)

        out.append(tb.heading(document.title, size=1))
        if document.intro.strip():
            out.append(tb.paragraph(document.intro.strip()))

        placements_by_section: dict[int, list[Any]] = {}
        for placement in document.product_placements:
            placements_by_section.setdefault(placement.after_section, []).append(placement)
        media_by_section: dict[int, list[Any]] = {}
        for placement in document.media_placements:
            media_by_section.setdefault(placement.after_section, []).append(placement)
        audio_by_section: dict[int, list[Any]] = {}
        for placement in document.audio_placements:
            audio_by_section.setdefault(placement.after_section, []).append(placement)

        collection_products: list[Product] = []

        for index, section in enumerate(document.sections):
            out.append(tb.heading(section.heading, size=min(max(section.level, 2), 3)))
            for block in section.blocks:
                rendered = self._render_block(block)
                if rendered is not None:
                    out.append(rendered)

            for placement in media_by_section.get(index, []):
                candidate = media.get(placement.media_id)
                if (
                    candidate is None
                    or candidate.id in used_media
                    or candidate.id in blocked_media_ids
                ):
                    continue
                out.append(tb.photo(candidate.url, caption=placement.caption or candidate.caption))
                used_media.append(candidate.id)

            for placement in audio_by_section.get(index, []):
                url = audio_urls.get(placement.product_id)
                product = products.get(placement.product_id)
                if not url or product is None:
                    continue
                out.append(
                    tb.audio(
                        url,
                        title=product.title,
                        performer="WeGoTrip",
                        caption=placement.caption,
                    )
                )

            for placement in placements_by_section.get(index, []):
                product = products.get(placement.product_id)
                if product is None:
                    continue
                if placement.placement == "collection":
                    collection_products.append(product)
                    continue
                card = (
                    self.cards.hero(
                        product,
                        market,
                        link_context,
                        pitch=placement.pitch,
                        url_override=resolve(product, "hero"),
                    )
                    if placement.placement == "hero"
                    else self.cards.compact(
                        product,
                        market,
                        link_context,
                        pitch=placement.pitch,
                        url_override=resolve(product, "compact"),
                    )
                )
                out.extend(card.blocks)
                cards.append(card)

        if document.faq:
            out.append(tb.divider())
            out.append(tb.heading(FAQ_TITLE[market], size=2))
            for item in document.faq:
                out.append(tb.details(item.question, [tb.paragraph(item.answer)]))

        if collection_products:
            overrides = {p.external_id: resolve(p, "collection") for p in collection_products}
            collection_blocks, collection_cards = self.cards.collection(
                collection_products,
                market,
                link_context,
                entity_name=entity_name,
                url_overrides=overrides,
            )
            out.extend(collection_blocks)
            cards.extend(collection_cards)

        if document.closing:
            out.append(tb.paragraph(document.closing))

        hashtags = normalize_hashtags(document.hashtags, self.settings)
        if hashtags:
            out.append(tb.footer(_hashtag_line(hashtags)))

        message = tb.rich_message(out, is_rtl=False)
        return RenderedArticle(
            message=message,
            product_cards=cards,
            media_urls=tb.collect_media_urls(message),
            used_media_ids=used_media,
            hashtags=hashtags,
        )

    # ---------------------------------------------------------------- blocks
    def _render_block(self, block: ArticleBlock) -> dict[str, Any] | None:
        match block.type:
            case "paragraph":
                return tb.paragraph(block.text) if block.text else None
            case "list":
                return tb.bullet_list(block.items) if block.items else None
            case "ordered_list":
                return tb.ordered_list(block.items) if block.items else None
            case "quote":
                return (
                    tb.blockquote([tb.paragraph(block.text)], block.credit) if block.text else None
                )
            case "tip":
                return tb.pull_quote(block.text) if block.text else None
            case "table":
                return tb.table(block.rows) if block.rows else None
            case "divider":
                return tb.divider()
        return tb.paragraph(block.text) if block.text else None

    def _cover(self, media: dict[str, MediaCandidate], blocked: set[str]) -> MediaCandidate | None:
        for candidate in media.values():
            if candidate.role == "cover" and candidate.id not in blocked:
                return candidate
        for candidate in media.values():
            if candidate.id not in blocked and candidate.kind == "photo":
                return candidate
        return None


def _hashtag_line(tags: list[str]) -> list[Any]:
    out: list[Any] = []
    for index, tag in enumerate(tags):
        if index:
            out.append(" ")
        out.append(tb.hashtag(tag))
    return out


__all__ = ["FAQ_TITLE", "RenderedArticle", "RichMessageRenderer", "UrlResolver"]
