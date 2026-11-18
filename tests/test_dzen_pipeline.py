from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.db.enums import DzenArticleStatus
from app.db.models import DzenArticle, DzenPublishingKit
from app.dzen.kit import FORBIDDEN_COPY_MARKERS, clipboard_html
from app.dzen.pipeline import generate_dzen_article
from app.dzen.planner import plan_dzen_week
from app.dzen.schemas import DzenArticleAST
from app.scheduler import jobs


def test_planner_creates_independent_slots(synced_session, settings):
    created = plan_dzen_week(synced_session, settings=settings, run_date=dt.date(2026, 11, 18))
    assert created
    countries = {row.destination_country for row in created if row.destination_country}
    for row in created:
        assert row.status == DzenArticleStatus.TOPIC_CANDIDATE.value
        assert row.format.startswith("dzen_")
        assert row.planned_date is not None
        assert row.planned_date.weekday() in {1, 3}  # TU/TH
    assert countries
    assert countries != {"RU"}


def test_generate_builds_kit_with_coupon_and_images(
    synced_session, settings, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    plan_dzen_week(synced_session, settings=settings, run_date=dt.date(2026, 11, 18))
    article = synced_session.scalars(select(DzenArticle)).first()
    report = generate_dzen_article(synced_session, article, settings=settings)
    assert report.ok, report.issues
    assert article.status == DzenArticleStatus.READY_FOR_HANDOFF.value
    kit = synced_session.scalars(select(DzenPublishingKit)).one()
    assert kit.cover_url and kit.cover_url.startswith("https://")
    assert "coupon=" not in kit.cover_url
    assert kit.html_body
    assert "{{" not in kit.html_body
    for marker in ("{{product_id}}", "media_asset_id"):
        assert marker not in kit.html_body
    for product in kit.product_links_json or []:
        assert product["url"].count("coupon=435") == 1
        assert "utm_source=dzen" in product["url"]
        assert product["url"] in kit.html_body or product["url"] in kit.plain_body
    if kit.zip_asset_path:
        path = Path(kit.zip_asset_path)
        assert path.is_file()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            assert "media_manifest.txt" in names
            assert any(name.startswith("00_cover") for name in names)


def test_jobs_do_not_touch_telegram_tables(synced_session, settings):
    from app.db.models import Article

    before = synced_session.scalars(select(Article)).all()
    jobs.run_dzen_planner(synced_session, settings=settings)
    jobs.generate_dzen_articles(synced_session, settings=settings, max_articles=1)
    after = synced_session.scalars(select(Article)).all()
    assert len(after) == len(before)


def test_clipboard_html_has_only_basic_tags():
    ast = DzenArticleAST(
        headline="Заголовок для Дзена про маршрут",
        lead="x" * 220,
        format="dzen_city_guide",
        pillar="city_guides",
        audience="russian_speaking_global",
        blocks=[],
        practical_takeaway="проверьте часы на сайте",
    )
    html = clipboard_html(ast, [])
    assert "<h2>" in html
    assert "<script" not in html
    for marker in FORBIDDEN_COPY_MARKERS:
        if marker in {"product_id", "media_asset_id"}:
            continue
        assert marker not in html


def ready_article(session, settings):
    candidate = session.scalar(
        select(DzenArticle)
        .where(DzenArticle.status == DzenArticleStatus.TOPIC_CANDIDATE.value)
        .order_by(DzenArticle.id)
    )
    if candidate is None:
        plan_dzen_week(session, settings=settings, run_date=dt.date(2026, 11, 18))
        candidate = session.scalar(
            select(DzenArticle)
            .where(DzenArticle.status == DzenArticleStatus.TOPIC_CANDIDATE.value)
            .order_by(DzenArticle.id)
        )
    assert candidate is not None
    report = generate_dzen_article(session, candidate, settings=settings)
    assert report.ok, report.issues
    kit = session.scalars(
        select(DzenPublishingKit).where(DzenPublishingKit.article_id == candidate.id)
    ).one()
    return candidate, kit
