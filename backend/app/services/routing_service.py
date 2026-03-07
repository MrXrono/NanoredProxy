from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Account, Proxy, ProxyAggregate, RoutingEvent, Session as SessionModel, SessionConnection


def choose_strategy() -> str:
    return 'A' if random.randint(1, 100) <= 50 else 'B'


def _score_columns(strategy: str):
    composite = func.coalesce(ProxyAggregate.composite_score, 0.0)
    stability = func.coalesce(ProxyAggregate.stability_score, 0.0)
    latency = func.coalesce(ProxyAggregate.avg_latency_day_ms, 999999.0)
    speed = (func.coalesce(ProxyAggregate.avg_download_day_mbps, 0.0) + func.coalesce(ProxyAggregate.avg_upload_day_mbps, 0.0)) / 2.0
    if strategy == 'A':
        return [stability.desc(), latency.asc(), speed.desc(), composite.desc()]
    return [latency.asc(), speed.desc(), stability.desc(), composite.desc()]


def select_proxy_for_account(db: Session, account: Account, strategy: str, sticky_proxy_id: int | None = None) -> Proxy | None:
    stmt = (
        select(Proxy)
        .outerjoin(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id)
        .where(Proxy.is_enabled.is_(True), Proxy.status.in_(['online','degraded']))
    )
    if account.account_type == 'country' and account.country_code:
        stmt = stmt.where(Proxy.country_code == account.country_code)
    non_quarantine = db.scalars(stmt.where(Proxy.is_quarantined.is_(False)).order_by(*_score_columns(strategy)).limit(50)).all()
    candidates = non_quarantine or db.scalars(stmt.order_by(*_score_columns(strategy)).limit(50)).all()
    if not candidates:
        return None
    if sticky_proxy_id:
        sticky = next((p for p in candidates if p.id == sticky_proxy_id), None)
        if sticky:
            return sticky
    return candidates[0]


def open_session(db: Session, account: Account, client_ip: str, client_login: str) -> SessionModel:
    existing = db.scalar(select(SessionModel).where(SessionModel.client_ip == client_ip, SessionModel.client_login == client_login, SessionModel.status == 'active').order_by(SessionModel.started_at.desc()))
    if existing:
        return existing
    strategy = choose_strategy()
    proxy = select_proxy_for_account(db, account, strategy)
    session = SessionModel(account_id=account.id, client_ip=client_ip, client_login=client_login, strategy_variant=strategy, assigned_proxy_id=proxy.id if proxy else None, sticky_proxy_id=proxy.id if proxy else None)
    db.add(session)
    db.flush()
    db.add(RoutingEvent(session_id=session.id, old_proxy_id=None, new_proxy_id=proxy.id if proxy else None, event_type='initial_assign', reason='session_open', strategy_variant=strategy))
    db.commit()
    db.refresh(session)
    return session


def ensure_connection_proxy(db: Session, session: SessionModel) -> Proxy | None:
    account = db.get(Account, session.account_id)
    proxy = db.get(Proxy, session.assigned_proxy_id) if session.assigned_proxy_id else None
    if proxy and proxy.is_enabled and proxy.status in ('online', 'degraded') and not proxy.is_quarantined:
        return proxy
    next_proxy = select_proxy_for_account(db, account, session.strategy_variant, sticky_proxy_id=session.sticky_proxy_id)
    old_id = session.assigned_proxy_id
    session.assigned_proxy_id = next_proxy.id if next_proxy else None
    if next_proxy:
        session.sticky_proxy_id = next_proxy.id
    db.add(RoutingEvent(session_id=session.id, old_proxy_id=old_id, new_proxy_id=next_proxy.id if next_proxy else None, event_type='reroute_new_connections', reason='assigned proxy unavailable', strategy_variant=session.strategy_variant))
    db.commit()
    return next_proxy


def open_connection(db: Session, session: SessionModel, target_host: str, target_port: int) -> SessionConnection:
    proxy = ensure_connection_proxy(db, session)
    conn = SessionConnection(session_id=session.id, proxy_id=proxy.id if proxy else None, target_host=target_host, target_port=target_port)
    session.connections_count += 1
    session.active_connections_count += 1
    session.last_activity_at = datetime.utcnow()
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def close_connection(db: Session, connection: SessionConnection, bytes_in: int, bytes_out: int, state: str, close_reason: str | None):
    connection.bytes_in += bytes_in
    connection.bytes_out += bytes_out
    connection.state = state
    connection.close_reason = close_reason
    connection.ended_at = datetime.utcnow()
    connection.last_activity_at = datetime.utcnow()
    session = db.get(SessionModel, connection.session_id)
    if session:
        session.bytes_in += bytes_in
        session.bytes_out += bytes_out
        session.active_connections_count = max(0, session.active_connections_count - 1)
        session.last_activity_at = datetime.utcnow()
        if session.active_connections_count == 0 and state in ('closed', 'failed', 'killed'):
            session.avg_speed_total_mbps = 0
    db.commit()


def update_traffic(db: Session, session_id, connection_id, bytes_in_delta: int, bytes_out_delta: int):
    session = db.get(SessionModel, session_id)
    connection = db.get(SessionConnection, connection_id)
    if session:
        session.bytes_in += bytes_in_delta
        session.bytes_out += bytes_out_delta
        session.last_activity_at = datetime.utcnow()
    if connection:
        connection.bytes_in += bytes_in_delta
        connection.bytes_out += bytes_out_delta
        connection.last_activity_at = datetime.utcnow()
    db.commit()


def close_session(db: Session, session: SessionModel, status: str):
    session.status = status
    session.ended_at = datetime.utcnow()
    session.last_activity_at = datetime.utcnow()
    db.commit()
