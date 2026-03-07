from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Account, Proxy, Session as SessionModel, SessionConnection
from app.services.routing_service import close_connection, close_session, ensure_connection_proxy, open_connection, open_session, update_traffic

router = APIRouter(prefix='/internal/v1/gateway', tags=['gateway-internal'])


def _proxy_payload(proxy: Proxy | None):
    if not proxy:
        return None
    return {
        'id': proxy.id,
        'host': str(proxy.host),
        'port': proxy.port,
        'auth_username': proxy.auth_username,
        'auth_password': proxy.auth_password,
    }


@router.post('/auth-resolve')
async def auth_resolve(payload: dict, db: Session = Depends(get_db)):
    username = payload.get('username')
    password = payload.get('password')
    account = db.scalar(select(Account).where(Account.username == username, Account.password == password, Account.is_enabled.is_(True)))
    if not account:
        return {'ok': False}
    return {'ok': True, 'account': {'id': account.id, 'username': account.username, 'account_type': account.account_type, 'country_code': account.country_code}, 'strategy_variant': 'A', 'sticky_policy': True}


@router.post('/session/open')
async def session_open(payload: dict, db: Session = Depends(get_db)):
    account = db.get(Account, payload.get('account_id'))
    if not account:
        return {'ok': False}
    session = open_session(db, account, payload.get('client_ip', '0.0.0.0'), payload.get('client_login', account.username))
    proxy = db.get(Proxy, session.assigned_proxy_id) if session.assigned_proxy_id else None
    return {'session_id': str(session.id), 'assigned_proxy': _proxy_payload(proxy), 'strategy_variant': session.strategy_variant}


@router.post('/connection/open')
async def connection_open(payload: dict, db: Session = Depends(get_db)):
    session = db.get(SessionModel, payload.get('session_id'))
    if not session:
        return {'ok': False}
    conn = open_connection(db, session, payload.get('target_host', 'unknown'), int(payload.get('target_port', 0)))
    proxy = db.get(Proxy, conn.proxy_id) if conn.proxy_id else ensure_connection_proxy(db, session)
    return {'connection_id': str(conn.id), 'proxy': _proxy_payload(proxy)}


@router.post('/connection/close')
async def connection_close(payload: dict, db: Session = Depends(get_db)):
    conn = db.get(SessionConnection, payload.get('connection_id'))
    if not conn:
        return {'ok': False}
    close_connection(db, conn, int(payload.get('bytes_in', 0)), int(payload.get('bytes_out', 0)), payload.get('state', 'closed'), payload.get('close_reason'))
    return {'ok': True}


@router.post('/session/update-traffic')
async def update_traffic_endpoint(payload: dict, db: Session = Depends(get_db)):
    update_traffic(db, payload.get('session_id'), payload.get('connection_id'), int(payload.get('bytes_in_delta', 0)), int(payload.get('bytes_out_delta', 0)))
    return {'ok': True}


@router.post('/session/close')
async def session_close(payload: dict, db: Session = Depends(get_db)):
    session = db.get(SessionModel, payload.get('session_id'))
    if not session:
        return {'ok': False}
    close_session(db, session, payload.get('status', 'closed'))
    return {'ok': True}


@router.get('/session/{session_id}/state')
async def session_state(session_id: str, db: Session = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if not session:
        return {'session_id': session_id, 'status': 'error', 'kill_requested': True, 'assigned_proxy_id': None}
    return {'session_id': str(session.id), 'status': session.status, 'kill_requested': session.status == 'killed', 'assigned_proxy_id': session.assigned_proxy_id}
