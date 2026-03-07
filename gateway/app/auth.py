import asyncio

import httpx

from app.config import BACKEND_URL, HTTP_TIMEOUT, HTTP_RETRIES, INTERNAL_API_KEY


async def _request(method: str, path: str, json: dict | None = None):
    last_exc = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.request(method, f'{BACKEND_URL}{path}', json=json, headers={'X-Internal-Api-Key': INTERNAL_API_KEY})
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt >= HTTP_RETRIES:
                raise
            await asyncio.sleep(0.25 * attempt)
    raise last_exc


async def resolve_auth(username: str, password: str, client_ip: str):
    return await _request('POST', '/internal/v1/gateway/auth-resolve', {'username': username, 'password': password, 'client_ip': client_ip})


async def open_session(account_id: int, client_ip: str, client_login: str):
    return await _request('POST', '/internal/v1/gateway/session/open', {'account_id': account_id, 'client_ip': client_ip, 'client_login': client_login})


async def open_connection(session_id: str, target_host: str, target_port: int):
    return await _request('POST', '/internal/v1/gateway/connection/open', {'session_id': session_id, 'target_host': target_host, 'target_port': target_port})


async def close_connection(connection_id: str, bytes_in: int, bytes_out: int, state: str = 'closed', close_reason: str | None = None):
    return await _request('POST', '/internal/v1/gateway/connection/close', {'connection_id': connection_id, 'bytes_in': bytes_in, 'bytes_out': bytes_out, 'state': state, 'close_reason': close_reason})


async def update_traffic(session_id: str, connection_id: str, bytes_in_delta: int, bytes_out_delta: int):
    return await _request('POST', '/internal/v1/gateway/session/update-traffic', {'session_id': session_id, 'connection_id': connection_id, 'bytes_in_delta': bytes_in_delta, 'bytes_out_delta': bytes_out_delta})


async def close_session(session_id: str, status: str = 'closed'):
    return await _request('POST', '/internal/v1/gateway/session/close', {'session_id': session_id, 'status': status})


async def session_state(session_id: str):
    return await _request('GET', f'/internal/v1/gateway/session/{session_id}/state')
