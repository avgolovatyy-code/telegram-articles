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
        "DEPLOY_SSH_PRIVATE_KEY",
    }
)

#: Dashboard / Cursor names that map onto the canonical setting. The owner already
#: stored Slack as ``*_TG`` and the droplet key as ``DEPLOY_SSH_KEY`` (shared with
#: the video-generation repo).
SECRET_ALIASES: dict[str, str] = {
    "SLACK_BOT_TOKEN_TG": "SLACK_BOT_TOKEN",
    "SLACK_SIGNING_SECRET_TG": "SLACK_SIGNING_SECRET",
    "DEPLOY_SSH_KEY": "DEPLOY_SSH_PRIVATE_KEY",
    "DROPLET_SSH_PRIVATE_KEY": "DEPLOY_SSH_PRIVATE_KEY",
}

#: Canonical names plus aliases — anything that must be stored encrypted and masked.
SECRET_INPUT_NAMES: frozenset[str] = SECRET_NAMES | frozenset(SECRET_ALIASES)


def canonical_secret_name(name: str) -> str:
    key = name.upper()
    return SECRET_ALIASES.get(key, key)


__all__ = [
    "SECRET_ALIASES",
    "SECRET_INPUT_NAMES",
    "SECRET_NAMES",
    "canonical_secret_name",
]
