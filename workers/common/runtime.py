import json
import os
from datetime import datetime, timezone

from redis import Redis
from redis.exceptions import RedisError

from workers.common.db import get_conn

REDIS_URL = os.getenv('REDIS_URL') or f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/0"
_redis = None


def _client():
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _rget_json(key: str, default=None):
    try:
        raw = _client().get(key)
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _rset_json(key: str, value):
    try:
        _client().set(key, json.dumps(value))
    except RedisError:
        pass


def get_setting(key: str, default=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('select value from system_settings where key=%s', (key,))
        row = cur.fetchone()
        return (row or {}).get('value', default)


def set_worker_state(worker_name: str, status: str, pause_reason: str | None = None):
    _rset_json(f'worker:{worker_name}:state', {'status': status, 'pause_reason': pause_reason})
    with get_conn() as conn, conn.cursor() as cur:
        now = datetime.now(timezone.utc)
        cur.execute(
            """update scheduler_state set status=%s, pause_reason=%s, updated_at=%s,
               last_started_at=case when %s='running' then %s else last_started_at end,
               last_finished_at=case when %s in ('idle','paused','error') then %s else last_finished_at end
               where worker_name=%s""",
            (status, pause_reason, now, status, now, status, now, worker_name),
        )
        conn.commit()


def worker_state(worker_name: str) -> dict:
    return _rget_json(f'worker:{worker_name}:state', {}) or {}


def active_sessions_count() -> int:
    redis_state = _rget_json('runtime:active_sessions', None)
    if redis_state and 'count' in redis_state:
        return int(redis_state['count'])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("select count(*) as c from sessions where status='active'")
        return int(cur.fetchone()['c'])
