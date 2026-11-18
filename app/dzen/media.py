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
from app.db.models import Product, ProductMedia
from app.dzen.links import image_url_is_clean
from app.telegram.media import MediaValidator

SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


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
    bytes_blob: bytes | None = field(default=None, repr=False)


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = SAFE_NAME.sub("_", name).strip("._") or fallback
    if not cleaned.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        cleaned += ".jpg"
    return cleaned[:80]


def collect_catalog_images(
    session: Session,
    *,
    product_ids: list[str],
    city_name: str | None = None,
    limit: int = 5,
) -> list[DzenMediaAsset]:
    assets: list[DzenMediaAsset] = []
    seen: set[str] = set()
    products = list(
        session.scalars(
            select(Product).where(Product.market == "ru", Product.external_id.in_(product_ids))
        )
    )
    if not products:
        products = list(
            session.scalars(
                select(Product).where(Product.market == "ru", Product.available.is_(True)).limit(12)
            )
        )
        if city_name:
            folded = city_name.casefold()
            products = [p for p in products if folded in (p.title or "").casefold()] or products
    for product in products:
        candidates = [product.cover, product.preview]
        for item in product.images or []:
            if isinstance(item, dict):
                candidates.extend([item.get("full"), item.get("preview"), item.get("url")])
            elif isinstance(item, str):
                candidates.append(item)
        for media in product.media_items or []:
            if isinstance(media, ProductMedia):
                candidates.extend([media.url, media.preview_url])
        for url in candidates:
            if not url or url in seen or not image_url_is_clean(url):
                continue
            if not urlsplit(url).path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            seen.add(url)
            role = "cover" if not assets else "inline"
            assets.append(
                DzenMediaAsset(
                    asset_id=f"api_product_{product.external_id}_{len(assets)}",
                    url=url,
                    role=role,
                    caption="Фотография из каталога WeGoTrip",
                    source_entity=f"product:{product.external_id}",
                )
            )
            if len(assets) >= limit:
                return assets
    return assets


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
    "download_asset",
    "staging_dir",
    "validate_assets",
]
