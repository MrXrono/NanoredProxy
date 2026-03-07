from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.models import RoutingEvent, Session as SessionModel, SessionConnection
from app.schemas.common import OkResponse
from app.schemas.session import SessionKillRequest
from app.services.routing_service import close_session
from app.services.runtime_state import request_kill

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('')
async def list_sessions(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(SessionModel).order_by(SessionModel.started_at.desc())
    if status:
        stmt = stmt.where(SessionModel.status == status)
    items = []
    for s in db.scalars(stmt):
        items.append({'id': str(s.id), 'account_id': s.account_id, 'client_ip': str(s.client_ip), 'client_login': s.client_login, 'assigned_proxy_id': s.assigned_proxy_id, 'sticky_proxy_id': s.sticky_proxy_id, 'strategy_variant': s.strategy_variant, 'status': s.status, 'started_at': s.started_at, 'last_activity_at': s.last_activity_at, 'connections_count': s.connections_count, 'active_connections_count': s.active_connections_count, 'bytes_in': s.bytes_in, 'bytes_out': s.bytes_out, 'total_bytes': s.bytes_in + s.bytes_out, 'avg_speed_total_mbps': float(s.avg_speed_total_mbps) if s.avg_speed_total_mbps is not None else None, 'kill_reason': s.kill_reason})
    return {'items': items, 'total': len(items)}


@router.get('/{session_id}')
async def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')
    return {'id': str(session.id), 'status': session.status, 'account_id': session.account_id, 'assigned_proxy_id': session.assigned_proxy_id, 'sticky_proxy_id': session.sticky_proxy_id, 'bytes_in': session.bytes_in, 'bytes_out': session.bytes_out, 'connections_count': session.connections_count, 'active_connections_count': session.active_connections_count, 'kill_reason': session.kill_reason}


@router.get('/{session_id}/connections')
async def get_session_connections(session_id: str, db: Session = Depends(get_db)):
    items = db.scalars(select(SessionConnection).where(SessionConnection.session_id == session_id).order_by(SessionConnection.started_at.desc())).all()
    return {'items': [{'id': str(x.id), 'proxy_id': x.proxy_id, 'target_host': x.target_host, 'target_port': x.target_port, 'state': x.state, 'bytes_in': x.bytes_in, 'bytes_out': x.bytes_out, 'started_at': x.started_at, 'ended_at': x.ended_at, 'close_reason': x.close_reason} for x in items]}


@router.get('/{session_id}/routing-events')
async def get_session_routing_events(session_id: str, db: Session = Depends(get_db)):
    items = db.scalars(select(RoutingEvent).where(RoutingEvent.session_id == session_id).order_by(RoutingEvent.created_at.desc())).all()
    return {'items': [{'id': x.id, 'old_proxy_id': x.old_proxy_id, 'new_proxy_id': x.new_proxy_id, 'event_type': x.event_type, 'reason': x.reason, 'created_at': x.created_at} for x in items]}


@router.post('/{session_id}/kill', response_model=OkResponse)
async def kill_session(session_id: str, payload: SessionKillRequest | None = None, db: Session = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')
    session.kill_reason = payload.reason if payload else 'manual kill'
    request_kill(session_id, session.kill_reason)
    close_session(db, session, 'killed')
    return OkResponse()


@router.post('/{session_id}/disconnect-connections', response_model=OkResponse)
async def disconnect_connections(session_id: str, db: Session = Depends(get_db)):
    items = db.scalars(select(SessionConnection).where(SessionConnection.session_id == session_id, SessionConnection.state == 'open')).all()
    for item in items:
        item.state = 'killed'
        item.close_reason = 'manual disconnect'
    session = db.get(SessionModel, session_id)
    if session:
        session.active_connections_count = 0
    db.commit()
    return OkResponse()
