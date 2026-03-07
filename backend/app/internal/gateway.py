from fastapi import APIRouter

router = APIRouter(prefix='/internal/v1/gateway', tags=['gateway-internal'])

@router.post('/auth-resolve')
async def auth_resolve(payload: dict):
    username = payload.get('username')
    password = payload.get('password')
    if username and username == password:
        return {"ok": True, "account": {"id": 1, "username": username, "account_type": 'all' if username == 'all' else 'country', "country_code": None if username == 'all' else username}, "strategy_variant": 'A', "sticky_policy": True}
    return {"ok": False}

@router.post('/session/open')
async def session_open(payload: dict):
    return {"session_id": payload.get('session_id', 'generated-session'), "assigned_proxy": None, "strategy_variant": 'A'}

@router.post('/connection/open')
async def connection_open(payload: dict):
    return {"connection_id": 'generated-connection', "proxy": None}

@router.post('/connection/close')
async def connection_close(payload: dict):
    return {"ok": True}

@router.post('/session/update-traffic')
async def update_traffic(payload: dict):
    return {"ok": True}

@router.post('/session/close')
async def session_close(payload: dict):
    return {"ok": True}

@router.get('/session/{session_id}/state')
async def session_state(session_id: str):
    return {"session_id": session_id, "status": 'active', "kill_requested": False, "assigned_proxy_id": None}
