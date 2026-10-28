"""Russia travel demand observations (spec 3.0 §7).

Dated baseline from named sources. Weekly refresh re-checks source URLs;
it never invents new percentages or treats organised-tour sales as all trips.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RussiaDemandObservation
from app.db.types import utcnow
from app.logging_setup import get_logger

log = get_logger("editorial.russia_demand")

MetricType = Literal[
    "search_interest",
    "actual_arrivals",
    "organized_tour_sales",
    "hotel_bookings",
    "air_ticket_searches",
    "museum_interest",
    "wegotrip_orders",
    "booking",
    "sale",
    "trip",
    "cultural_attention",
]

TravelType = Literal["domestic", "outbound", "local_leisure", "culture"]


@dataclass(slots=True)
class DemandObservation:
    geo: str
    audience_origin: str
    travel_type: str
    metric_type: str
    segment: str
    value: float | None
    unit: str
    period_start: str
    period_end: str
    published_at: str
    source_url: str
    source_name: str
    sample_context: str
    confidence: float
    valid_until: str
    caveat: str
    status: str = "seeded"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


#: Dated October 2026 baseline. These numbers are a starting ledger, not a prompt constant.
OCTOBER_2026_BASELINE: tuple[DemandObservation, ...] = (
    DemandObservation(
        geo="TR",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals",
        value=34.5,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Доля продаж организованных туров с заездами в октябре 2026",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Организованные туры ≠ весь выездной туризм и ≠ поисковый интерес",
    ),
    DemandObservation(
        geo="EG",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals",
        value=23.0,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Доля продаж организованных туров с заездами в октябре 2026",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Организованные туры ≠ весь выездной туризм и ≠ поисковый интерес",
    ),
    DemandObservation(
        geo="AE",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals",
        value=8.0,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Доля продаж организованных туров с заездами в октябре 2026",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Организованные туры ≠ весь выездной туризм и ≠ поисковый интерес",
    ),
    DemandObservation(
        geo="TH",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals",
        value=7.7,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Доля продаж организованных туров с заездами в октябре 2026",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Организованные туры ≠ весь выездной туризм и ≠ поисковый интерес",
    ),
    DemandObservation(
        geo="VN",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals",
        value=6.4,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Доля продаж организованных туров с заездами в октябре 2026",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Организованные туры ≠ весь выездной туризм и ≠ поисковый интерес",
    ),
    DemandObservation(
        geo="CN",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals",
        value=5.0,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Доля продаж организованных туров с заездами в октябре 2026",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Организованные туры ≠ весь выездной туризм и ≠ поисковый интерес",
    ),
    DemandObservation(
        geo="ASIA_TH_VN_CN",
        audience_origin="RU",
        travel_type="outbound",
        metric_type="organized_tour_sales",
        segment="package_tours_october_arrivals_asia_share",
        value=19.1,
        unit="percent_of_package_tour_sales",
        period_start="2026-10-01",
        period_end="2026-10-31",
        published_at="2026-10-05",
        source_url=(
            "https://www.interfax-russia.ru/tourism/news/"
            "pochti-kazhdyy-pyatyy-tur-na-oktyabr-prodan-v-tailand-vetnam-ili-kitay"
        ),
        source_name="АТОР / Интерфакс",
        sample_context="Таиланд+Вьетнам+Китай ≈ почти пятая часть октябрьских пакетных туров",
        confidence=0.7,
        valid_until="2026-11-15",
        caveat="Рост доли Азии не отменяет Турцию и Египет; сегмент ≠ все поездки",
    ),
    DemandObservation(
        geo="RU",
        audience_origin="RU",
        travel_type="domestic",
        metric_type="hotel_bookings",
        segment="ostrovok_bookings_31oct_8nov_2026",
        value=61.0,
        unit="percent_of_service_bookings",
        period_start="2026-10-31",
        period_end="2026-11-08",
        published_at="2026-10-14",
        source_url=(
            "https://rst.ru/novosti/novosti-turizm/"
            "noyabrskie-poezdki-turisty-vybirayut-korotkij-otdyh-a-spros-na-napravleniyah-menyaetsya-po-raznomu/"
        ),
        source_name="РСТ / Островок",
        sample_context="61% бронирований сервиса на 31 окт — 8 ноя 2026 — российские направления",
        confidence=0.65,
        valid_until="2026-11-20",
        caveat="Бронирования одного сервиса ≠ все поездки россиян",
    ),
    DemandObservation(
        geo="RU",
        audience_origin="RU",
        travel_type="domestic",
        metric_type="hotel_bookings",
        segment="short_domestic_trips_2_3_nights",
        value=None,
        unit="qualitative",
        period_start="2026-10-01",
        period_end="2026-11-08",
        published_at="2026-10-14",
        source_url=(
            "https://rst.ru/novosti/novosti-turizm/"
            "noyabrskie-poezdki-turisty-vybirayut-korotkij-otdyh-a-spros-na-napravleniyah-menyaetsya-po-raznomu/"
        ),
        source_name="РСТ",
        sample_context="Короткие поездки на 2–3 ночи — уместный редакционный сценарий",
        confidence=0.6,
        valid_until="2026-11-20",
        caveat="Качественный сигнал, не доля рынка",
    ),
    DemandObservation(
        geo="RU",
        audience_origin="RU",
        travel_type="domestic",
        metric_type="hotel_bookings",
        segment="regional_heterogeneity_autumn_2026",
        value=None,
        unit="qualitative",
        period_start="2026-09-01",
        period_end="2026-10-20",
        published_at="2026-10-20",
        source_url=(
            "https://rst.ru/novosti/novosti-turizm/"
            "v-rst-rasskazali-kak-broniruyutsya-tury-po-rossii-osenyu-i-chto-proishodit-s-cenami/"
        ),
        source_name="РСТ",
        sample_context="Неоднородная динамика внутреннего туризма по регионам осенью 2026",
        confidence=0.6,
        valid_until="2026-11-20",
        caveat="Не усреднять регионы в один рейтинг без источника",
    ),
)


DISCOVERY_CANDIDATES_OUTBOUND = (
    "TR",
    "EG",
    "CN",
    "TH",
    "VN",
    "AE",
    "AB",
    "GE",
    "AM",
    "UZ",
    "JP",
    "ID",
    "MV",
    "EU",
)

DISCOVERY_CANDIDATES_DOMESTIC = (
    "Санкт-Петербург",
    "Москва",
    "Казань",
    "Золотое кольцо",
    "Нижний Новгород",
    "Калининград",
    "Сочи",
    "Кисловодск",
    "Екатеринбург",
    "Новосибирск",
    "Дальний Восток",
)


class RussiaDemandProvider:
    """Stores sourced observations; never fabricates search volumes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def seed_baseline(self, *, force: bool = False) -> int:
        created = 0
        for item in OCTOBER_2026_BASELINE:
            existing = self.session.scalar(
                select(RussiaDemandObservation).where(
                    RussiaDemandObservation.geo == item.geo,
                    RussiaDemandObservation.metric_type == item.metric_type,
                    RussiaDemandObservation.segment == item.segment,
                    RussiaDemandObservation.period_start
                    == dt.date.fromisoformat(item.period_start),
                )
            )
            if existing is not None and not force:
                continue
            if existing is not None:
                continue
            self.session.add(_to_row(item))
            created += 1
        self.session.flush()
        return created

    def active_observations(self, *, as_of: dt.date | None = None) -> list[dict[str, Any]]:
        as_of = as_of or utcnow().date()
        rows = list(
            self.session.scalars(
                select(RussiaDemandObservation).order_by(
                    RussiaDemandObservation.published_at.desc()
                )
            ).all()
        )
        if not rows:
            self.seed_baseline()
            rows = list(self.session.scalars(select(RussiaDemandObservation)).all())
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = _row_as_dict(row)
            if row.valid_until and row.valid_until < as_of:
                payload["status"] = "stale"
                payload["caveat"] = (
                    f"{payload.get('caveat') or ''} "
                    "Источник старше valid_until; не выдавать как live."
                ).strip()
            out.append(payload)
        return out

    def brief_payload(self, *, as_of: dt.date | None = None) -> dict[str, Any]:
        observations = self.active_observations(as_of=as_of)
        outbound = [row for row in observations if row.get("travel_type") == "outbound"]
        domestic = [row for row in observations if row.get("travel_type") == "domestic"]
        return {
            "as_of": (as_of or utcnow().date()).isoformat(),
            "audience_origin_focus": "Russia",
            "methodology_note": (
                "metric_type различает продажи пакетных туров, бронирования сервиса и "
                "качественный интерес. Нельзя складывать их в один рейтинг стран."
            ),
            "domestic_demand_signals": domestic,
            "outbound_demand_signals": outbound,
            "discovery_candidates_outbound": list(DISCOVERY_CANDIDATES_OUTBOUND),
            "discovery_candidates_domestic": list(DISCOVERY_CANDIDATES_DOMESTIC),
            "missing_live_trends": {
                "google_trends": "UNAVAILABLE",
                "yandex_wordstat": "UNAVAILABLE",
                "reason": "Нет авторизованного коннектора; не выдумывать объёмы поиска",
            },
        }


