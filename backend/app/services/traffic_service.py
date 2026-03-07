from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountAggregate, CountryAggregate, Proxy, ProxyAggregate, Session as SessionModel, TrafficRollup
from app.services.runtime_state import clear_kill, clear_session_runtime, set_active_sessions_count, set_session_runtime


def _bucket_start(dt: datetime, bucket_type: str) -> datetime:
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if bucket_type == 'day':
        dt = dt.replace(hour=0)
    return dt


def _get_or_create_rollup(db: Session, scope_type: str, scope_id: str, bucket_type: str, bucket_start: datetime) -> TrafficRollup:
    row = db.scalar(select(TrafficRollup).where(TrafficRollup.scope_type == scope_type, TrafficRollup.scope_id == scope_id, TrafficRollup.bucket_type == bucket_type, TrafficRollup.bucket_start == bucket_start))
    if row:
        return row
    row = TrafficRollup(scope_type=scope_type, scope_id=scope_id, bucket_type=bucket_type, bucket_start=bucket_start)
    db.add(row)
    db.flush()
    return row


def apply_rollup(db: Session, scope_type: str, scope_id: str, bytes_in: int = 0, bytes_out: int = 0, sessions_delta: int = 0, connections_delta: int = 0, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    for bucket_type in ('hour', 'day'):
        row = _get_or_create_rollup(db, scope_type, scope_id, bucket_type, _bucket_start(now, bucket_type))
        row.bytes_in += int(bytes_in)
        row.bytes_out += int(bytes_out)
        row.sessions_count += int(sessions_delta)
        row.connections_count += int(connections_delta)


def _ensure_account_aggregate(db: Session, account_id: int) -> AccountAggregate:
    agg = db.get(AccountAggregate, account_id)
    if agg:
        return agg
    agg = AccountAggregate(account_id=account_id)
    db.add(agg)
    db.flush()
    return agg


def _ensure_country_aggregate(db: Session, country_code: str) -> CountryAggregate:
    agg = db.get(CountryAggregate, country_code)
    if agg:
        return agg
    agg = CountryAggregate(country_code=country_code)
    db.add(agg)
    db.flush()
    return agg


def _ensure_proxy_aggregate(db: Session, proxy_id: int) -> ProxyAggregate:
    agg = db.get(ProxyAggregate, proxy_id)
    if agg:
        return agg
    agg = ProxyAggregate(proxy_id=proxy_id)
    db.add(agg)
    db.flush()
    return agg


def session_opened(db: Session, session: SessionModel) -> None:
    account_agg = _ensure_account_aggregate(db, session.account_id)
    account_agg.active_sessions += 1
    account_agg.total_sessions += 1
    if session.assigned_proxy_id:
        proxy_agg = _ensure_proxy_aggregate(db, session.assigned_proxy_id)
        proxy_agg.current_active_sessions += 1
        proxy_agg.total_sessions += 1
    account = db.get(Account, session.account_id)
    if account and account.country_code:
        country_agg = _ensure_country_aggregate(db, account.country_code)
        country_agg.active_sessions += 1
    apply_rollup(db, 'account', str(session.account_id), sessions_delta=1)
    apply_rollup(db, 'global', 'global', sessions_delta=1)
    if account and account.country_code:
        apply_rollup(db, 'country', account.country_code, sessions_delta=1)
    set_session_runtime(str(session.id), {'status': session.status, 'assigned_proxy_id': session.assigned_proxy_id, 'sticky_proxy_id': session.sticky_proxy_id})


def connection_opened(db: Session, session: SessionModel, proxy_id: int | None) -> None:
    account_agg = _ensure_account_aggregate(db, session.account_id)
    account_agg.total_connections += 1
    if proxy_id:
        proxy_agg = _ensure_proxy_aggregate(db, proxy_id)
        proxy_agg.current_active_connections += 1
        proxy_agg.total_connections += 1
    account = db.get(Account, session.account_id)
    apply_rollup(db, 'account', str(session.account_id), connections_delta=1)
    apply_rollup(db, 'global', 'global', connections_delta=1)
    if account and account.country_code:
        apply_rollup(db, 'country', account.country_code, connections_delta=1)
    if proxy_id:
        apply_rollup(db, 'proxy', str(proxy_id), connections_delta=1)


def apply_traffic(db: Session, session: SessionModel | None, proxy_id: int | None, bytes_in: int, bytes_out: int) -> None:
    if not session:
        return
    account_agg = _ensure_account_aggregate(db, session.account_id)
    account_agg.bytes_in += int(bytes_in)
    account_agg.bytes_out += int(bytes_out)
    if proxy_id:
        proxy_agg = _ensure_proxy_aggregate(db, proxy_id)
        proxy_agg.bytes_in += int(bytes_in)
        proxy_agg.bytes_out += int(bytes_out)
    account = db.get(Account, session.account_id)
    if account and account.country_code:
        country_agg = _ensure_country_aggregate(db, account.country_code)
        country_agg.bytes_in += int(bytes_in)
        country_agg.bytes_out += int(bytes_out)
    apply_rollup(db, 'account', str(session.account_id), bytes_in=bytes_in, bytes_out=bytes_out)
    apply_rollup(db, 'global', 'global', bytes_in=bytes_in, bytes_out=bytes_out)
    if account and account.country_code:
        apply_rollup(db, 'country', account.country_code, bytes_in=bytes_in, bytes_out=bytes_out)
    if proxy_id:
        apply_rollup(db, 'proxy', str(proxy_id), bytes_in=bytes_in, bytes_out=bytes_out)


def connection_closed(db: Session, session: SessionModel | None, proxy_id: int | None) -> None:
    if proxy_id:
        proxy_agg = _ensure_proxy_aggregate(db, proxy_id)
        proxy_agg.current_active_connections = max(0, proxy_agg.current_active_connections - 1)
    if session:
        set_session_runtime(str(session.id), {'status': session.status, 'assigned_proxy_id': session.assigned_proxy_id, 'sticky_proxy_id': session.sticky_proxy_id, 'last_activity_at': session.last_activity_at.isoformat() if session.last_activity_at else None})


def session_closed(db: Session, session: SessionModel) -> None:
    account_agg = _ensure_account_aggregate(db, session.account_id)
    account_agg.active_sessions = max(0, account_agg.active_sessions - 1)
    if session.assigned_proxy_id:
        proxy_agg = _ensure_proxy_aggregate(db, session.assigned_proxy_id)
        proxy_agg.current_active_sessions = max(0, proxy_agg.current_active_sessions - 1)
    account = db.get(Account, session.account_id)
    if account and account.country_code:
        country_agg = _ensure_country_aggregate(db, account.country_code)
        country_agg.active_sessions = max(0, country_agg.active_sessions - 1)
    clear_kill(str(session.id))
    clear_session_runtime(str(session.id))
    active_sessions = db.execute(select(SessionModel)).scalars().all()
    set_active_sessions_count(sum(1 for x in active_sessions if x.status == 'active'))


def refresh_country_proxy_stats(db: Session) -> None:
    countries = {row[0] for row in db.execute(select(Proxy.country_code).where(Proxy.country_code.is_not(None))).all()}
    for country_code in countries:
        agg = _ensure_country_aggregate(db, country_code)
        proxies = db.execute(select(Proxy, ProxyAggregate).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True).where(Proxy.country_code == country_code)).all()
        agg.total_proxies = len(proxies)
        agg.working_proxies = sum(1 for proxy, _ in proxies if proxy.status in ('online', 'degraded') and proxy.is_enabled and not proxy.is_quarantined)
        agg.online_proxies = sum(1 for proxy, _ in proxies if proxy.status == 'online')
        agg.degraded_proxies = sum(1 for proxy, _ in proxies if proxy.status == 'degraded')
        agg.quarantined_proxies = sum(1 for proxy, _ in proxies if proxy.is_quarantined)
        latency_values = [float(a.avg_latency_day_ms) for _, a in proxies if a and a.avg_latency_day_ms is not None]
        download_values = [float(a.avg_download_day_mbps) for _, a in proxies if a and a.avg_download_day_mbps is not None]
        upload_values = [float(a.avg_upload_day_mbps) for _, a in proxies if a and a.avg_upload_day_mbps is not None]
        agg.avg_latency_day_ms = sum(latency_values) / len(latency_values) if latency_values else None
        agg.avg_download_day_mbps = sum(download_values) / len(download_values) if download_values else None
        agg.avg_upload_day_mbps = sum(upload_values) / len(upload_values) if upload_values else None
