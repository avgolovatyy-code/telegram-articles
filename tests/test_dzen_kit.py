from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_dzen_pipeline import ready_article


def test_token_kit_page_and_exports(synced_session, settings):
    article, kit = ready_article(synced_session, settings)
    app = create_app()
    app.dependency_overrides = {}
    # Bind the same session via get_db override.
    from app.db.base import get_db

    def _db():
        yield synced_session

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
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


def test_expired_token_is_gone(synced_session, settings):
    import datetime as dt

    from app.db.types import utcnow

    _article, kit = ready_article(synced_session, settings)
    kit.expires_at = utcnow() - dt.timedelta(days=1)
    synced_session.flush()
    from app.db.base import get_db
    from app.main import create_app

    app = create_app()

    def _db():
        yield synced_session

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    response = client.get(f"/dzen/k/{kit.access_token}")
    assert response.status_code == 410
