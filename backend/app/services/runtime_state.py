from __future__ import annotations

from app.core.redis import redis_delete, redis_get_json, redis_set_json

SESSION_PREFIX = 'session:'
WORKER_PREFIX = 'worker:'
RUNTIME_PREFIX = 'runtime:'


def _session_key(session_id: str, suffix: str) -> str:
    return f'{SESSION_PREFIX}{session_id}:{suffix}'


def request_kill(session_id: str, reason: str | None = None) -> None:
    redis_set_json(_session_key(session_id, 'kill'), {'requested': True, 'reason': reason or 'manual kill'})


def clear_kill(session_id: str) -> None:
    redis_delete(_session_key(session_id, 'kill'))


def is_kill_requested(session_id: str) -> bool:
    state = redis_get_json(_session_key(session_id, 'kill'), {}) or {}
    return bool(state.get('requested'))


def get_kill_reason(session_id: str) -> str | None:
    state = redis_get_json(_session_key(session_id, 'kill'), {}) or {}
    return state.get('reason')


def set_session_runtime(session_id: str, payload: dict) -> None:
    redis_set_json(_session_key(session_id, 'runtime'), payload, ex=60 * 60 * 24)


def get_session_runtime(session_id: str) -> dict:
    return redis_get_json(_session_key(session_id, 'runtime'), {}) or {}


def clear_session_runtime(session_id: str) -> None:
    redis_delete(_session_key(session_id, 'runtime'))


def set_worker_runtime(worker_name: str, status: str, pause_reason: str | None = None) -> None:
    redis_set_json(f'{WORKER_PREFIX}{worker_name}:state', {'status': status, 'pause_reason': pause_reason})


def get_worker_runtime(worker_name: str) -> dict:
    return redis_get_json(f'{WORKER_PREFIX}{worker_name}:state', {}) or {}


def set_active_sessions_count(value: int) -> None:
    redis_set_json(f'{RUNTIME_PREFIX}active_sessions', {'count': max(0, int(value))})


def get_active_sessions_count() -> int:
    state = redis_get_json(f'{RUNTIME_PREFIX}active_sessions', {'count': 0}) or {'count': 0}
    return int(state.get('count', 0))
