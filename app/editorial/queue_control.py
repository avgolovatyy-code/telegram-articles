"""Runtime pause for the publication queue (spec §16 / §19.14)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import SystemSetting
from app.db.types import utcnow

PAUSE_KEY = "publication_queue_paused"


def queue_is_paused(session: Session) -> bool:
    row = session.get(SystemSetting, PAUSE_KEY)
    if row is None or not isinstance(row.value, dict):
        return False
    return bool(row.value.get("on"))


def set_queue_paused(session: Session, paused: bool, *, actor: str = "admin") -> None:
    row = session.get(SystemSetting, PAUSE_KEY)
    payload = {"on": bool(paused), "by": actor, "at": utcnow().isoformat()}
    if row is None:
        session.add(SystemSetting(key=PAUSE_KEY, value=payload))
    else:
        row.value = payload
    session.flush()


__all__ = ["PAUSE_KEY", "queue_is_paused", "set_queue_paused"]
