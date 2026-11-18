"""WeGoTrip-only media for Dzen: validate, stage, ZIP. No generated images."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import City, Product, ProductMedia
from app.dzen.links import image_url_is_clean
from app.dzen.products import fold_place, place_tokens
from app.telegram.media import MediaValidator

SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
PRODUCT_DIR = re.compile(r"/product/(\d+)/", re.I)
CACHE_DIR = re.compile(r"/cache/images/", re.I)


@dataclass(slots=True)
class DzenMediaAsset:
    asset_id: str
    url: str
    role: str  # cover | inline
    caption: str
    after_heading: str | None = None
    source_entity: str | None = None
    content_type: str | None = None
    sha256: str | None = None
    fingerprint: str | None = None
    bytes_blob: bytes | None = field(default=None, repr=False)


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = SAFE_NAME.sub("_", name).strip("._") or fallback
    if not cleaned.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        cleaned += ".jpg"
    return cleaned[:80]


def image_fingerprint(url: str) -> str:
    """Collapse CDN CACHE variants and hashed suffixes of the same catalog photo."""
    path = urlsplit(url or "").path.lower()
    path = CACHE_DIR.sub("/", path)
    path = re.sub(r"/[a-f0-9]{32}(\.[a-z]+)$", r"\1", path)
    stem = Path(path).stem
    stem = re.sub(r"(_sm|_small|_thumb|_preview)$", "", stem)
    product_id = ""
    match = PRODUCT_DIR.search(path)
    if match:
        product_id = match.group(1)
    return f"{product_id}:{stem}" if product_id or stem else path


def _candidate_urls(product: Product) -> list[str]:
    urls: list[str] = []
    for item in (product.cover, product.preview):
        if item:
            urls.append(item)
    for image in product.images or []:
        if isinstance(image, dict):
            for key in ("full", "url", "preview"):
                value = image.get(key)
                if isinstance(value, str) and value:
                    urls.append(value)
        elif isinstance(image, str):
            urls.append(image)
    for media in product.media_items or []:
        if isinstance(media, ProductMedia):
            urls.extend([media.url, media.preview_url or ""])
    # Prefer original files over CACHE thumbs: originals first.
    originals: list[str] = []
    cached: list[str] = []
    for url in urls:
        if not url:
            continue
        (cached if "/CACHE/" in url or "/cache/" in url.lower() else originals).append(url)
    return originals + cached


def _caption_for(product: Product, heading: str | None) -> str:
    if heading:
        return heading
    if product.title:
        return product.title.split(":")[0].strip()[:180]
    return "Фотография из каталога WeGoTrip"


def _heading_score(url: str, product: Product, heading: str | None) -> int:
    if not heading:
        return 0
    tokens = place_tokens(heading)
    hay = place_tokens(product.title, Path(urlsplit(url).path).stem, heading)
    return len(tokens & hay)


def collect_catalog_images(
    session: Session,
    *,
    product_ids: list[str],
    city_name: str | None = None,
    headings: list[str] | None = None,
    limit: int = 5,
) -> list[DzenMediaAsset]:
    assets: list[DzenMediaAsset] = []
    seen_fp: set[str] = set()
    headings = [h for h in (headings or []) if h]
    products = list(
        session.scalars(
            select(Product).where(
                Product.market == "ru", Product.external_id.in_(product_ids or [])
            )
        )
    )
    if not products and city_name:
        folded = city_name.casefold()
        titled = [
            row
            for row in session.scalars(
                select(Product).where(Product.market == "ru", Product.available.is_(True))
            )
            if folded in (row.title or "").casefold()
        ]
        products.extend(titled[:8])
    if city_name and not product_ids:
        folded = fold_place(city_name)
        city_rows = list(session.scalars(select(City).where(City.market == "ru")))
        city_ids = [row.external_id for row in city_rows if folded == fold_place(row.name)]
        extra = list(
            session.scalars(
                select(Product).where(
                    Product.market == "ru",
                    Product.available.is_(True),
                    Product.city_external_id.in_(city_ids or ["__none__"]),
                )
            )
        )
        heading_tokens = place_tokens(*(headings or []), city_name)
        dest_tokens = place_tokens(city_name)
        for product in extra:
            if product in products:
                continue
            title_tokens = place_tokens(product.title)
            distinctive = title_tokens - dest_tokens
            if distinctive and not (distinctive & heading_tokens):
                continue
            products.append(product)

    if city_name:
        dest_ids = {
            row.external_id
            for row in session.scalars(select(City).where(City.market == "ru"))
            if fold_place(row.name) == fold_place(city_name)
        }
        if dest_ids:
            products = [p for p in products if p.city_external_id in dest_ids]

    used_headings: set[int] = set()
    for product in products:
        for url in _candidate_urls(product):
            if not image_url_is_clean(url):
                continue
            if not urlsplit(url).path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            fingerprint = image_fingerprint(url)
            if fingerprint in seen_fp:
                continue
            heading = None
            best = -1
            best_idx = None
            for index, name in enumerate(headings):
                if index in used_headings:
                    continue
                score = _heading_score(url, product, name)
                if score > best:
                    best, heading, best_idx = score, name, index
            if best_idx is not None and best > 0:
                used_headings.add(best_idx)
            seen_fp.add(fingerprint)
            role = "cover" if not assets else "inline"
            assets.append(
                DzenMediaAsset(
                    asset_id=f"api_product_{product.external_id}_{len(assets)}",
                    url=url,
                    role=role,
                    caption=_caption_for(product, heading),
                    after_heading=heading,
                    source_entity=f"product:{product.external_id}",
                    fingerprint=fingerprint,
                )
            )
            if len(assets) >= limit:
                return assets
    return assets


def dedupe_downloaded(assets: list[DzenMediaAsset]) -> list[DzenMediaAsset]:
    """Drop byte-identical and fingerprint-identical photos after download."""
    kept: list[DzenMediaAsset] = []
    seen_hash: set[str] = set()
    seen_fp: set[str] = set()
    for asset in assets:
        fp = asset.fingerprint or image_fingerprint(asset.url)
        if fp in seen_fp:
            continue
        digest = asset.sha256
        if digest and digest in seen_hash:
            continue
        seen_fp.add(fp)
        if digest:
            seen_hash.add(digest)
        kept.append(asset)
    if kept:
        kept[0].role = "cover"
        for extra in kept[1:]:
            extra.role = "inline"
    return kept


def validate_assets(
    assets: list[DzenMediaAsset],
    settings: Settings | None = None,
) -> list[DzenMediaAsset]:
    settings = settings or get_settings()
    validator = MediaValidator(settings)
    kept: list[DzenMediaAsset] = []
    try:
        for asset in assets:
            check = validator.check(asset.url, kind="photo")
            if not check.ok:
                continue
            asset.content_type = check.content_type
            kept.append(asset)
    finally:
        validator.close()
    return kept


def download_asset(asset: DzenMediaAsset, settings: Settings | None = None) -> DzenMediaAsset:
    settings = settings or get_settings()
    if not settings.validate_media_over_network:
        payload = b"\xff\xd8\xff" + asset.url.encode("utf-8")[:200]
        asset.bytes_blob = payload
        asset.sha256 = hashlib.sha256(payload).hexdigest()
        return asset
    import httpx

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(asset.url)
        response.raise_for_status()
        payload = response.content
    if len(payload) < 32:
        raise ValueError(f"image too small: {asset.url}")
    asset.bytes_blob = payload
    asset.sha256 = hashlib.sha256(payload).hexdigest()
    asset.content_type = response.headers.get("content-type", asset.content_type)
    return asset


def build_zip(assets: list[DzenMediaAsset], dest: Path) -> tuple[Path, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        lines = ["WeGoTrip Dzen media manifest", ""]
        for index, asset in enumerate(assets):
            prefix = "00_cover" if asset.role == "cover" or index == 0 else f"{index:02d}_inline"
            filename = _safe_filename(prefix, f"{index:02d}.jpg")
            payload = asset.bytes_blob or asset.url.encode("utf-8")
            archive.writestr(filename, payload)
            where = asset.after_heading or (
                "обложка" if index == 0 else "после соответствующего раздела"
            )
            lines.append(f"{filename}\t{where}\t{asset.url}\t{asset.caption}")
        archive.writestr("media_manifest.txt", "\n".join(lines) + "\n")
    payload = buffer.getvalue()
    dest.write_bytes(payload)
    return dest, hashlib.sha256(payload).hexdigest()


def staging_dir(public_id: str) -> Path:
    return Path("var") / "dzen" / public_id


__all__ = [
    "DzenMediaAsset",
    "build_zip",
    "collect_catalog_images",
    "dedupe_downloaded",
    "download_asset",
    "image_fingerprint",
    "staging_dir",
    "validate_assets",
]
