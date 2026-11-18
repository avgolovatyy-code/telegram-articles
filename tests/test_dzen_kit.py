from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import ROBOTS_TAG, ROBOTS_TXT, create_app
from tests.test_dzen_pipeline import ready_article

HOWTO = "Это не страница Дзена и не публикация"


def _client(session) -> TestClient:
    from app.db.base import get_db

    app = create_app()

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_token_kit_page_and_exports(synced_session, settings):
    article, kit = ready_article(synced_session, settings)
    client = _client(synced_session)
    page = client.get(f"/dzen/k/{kit.access_token}")
    assert page.status_code == 200
    body = page.text
    assert article.headline in body
    assert "Скопировать форматированный текст" in body
    assert "Скопировать заголовок" in body
    assert "{{" not in body
    assert kit.access_token in body or "dzen-kit" in body
    html = client.get(f"/dzen/k/{kit.access_token}/article.html")
    assert html.status_code == 200
    assert "<h2>" in html.text
    txt = client.get(f"/dzen/k/{kit.access_token}/article.txt")
    assert txt.status_code == 200
    assert article.headline.split()[0] in txt.text


def test_kit_howto_is_before_article_and_not_in_clipboard(synced_session, settings):
    _article, kit = ready_article(synced_session, settings)
    client = _client(synced_session)
    page = client.get(f"/dzen/k/{kit.access_token}")
    body = page.text
    assert HOWTO in body
    assert 'class="dzen-howto"' in body
    assert body.index("dzen-howto") < body.index('id="dzen-preview"')
    assert 'id="dzen-select-preview"' in body
    assert "Студия → Создать публикацию → Статья" in body
    assert 'name="robots" content="noindex, nofollow, noarchive, nosnippet"' in body
    assert 'name="referrer" content="no-referrer"' in body
    assert page.headers["x-robots-tag"] == ROBOTS_TAG
    assert page.headers["referrer-policy"] == "no-referrer"

    html = client.get(f"/dzen/k/{kit.access_token}/article.html")
    txt = client.get(f"/dzen/k/{kit.access_token}/article.txt")
    assert HOWTO not in html.text
    assert HOWTO not in txt.text
    assert "dzen-howto" not in html.text
    assert "Служебный пакет" not in html.text
    assert html.headers["x-robots-tag"] == ROBOTS_TAG
    assert "<!--StartFragment-->" in kit.html_body
    assert HOWTO not in kit.html_body
    assert HOWTO not in (kit.plain_body or "")


def test_site_is_not_indexable():
    client = TestClient(create_app())
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert robots.text == ROBOTS_TXT
    assert "Disallow: /" in robots.text
    assert robots.headers["x-robots-tag"] == ROBOTS_TAG
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.headers["x-robots-tag"] == ROBOTS_TAG
    assert health.headers["referrer-policy"] == "no-referrer"


def test_caddy_blocks_indexing():
    text = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    assert 'X-Robots-Tag "noindex, nofollow, noarchive, nosnippet"' in text
    assert 'Referrer-Policy "no-referrer"' in text


def test_expired_token_is_gone(synced_session, settings):
    import datetime as dt

    from app.db.types import utcnow

    _article, kit = ready_article(synced_session, settings)
    kit.expires_at = utcnow() - dt.timedelta(days=1)
    synced_session.flush()
    client = _client(synced_session)
    response = client.get(f"/dzen/k/{kit.access_token}")
    assert response.status_code == 410
