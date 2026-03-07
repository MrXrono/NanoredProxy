from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.redis import EVENT_CHANNEL, redis_publish_json


def publish_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    event = {
        'type': event_type,
        'payload': payload or {},
        'ts': datetime.now(timezone.utc).isoformat(),
    }
    redis_publish_json(EVENT_CHANNEL, event)
