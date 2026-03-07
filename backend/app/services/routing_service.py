from __future__ import annotations

import ipaddress
import random
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Proxy, ProxyAggregate, RoutingEvent, Session as SessionModel, SessionConnection, SystemSetting
from app.services.runtime_state import is_kill_requested, set_active_sessions_count, set_session_runtime
from app.services.traffic_service import apply_traffic, connection_closed, connection_opened, session_closed, session_opened


def choose_strategy(db: Session | None = None) -> str:
    split_a = 50
    if db is not None:
        setting = db.get(SystemSetting, 'ab_strategy_split')
        if setting and isinstance(setting.value, dict):
            split_a = int(setting.value.get('A', 50))
    return 'A' if random.randint(1, 100) <= split_a else 'B'


def _score_columns(strategy: str):
    rating = func.coalesce(ProxyAggregate.rating_score, 0)
    latency = func.coalesce(ProxyAggregate.avg_latency_day_ms, 999999.0)
    speed = (func.coalesce(ProxyAggregate.avg_download_day_mbps, 0.0) + func.coalesce(ProxyAggregate.avg_upload_day_mbps, 0.0)) / 2.0
    if strategy == 'A':
        return [rating.desc(), latency.asc(), speed.desc()]
    return [rating.desc(), speed.desc(), latency.asc()]


def _sticky_rating_threshold(db: Session) -> int:
    """Sticky proxy kept if rating difference <= threshold (out of 600)."""
    setting = db.get(SystemSetting, 'sticky_rating_threshold')
    if setting and isinstance(setting.value, dict):
        return int(setting.value.get('value', 50))
    return 50


def _normalize_client_ip(client_ip: str):
    try:
        return ipaddress.ip_address(client_ip)
    except ValueError:
        return client_ip


def select_proxy_for_account(
    db: Session,
    account: Account,
    strategy: str,
    sticky_proxy_id: int | None = None,
    exclude_proxy_ids: set[int] | None = None,
) -> Proxy | None:
    stmt = (
        select(Proxy)
        .outerjoin(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id)
        .where(Proxy.is_enabled.is_(True), Proxy.status.in_(['online', 'degraded']))
    )
    if account.account_type == 'country' and account.country_code:
        stmt = stmt.where(Proxy.country_code == account.country_code)
    if exclude_proxy_ids:
        stmt = stmt.where(Proxy.id.not_in(sorted(exclude_proxy_ids)))
    non_quarantine = db.scalars(stmt.where(Proxy.is_quarantined.is_(False)).order_by(*_score_columns(strategy)).limit(50)).all()
    candidates = non_quarantine or db.scalars(stmt.order_by(*_score_columns(strategy)).limit(50)).all()
    if not candidates:
        return None
    best = candidates[0]
    if sticky_proxy_id:
        sticky = next((p for p in candidates if p.id == sticky_proxy_id), None)
        if sticky:
            sticky_rating = int(sticky.aggregate.rating_score) if sticky.aggregate and sticky.aggregate.rating_score is not None else 0
            best_rating = int(best.aggregate.rating_score) if best.aggregate and best.aggregate.rating_score is not None else 0
            if best_rating - sticky_rating <= _sticky_rating_threshold(db):
                return sticky
    return best


def reroute_session_proxy(
    db: Session,
    session: SessionModel,
    reason: str,
    exclude_proxy_ids: set[int] | None = None,
    prefer_sticky: bool = True,
) -> Proxy | None:
    account = db.get(Account, session.account_id)
    if not account:
        return None
    next_proxy = select_proxy_for_account(
        db,
        account,
        session.strategy_variant,
        sticky_proxy_id=session.sticky_proxy_id if prefer_sticky else None,
        exclude_proxy_ids=exclude_proxy_ids,
    )
    old_id = session.assigned_proxy_id
    session.assigned_proxy_id = next_proxy.id if next_proxy else None
    if next_proxy:
        session.sticky_proxy_id = next_proxy.id
    set_session_runtime(str(session.id), {'status': session.status, 'assigned_proxy_id': session.assigned_proxy_id, 'sticky_proxy_id': session.sticky_proxy_id})
    db.add(RoutingEvent(session_id=session.id, old_proxy_id=old_id, new_proxy_id=next_proxy.id if next_proxy else None, event_type='reroute_new_connections', reason=reason, strategy_variant=session.strategy_variant))
    db.commit()
    return next_proxy


