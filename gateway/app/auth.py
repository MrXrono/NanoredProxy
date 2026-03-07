import httpx

from app.config import BACKEND_URL, HTTP_TIMEOUT


async def resolve_auth(username: str, password: str, client_ip: str):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f'{BACKEND_URL}/internal/v1/gateway/auth-resolve', json={'username': username, 'password': password, 'client_ip': client_ip})
        resp.raise_for_status()
        return resp.json()


async def open_session(account_id: int, client_ip: str, client_login: str):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f'{BACKEND_URL}/internal/v1/gateway/session/open', json={'account_id': account_id, 'client_ip': client_ip, 'client_login': client_login})
        resp.raise_for_status()
        return resp.json()


async def open_connection(session_id: str, target_host: str, target_port: int):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f'{BACKEND_URL}/internal/v1/gateway/connection/open', json={'session_id': session_id, 'target_host': target_host, 'target_port': target_port})
        resp.raise_for_status()
        return resp.json()


async def close_connection(connection_id: str, bytes_in: int, bytes_out: int, state: str = 'closed', close_reason: str | None = None):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f'{BACKEND_URL}/internal/v1/gateway/connection/close', json={'connection_id': connection_id, 'bytes_in': bytes_in, 'bytes_out': bytes_out, 'state': state, 'close_reason': close_reason})
        resp.raise_for_status()
        return resp.json()


async def update_traffic(session_id: str, connection_id: str, bytes_in_delta: int, bytes_out_delta: int):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f'{BACKEND_URL}/internal/v1/gateway/session/update-traffic', json={'session_id': session_id, 'connection_id': connection_id, 'bytes_in_delta': bytes_in_delta, 'bytes_out_delta': bytes_out_delta})
        resp.raise_for_status()
        return resp.json()


async def close_session(session_id: str, status: str = 'closed'):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f'{BACKEND_URL}/internal/v1/gateway/session/close', json={'session_id': session_id, 'status': status})
        resp.raise_for_status()
        return resp.json()


async def session_state(session_id: str):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f'{BACKEND_URL}/internal/v1/gateway/session/{session_id}/state')
        resp.raise_for_status()
        return resp.json()
