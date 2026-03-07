from __future__ import annotations

import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

EVENT_CHANNEL = 'nanoredproxy:events'
_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def redis_get_json(key: str, default: Any = None):
    try:
        raw = get_redis().get(key)
    except RedisError:
        return default
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def redis_set_json(key: str, value: Any, ex: int | None = None) -> bool:
    try:
        get_redis().set(key, json.dumps(value), ex=ex)
        return True
    except RedisError:
        return False


def redis_delete(key: str) -> bool:
    try:
        get_redis().delete(key)
        return True
    except RedisError:
        return False


def redis_publish_json(channel: str, value: Any) -> bool:
    try:
        get_redis().publish(channel, json.dumps(value))
        return True
    except RedisError:
        return False


def redis_pubsub():
    try:
        return get_redis().pubsub(ignore_subscribe_messages=True)
    except RedisError:
        return None
