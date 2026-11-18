"""Publishing Kit: magazine HTML, clipboard payloads, ZIP, product links."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.enums import DzenArticleStatus
from app.db.models import DzenArticle, DzenPublishingKit
from app.db.types import utcnow
from app.dzen.media import (
    DzenMediaAsset,
    build_zip,
    dedupe_downloaded,
    download_asset,
    staging_dir,
)
from app.dzen.products import DzenProductPick
from app.dzen.schemas import DzenArticleAST, DzenBlock

FORBIDDEN_COPY_MARKERS = (
    "{{",
    "}}",
    "product_id",
    "media_asset_id",
    "/admin/",
    "internal-source",
)


def _plain_block(block: DzenBlock) -> str:
    if block.type == "heading":
        return f"\n{(block.text or '').strip()}\n"
    if block.type in {"list", "ordered_list"}:
        bullet = "1." if block.type == "ordered_list" else "•"
        return "\n".join(f"{bullet} {item}" for item in block.items) + "\n"
    if block.type == "image":
        return f"[{block.caption or 'изображение'}]\n"
    if block.type == "product_mention":
        return ""
    if block.type == "takeaway":
        return f"\nКоротко: {(block.text or '').strip()}\n"
    return f"{(block.text or '').strip()}\n"


def render_plain(ast: DzenArticleAST, products: list[DzenProductPick]) -> str:
    parts = [ast.headline.strip(), "", ast.lead.strip(), ""]
    for block in ast.blocks:
        parts.append(_plain_block(block))
    if ast.practical_takeaway:
        parts.extend(["", ast.practical_takeaway.strip()])
    if products:
        parts.append("\nПодходящие варианты:\n")
        for product in products:
            ticket = (
                "билет включён" if product.ticket_included else "уточните, входит ли входной билет"
            )
            parts.append(f"— {product.title} ({ticket}): {product.affiliate_url}")
    return "\n".join(parts).strip() + "\n"


def _p(text: str) -> str:
    return f"<p>{html.escape(text)}</p>"


def render_html(
    ast: DzenArticleAST,
    products: list[DzenProductPick],
    assets: list[DzenMediaAsset],
    *,
    include_images: bool = True,
) -> str:
    chunks: list[str] = [f"<h2>{html.escape(ast.headline)}</h2>", _p(ast.lead)]
    product_by_id = {item.external_id: item for item in products}
    used_products: set[str] = set()
    for block in ast.blocks:
        if block.type == "heading":
            chunks.append(f"<h3>{html.escape(block.text or '')}</h3>")
        elif block.type == "list":
            items = "".join(f"<li>{html.escape(item)}</li>" for item in block.items)
            chunks.append(f"<ul>{items}</ul>")
        elif block.type == "ordered_list":
            items = "".join(f"<li>{html.escape(item)}</li>" for item in block.items)
            chunks.append(f"<ol>{items}</ol>")
        elif block.type == "image" and include_images:
            asset = next((a for a in assets if a.asset_id == block.media_asset_id), None)
            url = asset.url if asset else ""
            if url:
                cap = html.escape(block.caption or (asset.caption if asset else ""))
                chunks.append(
                    f'<p><img src="{html.escape(url)}" alt="{cap}"></p><p><em>{cap}</em></p>'
                )
        elif block.type == "product_mention":
            product = product_by_id.get(block.product_id or "")
            if product and product.external_id not in used_products:
                used_products.add(product.external_id)
                chunks.append(_product_html(product))
        elif block.type == "takeaway":
            chunks.append(f"<p><strong>{html.escape(block.text or '')}</strong></p>")
        elif block.text:
            chunks.append(_p(block.text))
    if ast.practical_takeaway:
        chunks.append(f"<h3>Коротко</h3>{_p(ast.practical_takeaway)}")
    leftover = [p for p in products if p.external_id not in used_products]
    if leftover:
        chunks.append("<h3>Подходящие варианты</h3>")
        for product in leftover:
            chunks.append(_product_html(product))
    html_body = "\n".join(chunks)
    for marker in FORBIDDEN_COPY_MARKERS:
        if marker in {"product_id", "media_asset_id"}:
            continue
        html_body = html_body.replace(marker, "")
    return html_body


def _product_html(product: DzenProductPick) -> str:
    ticket = (
        "входной билет включён"
        if product.ticket_included
        else "входной билет может быть отдельно — проверьте карточку товара"
    )
    return (
        f'<p><a href="{html.escape(product.affiliate_url)}">'
        f"{html.escape(product.title)}</a> — {html.escape(ticket)}.</p>"
    )


ALLOWED_DZEN_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "a", "strong", "em", "br"}


def sanitize_for_dzen_editor(raw_html: str) -> str:
    """Keep the tags Dzen's article editor typically preserves on paste."""
    from html.parser import HTMLParser

    class _Strip(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.out: list[str] = []
            self._anchor = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag not in ALLOWED_DZEN_TAGS:
                return
            if tag == "br":
                self.out.append("<br>")
                return
            if tag == "a":
                href = next((value or "" for name, value in attrs if name == "href"), "")
                if href.startswith("https://"):
                    self.out.append(f'<a href="{html.escape(href, quote=True)}">')
                    self._anchor = True
                return
            self.out.append(f"<{tag}>")

        def handle_endtag(self, tag: str) -> None:
            if tag == "br" or tag not in ALLOWED_DZEN_TAGS:
                return
            if tag == "a":
                if self._anchor:
                    self.out.append("</a>")
                    self._anchor = False
                return
            self.out.append(f"</{tag}>")

        def handle_data(self, data: str) -> None:
            self.out.append(html.escape(data, quote=False))

    parser = _Strip()
    parser.feed(raw_html or "")
    parser.close()
    return "".join(parser.out)


def clipboard_html(ast: DzenArticleAST, products: list[DzenProductPick]) -> str:
    """Rich text for Dzen paste: basic tags only, no images (staff uploads them)."""
    inner = sanitize_for_dzen_editor(render_html(ast, products, assets=[], include_images=False))
    return f"<!--StartFragment-->{inner}<!--EndFragment-->"


def content_hash(html_body: str, plain_body: str) -> str:
    return hashlib.sha256(f"{html_body}\n{plain_body}".encode()).hexdigest()


def persist_kit(
    session: Session,
    article: DzenArticle,
    ast: DzenArticleAST,
    products: list[DzenProductPick],
    assets: list[DzenMediaAsset],
    settings: Settings | None = None,
) -> DzenPublishingKit:
    settings = settings or get_settings()
    html_body = clipboard_html(ast, products)
    plain_body = render_plain(ast, products)
    preview_html = render_html(ast, products, assets, include_images=True)
    digest = content_hash(html_body, plain_body)
    expires = utcnow() + dt.timedelta(days=int(settings.dzen_kit_ttl_days))
    zip_path = None
    zip_sha = None
    staged: list[DzenMediaAsset] = []
    if settings.dzen_asset_zip_enabled and assets:
        for asset in assets:
            try:
                staged.append(download_asset(asset, settings))
            except Exception:
                continue
        staged = dedupe_downloaded(staged)
        if staged:
            path, zip_sha = build_zip(staged, staging_dir(article.public_id) / "media.zip")
            zip_path = str(path)
    previous = session.scalars(
        select(DzenPublishingKit).where(
            DzenPublishingKit.article_id == article.id,
            DzenPublishingKit.stale.is_(False),
        )
    )
    for row in previous:
        row.stale = True
    cover = next((a for a in assets if a.role == "cover"), assets[0] if assets else None)
    kit = DzenPublishingKit(
        article_id=article.id,
        article_version=article.version,
        access_token=secrets.token_urlsafe(32),
        html_body=html_body,
        plain_body=plain_body,
        cover_url=cover.url if cover else None,
        cover_asset_id=cover.asset_id if cover else None,
        media_manifest_json=[
            {
                "asset_id": a.asset_id,
                "url": a.url,
                "role": a.role,
                "caption": a.caption,
                "after_heading": a.after_heading,
                "content_type": a.content_type,
            }
            for a in assets
        ],
        product_links_json=[
            {
                "product_id": p.external_id,
                "title": p.title,
                "url": p.affiliate_url,
                "ticket_included": p.ticket_included,
                "inclusions": p.inclusions,
                "verified_at": utcnow().date().isoformat(),
            }
            for p in products
        ],
        zip_asset_path=zip_path,
        zip_sha256=zip_sha,
        content_hash=digest,
        ready_at=utcnow(),
        expires_at=expires,
    )
    session.add(kit)
    article.content_hash = digest
    article.media_manifest = kit.media_manifest_json
    article.body_ast = json.loads(ast.model_dump_json())
    article.status = DzenArticleStatus.READY_FOR_HANDOFF.value
    article.ready_at = utcnow()
    session.flush()
    kit.html_body = html_body
    # Store preview separately in article quality_scores so the kit copy stays clean.
    scores = dict(article.quality_scores or {})
    scores["preview_html"] = preview_html
    article.quality_scores = scores
    return kit


def kit_is_expired(kit: DzenPublishingKit, now: dt.datetime | None = None) -> bool:
    if kit.expires_at is None:
        return False
    clock = now or utcnow()
    return clock >= kit.expires_at


def public_kit_path(kit: DzenPublishingKit) -> str:
    return f"/dzen/k/{kit.access_token}"


def admin_kit_path(article: DzenArticle) -> str:
    return f"/admin/dzen/publishing-kits/{article.public_id}"


__all__ = [
    "FORBIDDEN_COPY_MARKERS",
    "admin_kit_path",
    "clipboard_html",
    "content_hash",
    "kit_is_expired",
    "persist_kit",
    "public_kit_path",
    "render_html",
    "render_plain",
    "sanitize_for_dzen_editor",
]
