"""Fact research and verification.

Verification runs on the cheap utility model with the Responses API web-search tool and
is only invoked for claims that genuinely need it (spec §48.6). Results are cached in
``verified_fact_cache`` so an evergreen fact is paid for once.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts import FACT_RESEARCH
from app.ai.router import LLMGateway
from app.config import Market, Settings, get_settings
from app.db.enums import ClaimStatus, LLMTask
from app.db.models import VerifiedFactCache
from app.db.types import utcnow
from app.errors import LLMError
from app.generation.claims import DetectedClaim
from app.generation.schemas import FACT_VERIFICATION_JSON_SCHEMA
from app.logging_setup import get_logger

log = get_logger("generation.research")

#: Source tiers (spec §14). Lower is better.
TIER_OFFICIAL_VENUE = 1
TIER_TOURISM_BOARD = 2
TIER_TRANSPORT_OPERATOR = 3
TIER_PRIMARY = 4
TIER_SECONDARY = 5
TIER_UNTRUSTED = 9

_OFFICIAL_HINTS = ("museum", "musee", "louvre", "palace", "official", "gov", "gouv", "ru/museum")
_GOVERNMENT_TLDS = (".gov", ".gov.uk", ".gouv.fr", ".gob.es", ".gov.it", ".mos.ru", ".gov.tr")
_TOURISM_HINTS = ("tourism", "visit", "turismo", "tourisme", "travel.")
_TRANSPORT_HINTS = ("metro", "transport", "ratp", "tfl", "mosmetro", "railway", "sncf")
_UNTRUSTED_HINTS = (
    "tripadvisor.",
    "pinterest.",
    "medium.com",
    "blogspot.",
    "wordpress.com",
    "reddit.com",
    "quora.com",
)

#: How long a verified fact may be reused before it must be re-checked.
_TTL_BY_CATEGORY: dict[str, dt.timedelta] = {
    "opening_hours": dt.timedelta(days=7),
    "closing_days": dt.timedelta(days=14),
    "ticket_price": dt.timedelta(days=7),
    "current_exhibition": dt.timedelta(days=3),
    "temporary_restriction": dt.timedelta(days=3),
    "schedule": dt.timedelta(days=7),
    "transport": dt.timedelta(days=14),
    "historical": dt.timedelta(days=365),
}
_DEFAULT_TTL = dt.timedelta(days=30)


def classify_source(url: str | None) -> int:
    if not url:
        return TIER_UNTRUSTED
    host = urlsplit(url).netloc.lower()
    if any(hint in host for hint in _UNTRUSTED_HINTS):
        return TIER_UNTRUSTED
    if any(host.endswith(tld) or tld in host for tld in _GOVERNMENT_TLDS):
        return TIER_TOURISM_BOARD
    if any(hint in host for hint in _OFFICIAL_HINTS):
        return TIER_OFFICIAL_VENUE
    if any(hint in host for hint in _TOURISM_HINTS):
        return TIER_TOURISM_BOARD
    if any(hint in host for hint in _TRANSPORT_HINTS):
        return TIER_TRANSPORT_OPERATOR
    return TIER_SECONDARY


#: The weakest source tier accepted for a critical claim.
MAX_ACCEPTED_TIER = TIER_SECONDARY


@dataclass(slots=True)
class VerificationResult:
    claim: str
    status: ClaimStatus
    source_url: str | None = None
    source_title: str | None = None
    source_tier: int = TIER_UNTRUSTED
    confidence: float = 0.0
    corrected_statement: str | None = None
    from_cache: bool = False

    @property
    def is_verified(self) -> bool:
        return self.status == ClaimStatus.VERIFIED


def fact_key(claim: str, entity_name: str) -> str:
    digest = hashlib.sha256(f"{entity_name}|{claim}".lower().encode("utf-8")).hexdigest()
    return digest[:48]


class FactResearchService:
    def __init__(
        self,
        session: Session,
        gateway: LLMGateway,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self.settings = settings or get_settings()

    def verify(
        self,
        claims: list[DetectedClaim],
        *,
        market: Market,
        entity_name: str,
        article_id: int | None = None,
        job_id: str | None = None,
    ) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        pending: list[DetectedClaim] = []

        for claim in claims:
            cached = self._from_cache(market, claim, entity_name)
            if cached is not None:
                results.append(cached)
            else:
                pending.append(claim)

        if not pending:
            return results

        payload = json.dumps(
            {
                "market": market,
                "entity": entity_name,
                "claims": [
                    {"claim": claim.text, "category": str(claim.category)} for claim in pending
                ],
            },
            ensure_ascii=False,
        )

        try:
            outcome = self.gateway.run(
                task=LLMTask.FACT_RESEARCH,
                prompt=FACT_RESEARCH,
                payload=payload,
                json_schema=FACT_VERIFICATION_JSON_SCHEMA,
                schema_name="fact_verification",
                market=market,
                article_id=article_id,
                job_id=job_id,
                enable_web_search=True,
            )
        except LLMError as exc:
            log.warning("research.failed", error=str(exc), claims=len(pending))
            return results + [
                VerificationResult(claim=claim.text, status=ClaimStatus.UNVERIFIED)
                for claim in pending
            ]

        parsed = outcome.response.parsed or {}
        by_claim = {
            str(item.get("claim", "")).strip().lower(): item
            for item in parsed.get("results", [])
            if isinstance(item, dict)
        }

        for claim in pending:
            item = by_claim.get(claim.text.strip().lower())
            if item is None:
                results.append(VerificationResult(claim=claim.text, status=ClaimStatus.UNVERIFIED))
                continue
            result = self._to_result(claim, item)
            results.append(result)
            self._store_cache(market, claim, entity_name, result)
        return results

    # ---------------------------------------------------------------- helpers
    def _to_result(self, claim: DetectedClaim, item: dict[str, Any]) -> VerificationResult:
        raw_status = str(item.get("status") or "unverified")
        raw_url = item.get("source_url")
        url = raw_url if isinstance(raw_url, str) and raw_url.startswith("http") else None
        tier = classify_source(url)
        raw_confidence = item.get("confidence")
        confidence = float(raw_confidence) if isinstance(raw_confidence, int | float) else 0.0

        if raw_status == "verified" and url and tier <= MAX_ACCEPTED_TIER and confidence >= 0.7:
            status = ClaimStatus.VERIFIED
        elif raw_status == "refuted":
            status = ClaimStatus.REJECTED
        else:
            status = ClaimStatus.UNVERIFIED

        corrected = item.get("corrected_statement")
        title = item.get("source_title")
        return VerificationResult(
            claim=claim.text,
            status=status,
            source_url=url,
            source_title=title if isinstance(title, str) else None,
            source_tier=tier,
            confidence=confidence,
            corrected_statement=corrected if isinstance(corrected, str) else None,
        )

    def _from_cache(
        self, market: Market, claim: DetectedClaim, entity_name: str
    ) -> VerificationResult | None:
        key = fact_key(claim.text, entity_name)
        row = self.session.scalar(
            select(VerifiedFactCache).where(
                VerifiedFactCache.market == market, VerifiedFactCache.fact_key == key
            )
        )
        if row is None:
            return None
        if row.expires_at is not None and row.expires_at < utcnow():
            self.session.delete(row)
            self.session.flush()
            return None
        return VerificationResult(
            claim=claim.text,
            status=ClaimStatus(row.status),
            source_url=row.source_url,
            source_title=row.source_title,
            source_tier=row.source_tier or TIER_UNTRUSTED,
            confidence=row.confidence or 0.0,
            from_cache=True,
        )

    def _store_cache(
        self,
        market: Market,
        claim: DetectedClaim,
        entity_name: str,
        result: VerificationResult,
    ) -> None:
        if result.status != ClaimStatus.VERIFIED:
            return
        ttl = _TTL_BY_CATEGORY.get(str(claim.category), _DEFAULT_TTL)
        key = fact_key(claim.text, entity_name)
        existing = self.session.scalar(
            select(VerifiedFactCache).where(
                VerifiedFactCache.market == market, VerifiedFactCache.fact_key == key
            )
        )
        if existing is None:
            existing = VerifiedFactCache(market=market, fact_key=key, claim=claim.text)
            self.session.add(existing)
        existing.category = str(claim.category)
        existing.claim = claim.text
        existing.status = str(result.status)
        existing.source_url = result.source_url
        existing.source_title = result.source_title
        existing.source_tier = result.source_tier
        existing.confidence = result.confidence
        existing.verified_at = utcnow()
        existing.expires_at = utcnow() + ttl
        self.session.flush()


__all__ = [
    "MAX_ACCEPTED_TIER",
    "TIER_OFFICIAL_VENUE",
    "TIER_SECONDARY",
    "TIER_TOURISM_BOARD",
    "TIER_TRANSPORT_OPERATOR",
    "FactResearchService",
    "VerificationResult",
    "classify_source",
    "fact_key",
]