def open_session(db: Session, account: Account, client_ip: str, client_login: str) -> SessionModel:
    normalized_client_ip = _normalize_client_ip(client_ip)
    existing = db.scalar(
        select(SessionModel)
        .where(SessionModel.client_ip == normalized_client_ip, SessionModel.client_login == client_login, SessionModel.status == 'active')
        .order_by(SessionModel.started_at.desc())
    )
    if existing:
        set_session_runtime(str(existing.id), {'status': existing.status, 'assigned_proxy_id': existing.assigned_proxy_id, 'sticky_proxy_id': existing.sticky_proxy_id})
        return existing
    strategy = choose_strategy(db)
    proxy = select_proxy_for_account(db, account, strategy)
    session = SessionModel(
        account_id=account.id,
        client_ip=normalized_client_ip,
        client_login=client_login,
        strategy_variant=strategy,
        assigned_proxy_id=proxy.id if proxy else None,
        sticky_proxy_id=proxy.id if proxy else None,
    )
    db.add(session)
    db.flush()
    db.add(RoutingEvent(session_id=session.id, old_proxy_id=None, new_proxy_id=proxy.id if proxy else None, event_type='initial_assign', reason='session_open', strategy_variant=strategy))
    session_opened(db, session)
    db.commit()
    set_active_sessions_count(db.scalar(select(func.count()).select_from(SessionModel).where(SessionModel.status == 'active')) or 0)
    db.refresh(session)
    return session


def ensure_connection_proxy(db: Session, session: SessionModel) -> Proxy | None:
    proxy = db.get(Proxy, session.assigned_proxy_id) if session.assigned_proxy_id else None
    if proxy and proxy.is_enabled and proxy.status in ('online', 'degraded') and not proxy.is_quarantined:
        return proxy
    return reroute_session_proxy(db, session, reason='assigned proxy unavailable', prefer_sticky=True)


def open_connection(db: Session, session: SessionModel, target_host: str, target_port: int) -> SessionConnection:
    proxy = ensure_connection_proxy(db, session)
    conn = SessionConnection(session_id=session.id, proxy_id=proxy.id if proxy else None, target_host=target_host, target_port=target_port)
    session.connections_count += 1
    session.active_connections_count += 1
    session.last_activity_at = datetime.now(timezone.utc)
    db.add(conn)
    db.flush()
    connection_opened(db, session, proxy.id if proxy else None)
    db.commit()
    db.refresh(conn)
    return conn


def close_connection(db: Session, connection: SessionConnection, bytes_in: int, bytes_out: int, state: str, close_reason: str | None):
    connection.bytes_in += bytes_in
    connection.bytes_out += bytes_out
    connection.state = state
    connection.close_reason = close_reason
    connection.ended_at = datetime.now(timezone.utc)
    connection.last_activity_at = datetime.now(timezone.utc)
    session = db.get(SessionModel, connection.session_id)
    if session:
        session.bytes_in += bytes_in
        session.bytes_out += bytes_out
        session.active_connections_count = max(0, session.active_connections_count - 1)
        session.last_activity_at = datetime.now(timezone.utc)
        apply_traffic(db, session, connection.proxy_id, bytes_in, bytes_out)
        connection_closed(db, session, connection.proxy_id)
        if session.active_connections_count == 0 and session.status == 'killed':
            session.ended_at = datetime.now(timezone.utc)
    db.commit()


def update_traffic(db: Session, session_id, connection_id, bytes_in_delta: int, bytes_out_delta: int):
    session = db.get(SessionModel, session_id)
    connection = db.get(SessionConnection, connection_id)
    if session:
        session.bytes_in += bytes_in_delta
        session.bytes_out += bytes_out_delta
        session.last_activity_at = datetime.now(timezone.utc)
    if connection:
        connection.bytes_in += bytes_in_delta
        connection.bytes_out += bytes_out_delta
        connection.last_activity_at = datetime.now(timezone.utc)
    apply_traffic(db, session, connection.proxy_id if connection else None, bytes_in_delta, bytes_out_delta)
    db.commit()


def close_session(db: Session, session: SessionModel, status: str):
    if session.status == 'killed' and status == 'closed':
        status = 'killed'
    if is_kill_requested(str(session.id)):
        status = 'killed'
    session.status = status
    session.ended_at = datetime.now(timezone.utc)
    session.last_activity_at = datetime.now(timezone.utc)
    if status != 'active':
        session_closed(db, session)
    db.commit()
