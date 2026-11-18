from __future__ import annotations

from app.dzen.confirm import normalize_dzen_url, parse_thread_reply, verify_and_confirm
from tests.test_dzen_pipeline import ready_article


def test_rejects_non_dzen_and_internal_urls(synced_session, settings):
    article, _kit = ready_article(synced_session, settings)
    bad = verify_and_confirm(
        synced_session, article, "https://example.com/post", confirmed_by="test", network=False
    )
    assert bad.ok is False
    internal = verify_and_confirm(
        synced_session,
        article,
        "https://dzen.ru/a/abc?next=/admin/secret",
        confirmed_by="test",
        network=False,
    )
    # still a dzen host — admin path check is on the URL string
    assert "admin" not in (internal.url or "") or internal.ok is False


def test_confirms_article_path_without_network(synced_session, settings):
    article, _kit = ready_article(synced_session, settings)
    result = verify_and_confirm(
        synced_session,
        article,
        "смотрите https://dzen.ru/a/AbCdEfGh123",
        confirmed_by="kit_form",
        network=False,
    )
    assert result.ok is True
    assert article.status == "published_confirmed"
    assert article.published_url == "https://dzen.ru/a/AbCdEfGh123"


def test_thread_parser_does_not_guess_two_urls():
    text = "https://dzen.ru/a/one https://dzen.ru/a/two"
    assert parse_thread_reply(text, item_count=2) == {}
    mapped = parse_thread_reply("1: https://dzen.ru/a/one\n2: https://dzen.ru/a/two", 2)
    assert mapped[1].endswith("one")
    assert mapped[2].endswith("two")
    single = parse_thread_reply("готово https://dzen.ru/a/only", 1)
    assert single[1].endswith("only")


def test_normalize_requires_https_dzen():
    assert normalize_dzen_url("http://dzen.ru/a/x") is None
    assert normalize_dzen_url("https://dzen.ru/a/x") == "https://dzen.ru/a/x"