def _to_row(item: DemandObservation) -> RussiaDemandObservation:
    return RussiaDemandObservation(
        geo=item.geo,
        audience_origin=item.audience_origin,
        travel_type=item.travel_type,
        metric_type=item.metric_type,
        segment=item.segment,
        value=item.value,
        unit=item.unit,
        period_start=dt.date.fromisoformat(item.period_start),
        period_end=dt.date.fromisoformat(item.period_end),
        published_at=dt.date.fromisoformat(item.published_at),
        source_url=item.source_url,
        source_name=item.source_name,
        sample_context=item.sample_context,
        confidence=item.confidence,
        valid_until=dt.date.fromisoformat(item.valid_until),
        caveat=item.caveat,
        status=item.status,
        payload=item.as_dict(),
    )


def _row_as_dict(row: RussiaDemandObservation) -> dict[str, Any]:
    return {
        "id": row.id,
        "geo": row.geo,
        "audience_origin": row.audience_origin,
        "travel_type": row.travel_type,
        "metric_type": row.metric_type,
        "segment": row.segment,
        "value": row.value,
        "unit": row.unit,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "source_url": row.source_url,
        "source_name": row.source_name,
        "sample_context": row.sample_context,
        "confidence": row.confidence,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "caveat": row.caveat,
        "status": row.status,
    }


