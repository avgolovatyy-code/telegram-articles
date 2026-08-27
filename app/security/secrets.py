"""Encrypted secret storage.

Secrets live in ``var/secrets.enc``, encrypted with Fernet (AES-128-CBC + HMAC-SHA256).
The master key is read, in order, from:

1. the ``SECRETS_MASTER_KEY`` environment variable;
2. the key file at ``SECRETS_KEY_FILE`` (default ``var/master.key``, mode 600);
3. a freshly generated key written to that file.

At startup the decrypted values are merged into the process environment, so the rest of
the application keeps reading plain settings and knows nothing about encryption.

**What this protects against and what it does not.** It removes plaintext credentials
from disk, from `.env`, from backups, from `docker inspect` and from anything that
scrapes the filesystem or a copied volume. It does *not* protect against someone who
already has root on the running server: the process must be able to decrypt, so the key
is reachable there by definition. For that threat you need a managed KMS, and the store
below is deliberately shaped so swapping in one later touches only this file.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.errors import ConfigurationError
from app.logging_setup import get_logger
from app.security.names import SECRET_NAMES

log = get_logger("security.secrets")

DEFAULT_STORE_PATH = Path("var/secrets.enc")
DEFAULT_KEY_PATH = Path("var/master.key")

_PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0600


class SecretStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        key_path: Path | None = None,
        master_key: str | None = None,
    ) -> None:
        self.path = Path(path or os.getenv("SECRETS_STORE_FILE") or DEFAULT_STORE_PATH)
        self.key_path = Path(key_path or os.getenv("SECRETS_KEY_FILE") or DEFAULT_KEY_PATH)
        self._explicit_key = master_key or os.getenv("SECRETS_MASTER_KEY")
        self._fernet: Fernet | None = None

    # ------------------------------------------------------------------- keys
    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()

    def _load_key(self) -> str:
        if self._explicit_key:
            return self._explicit_key
        if self.key_path.exists():
            return self.key_path.read_text(encoding="utf-8").strip()
        key = self.generate_key()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.write_text(key, encoding="utf-8")
        self.key_path.chmod(_PRIVATE_FILE_MODE)
        log.info("secrets.key_created", path=str(self.key_path))
        return key

    def _cipher(self) -> Fernet:
        if self._fernet is None:
            try:
                self._fernet = Fernet(self._load_key().encode())
            except (ValueError, TypeError) as exc:
                raise ConfigurationError(
                    "Master key is not a valid Fernet key. Generate one with "
                    "`wgt secrets init` or unset SECRETS_MASTER_KEY."
                ) from exc
        return self._fernet

    @property
    def key_source(self) -> str:
        if self._explicit_key:
            return "SECRETS_MASTER_KEY"
        return str(self.key_path)

    # ------------------------------------------------------------------ store
    def exists(self) -> bool:
        return self.path.exists()

    def _read_all(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        blob = self.path.read_bytes()
        if not blob.strip():
            return {}
        try:
            payload = self._cipher().decrypt(blob)
        except InvalidToken as exc:
            raise ConfigurationError(
                f"Cannot decrypt {self.path}: the master key does not match this store."
            ) from exc
        data = json.loads(payload.decode("utf-8"))
        return {str(k): str(v) for k, v in data.items()}

    def _write_all(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._cipher().encrypt(json.dumps(values, ensure_ascii=False).encode("utf-8"))
        self.path.write_bytes(blob)
        self.path.chmod(_PRIVATE_FILE_MODE)

    # -------------------------------------------------------------------- API
    def names(self) -> list[str]:
        return sorted(self._read_all())

    def get(self, name: str) -> str | None:
        return self._read_all().get(name.upper())

    def set(self, name: str, value: str) -> None:
        key = name.upper()
        if key not in SECRET_NAMES:
            raise ConfigurationError(
                f"{key} is not a known secret. Allowed: {', '.join(sorted(SECRET_NAMES))}"
            )
        if not value.strip():
            raise ConfigurationError(f"Refusing to store an empty value for {key}")
        values = self._read_all()
        values[key] = value.strip()
        self._write_all(values)
        log.info("secrets.stored", name=key)

    def delete(self, name: str) -> bool:
        values = self._read_all()
        removed = values.pop(name.upper(), None) is not None
        if removed:
            self._write_all(values)
            log.info("secrets.deleted", name=name.upper())
        return removed

    def rotate_key(self) -> str:
        """Re-encrypt the store under a brand new master key."""
        values = self._read_all()
        new_key = self.generate_key()
        self._explicit_key = new_key
        self._fernet = None
        self._write_all(values)
        if not os.getenv("SECRETS_MASTER_KEY"):
            self.key_path.write_text(new_key, encoding="utf-8")
            self.key_path.chmod(_PRIVATE_FILE_MODE)
        log.info("secrets.key_rotated", entries=len(values))
        return new_key

    def import_env_file(self, path: Path) -> list[str]:
        """Move credentials out of a plaintext ``.env`` and into the store."""
        imported: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            name = name.strip().upper()
            value = value.strip().strip("'\"")
            if name in SECRET_NAMES and value:
                self.set(name, value)
                imported.append(name)
        return imported

    def load_into_env(self, *, override: bool = False) -> list[str]:
        """Merge decrypted secrets into ``os.environ``.

        Existing environment variables win by default, so a container orchestrator or a
        one-off shell override still takes precedence over the file on disk.
        """
        if not self.exists():
            return []
        loaded: list[str] = []
        for name, value in self._read_all().items():
            if override or not os.environ.get(name):
                os.environ[name] = value
                loaded.append(name)
        return loaded


_loaded = False


def load_secrets_into_env() -> list[str]:
    """Idempotently load the encrypted store; never fatal if it is absent."""
    global _loaded
    if _loaded or os.getenv("SECRETS_DISABLED") == "1":
        return []
    _loaded = True
    try:
        store = SecretStore()
        if not store.exists():
            return []
        names = store.load_into_env()
        if names:
            log.info("secrets.loaded", count=len(names))
        return names
    except ConfigurationError as exc:
        log.error("secrets.load_failed", error=str(exc))
        return []


def reset_loaded_flag() -> None:
    """Test hook."""
    global _loaded
    _loaded = False


__all__ = [
    "DEFAULT_KEY_PATH",
    "DEFAULT_STORE_PATH",
    "SecretStore",
    "load_secrets_into_env",
    "reset_loaded_flag",
]
