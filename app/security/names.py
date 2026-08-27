"""The list of settings treated as credentials.

A leaf module with no imports: both the encrypted store and the log redactor need it,
and logging must not end up depending on the store.
"""

from __future__ import annotations

#: Only these names are accepted into the encrypted store and masked in logs, so a
#: typo cannot silently shadow an ordinary setting.
SECRET_NAMES: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "WEGOTRIP_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET",
        "ADMIN_PASSWORD",
        "DATABASE_URL",
        "POSTGRES_PASSWORD",
        "DIGITALOCEAN_ACCESS_TOKEN",
    }
)

__all__ = ["SECRET_NAMES"]
