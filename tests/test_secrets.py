"""Encrypted credential storage and log redaction."""

from __future__ import annotations

import os
import stat

import pytest

from app.errors import ConfigurationError
from app.security.names import SECRET_NAMES
from app.security.redaction import MASK, redact, redaction_processor
from app.security.secrets import SecretStore

# Built at runtime rather than written out, so these fixtures cannot be mistaken for
# real credentials by a secret scanner.
OPENAI_KEY = "sk-" + "proj-" + "TESTtestTESTtest" + "1234567890abcdefGHIJKLMN"
TELEGRAM_TOKEN = "1234567890:" + "AAF" + "testTESTtestTESTtestTESTtestTE"


@pytest.fixture()
def store(tmp_path) -> SecretStore:
    return SecretStore(tmp_path / "secrets.enc", key_path=tmp_path / "master.key")


# --------------------------------------------------------------------- store
def test_value_is_not_readable_on_disk(store: SecretStore):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    blob = store.path.read_bytes()
    assert OPENAI_KEY.encode() not in blob
    assert b"OPENAI_API_KEY" not in blob
    assert store.get("OPENAI_API_KEY") == OPENAI_KEY


def test_store_and_key_are_owner_only(store: SecretStore):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    for path in (store.path, store.key_path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_different_key_cannot_decrypt(store: SecretStore, tmp_path):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    intruder = SecretStore(store.path, master_key=SecretStore.generate_key())
    with pytest.raises(ConfigurationError, match="does not match"):
        intruder.get("OPENAI_API_KEY")


def test_unknown_names_are_refused(store: SecretStore):
    with pytest.raises(ConfigurationError, match="not a known secret"):
        store.set("SOME_RANDOM_SETTING", "x")


def test_empty_values_are_refused(store: SecretStore):
    with pytest.raises(ConfigurationError, match="empty value"):
        store.set("OPENAI_API_KEY", "   ")


def test_delete_removes_the_entry(store: SecretStore):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    assert store.delete("OPENAI_API_KEY") is True
    assert store.get("OPENAI_API_KEY") is None
    assert store.delete("OPENAI_API_KEY") is False


def test_names_are_listed_without_values(store: SecretStore):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    store.set("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN)
    assert store.names() == ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"]


def test_key_rotation_keeps_the_values_readable(store: SecretStore):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    old_key = store.key_path.read_text()

    new_key = store.rotate_key()

    assert new_key != old_key
    assert store.get("OPENAI_API_KEY") == OPENAI_KEY
    stale = SecretStore(store.path, master_key=old_key)
    with pytest.raises(ConfigurationError):
        stale.get("OPENAI_API_KEY")


def test_import_moves_credentials_out_of_a_plaintext_env(store: SecretStore, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "# comment",
                "APP_ENV=production",
                f"OPENAI_API_KEY={OPENAI_KEY}",
                f'TELEGRAM_BOT_TOKEN="{TELEGRAM_TOKEN}"',
                "LOG_LEVEL=INFO",
                "",
            ]
        ),
        encoding="utf-8",
    )

    imported = store.import_env_file(env)

    assert sorted(imported) == ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"]
    assert store.get("TELEGRAM_BOT_TOKEN") == TELEGRAM_TOKEN
    # Ordinary settings are left alone.
    assert store.get("APP_ENV") is None


def test_load_into_env_does_not_override_the_environment(store: SecretStore, monkeypatch):
    store.set("OPENAI_API_KEY", OPENAI_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "set-by-the-orchestrator")

    store.load_into_env()

    assert os.environ["OPENAI_API_KEY"] == "set-by-the-orchestrator"


def test_load_into_env_fills_missing_values(store: SecretStore, monkeypatch):
    store.set("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    loaded = store.load_into_env()

    assert loaded == ["TELEGRAM_BOT_TOKEN"]
    assert os.environ["TELEGRAM_BOT_TOKEN"] == TELEGRAM_TOKEN


def test_missing_store_is_not_an_error(tmp_path):
    store = SecretStore(tmp_path / "absent.enc", key_path=tmp_path / "k")
    assert store.exists() is False
    assert store.load_into_env() == []


# ------------------------------------------------------------------ redaction
def test_registered_values_are_masked(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    assert OPENAI_KEY not in redact(f"request failed with key {OPENAI_KEY}")


def test_unregistered_credentials_are_masked_by_shape():
    # Assembled at runtime so the literals do not trip secret scanners in this repo —
    # which is itself a reminder of why the redactor matches on shape.
    slack = "xoxb-" + "1" * 10 + "-" + "abcdefghijklmnop"
    openai = "sk-" + "abcdefghijklmnopqrstuvwxyz012345"
    telegram = "987654321:AAH" + "qwertyuiopasdfghjklzxcvbnm1234"

    assert redact(f"token={slack}") == f"token={MASK}"
    assert redact(f"Authorization: Bearer {openai}") == f"Authorization: Bearer {MASK}"
    assert MASK in redact(f"bot {telegram}")


def test_private_keys_are_masked():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\ndef\n-----END OPENSSH PRIVATE KEY-----"
    assert redact(f"key: {pem}") == f"key: {MASK}"


def test_ordinary_text_is_untouched():
    text = "published article 42 to @wegotrip_ru in 1200 ms"
    assert redact(text) == text


def test_processor_masks_nested_structures(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN)
    event = {
        "event": "telegram.call",
        "url": f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendRichMessage",
        "context": {"headers": [f"Bearer {OPENAI_KEY}"]},
        "duration_ms": 12,
    }

    cleaned = redaction_processor(None, "info", event)

    rendered = str(cleaned)
    assert TELEGRAM_TOKEN not in rendered
    assert OPENAI_KEY not in rendered
    assert cleaned["duration_ms"] == 12


def test_secret_names_cover_every_credential_setting():
    from app.config import Settings

    fields = set(Settings.model_fields)
    for name in SECRET_NAMES:
        lowered = name.lower()
        # POSTGRES_PASSWORD and DIGITALOCEAN_ACCESS_TOKEN belong to deployment, not
        # to the application settings model.
        if lowered in {"postgres_password", "digitalocean_access_token"}:
            continue
        assert lowered in fields, f"{name} is not a setting"
