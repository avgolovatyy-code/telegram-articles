"""Re-render a stored article.

Used by the admin preview, by test publication and whenever a product disappears from
the catalogue and the payload has to be rebuilt without it. It reads the persisted
Article JSON and the persisted media/product rows, so it never calls a model.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.tracking import TrackingService
from app.config import Market, Settings, get_settings
from app.db.models import Article, Product
from app.generation.context import MediaCandidate
from app.generation.schemas import ArticleDocument
from app.links.affiliate import AffiliateLinkBuilder, LinkContext
from app.telegram.renderer import RenderedArticle, RichMessageRenderer


def render_stored_article(
    session: Session,
    article: Article,
    *,
    settings: Settings | None = None,
    use_tracking: bool | None = None,
) -> RenderedArticle:
    settings = settings or get_settings()
    if not article.body:
        raise ValueError(f"article {article.id} has no stored body")

    market: Market = article.market  # type: ignore[assignment]
    document = ArticleDocument.model_validate(article.body)
    links = AffiliateLinkBuilder(settings)
    renderer = RichMessageRenderer(settings=settings, link_builder=links)
    tracking = TrackingService(session, settings=settings, link_builder=links)

    product_ids = [link.product_external_id for link in article.products]
    rows = (
        session.scalars(
            select(Product).where(Product.market == market, Product.external_id.in_(product_ids))
        ).all()
        if product_ids
        else []
    )
    products = {row.external_id: row for row in rows}

    media: dict[str, MediaCandidate] = {}
    for index, item in enumerate(sorted(article.media, key=lambda m: m.position)):
        media_id = item.media_key or f"m{index + 1}"
        media[media_id] = MediaCandidate(
            id=media_id,
            url=item.url,
            kind=item.kind,
            source_entity_type=item.source_entity_type or "product",
            source_entity_id=item.source_entity_id,
            product_external_id=item.product_external_id,
            caption=item.caption,
            role=item.role,
        )
    # Only assets that survived media validation the first time are still available.
    document.media_placements = [
        placement for placement in document.media_placements if placement.media_id in media
    ]

    audio_urls = {row.external_id: row.audio_preview_url for row in rows if row.audio_preview_url}

    link_context = LinkContext(
        market=market, article_id=article.public_id, topic_slug=article.topic_slug
    )
    tracked = settings.use_tracking_redirect if use_tracking is None else use_tracking

    def resolver(product_id: str, placement: str) -> str:
        product = products[product_id]
        affiliate_url = renderer.cards.product_url(product, market, link_context)
        if not tracked:
            return affiliate_url
        return tracking.get_or_create(
            article=article,
            market=market,
            target_url=affiliate_url,
            product_external_id=product_id,
            placement=placement,
            entity_type=article.entity_type,
            entity_external_id=article.entity_external_id,
        ).public_url

    inactive = {link.product_external_id for link in article.products if not link.active}
    document.product_placements = [
        placement
        for placement in document.product_placements
        if placement.product_id in products and placement.product_id not in inactive
    ]

    return renderer.render(
        document,
        market=market,
        products=products,
        media=media,
        link_context=link_context,
        entity_name=article.entity_name,
        audio_urls=audio_urls,
        url_resolver=resolver,
    )


__all__ = ["render_stored_article"]