def refresh_russia_travel_demand(session: Session, *, http_get=None) -> dict[str, Any]:
    """Weekly job: keep last valid observations; mark sources UNAVAILABLE if unreachable."""
    provider = RussiaDemandProvider(session)
    seeded = provider.seed_baseline()
    observations = provider.active_observations()
    source_status: dict[str, str] = {}
    urls = {row["source_url"] for row in observations if row.get("source_url")}
    if http_get is None:
        for url in urls:
            source_status[url] = "UNCHECKED"
    else:
        for url in urls:
            host = urlparse(url).hostname or ""
            try:
                ok = bool(http_get(url))
                source_status[url] = "OK" if ok else "UNAVAILABLE"
            except Exception as exc:
                source_status[url] = f"UNAVAILABLE:{host}:{type(exc).__name__}"
                log.warning("russia_demand.source_unavailable", url=url, error=str(exc)[:200])
    return {
        "seeded": seeded,
        "observations": len(observations),
        "source_status": source_status,
        "invented_trends": False,
    }


__all__ = [
    "DISCOVERY_CANDIDATES_DOMESTIC",
    "DISCOVERY_CANDIDATES_OUTBOUND",
    "OCTOBER_2026_BASELINE",
    "DemandObservation",
    "RussiaDemandProvider",
    "refresh_russia_travel_demand",
]
