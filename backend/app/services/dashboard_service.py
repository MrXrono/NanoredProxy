from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, CountryAggregate, Proxy, ProxyAggregate, Session as SessionModel, SessionConnection, TrafficRollup


def get_summary(db: Session) -> dict:
    return {
        'proxies_total': db.scalar(select(func.count()).select_from(Proxy)) or 0,
        'proxies_online': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'online')) or 0,
        'proxies_degraded': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'degraded')) or 0,
        'proxies_offline': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'offline')) or 0,
        'proxies_quarantine': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.is_quarantined.is_(True))) or 0,
        'country_unknown': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.country_code.is_(None))) or 0,
        'accounts_total': db.scalar(select(func.count()).select_from(Account)) or 0,
        'accounts_enabled': db.scalar(select(func.count()).select_from(Account).where(Account.is_enabled.is_(True))) or 0,
        'active_sessions': db.scalar(select(func.count()).select_from(SessionModel).where(SessionModel.status == 'active')) or 0,
        'active_connections': db.scalar(select(func.count()).select_from(SessionConnection).where(SessionConnection.state == 'open')) or 0,
        'traffic_bytes_in': db.scalar(select(func.coalesce(func.sum(SessionModel.bytes_in), 0))) or 0,
        'traffic_bytes_out': db.scalar(select(func.coalesce(func.sum(SessionModel.bytes_out), 0))) or 0,
    }


def _period_delta(period: str) -> timedelta:
    return {
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30),
    }.get(period, timedelta(hours=24))


def _serialize_rollup(row: TrafficRollup) -> dict:
    return {
        'bucket_start': row.bucket_start.isoformat() if row.bucket_start else None,
        'bytes_in': row.bytes_in,
        'bytes_out': row.bytes_out,
        'total_bytes': row.bytes_in + row.bytes_out,
        'sessions_count': row.sessions_count,
        'connections_count': row.connections_count,
    }


def get_charts(db: Session, period: str = '24h') -> dict:
    since = datetime.now(timezone.utc) - _period_delta(period)
    bucket_type = 'hour' if period == '24h' else 'day'

    traffic_rows = db.scalars(
        select(TrafficRollup)
        .where(
            TrafficRollup.scope_type == 'global',
            TrafficRollup.scope_id == 'global',
            TrafficRollup.bucket_type == bucket_type,
            TrafficRollup.bucket_start >= since,
        )
        .order_by(TrafficRollup.bucket_start.asc())
    ).all()

    latency_rows = db.execute(
        select(Proxy.id, Proxy.host, ProxyAggregate.avg_latency_hour_ms, ProxyAggregate.avg_latency_day_ms)
        .join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True)
        .where(Proxy.is_enabled.is_(True))
        .order_by(ProxyAggregate.avg_latency_day_ms.asc().nullslast())
        .limit(10)
    ).all()

    speed_rows = db.execute(
        select(Proxy.id, Proxy.host, Proxy.country_code, ProxyAggregate.avg_download_day_mbps, ProxyAggregate.avg_upload_day_mbps, ProxyAggregate.composite_score)
        .join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True)
        .where(Proxy.is_enabled.is_(True))
        .order_by(ProxyAggregate.avg_download_day_mbps.desc().nullslast())
        .limit(10)
    ).all()

    countries = db.scalars(
        select(CountryAggregate).order_by(CountryAggregate.working_proxies.desc(), CountryAggregate.country_code.asc()).limit(20)
    ).all()

    return {
        'period': period,
        'bucket_type': bucket_type,
        'traffic_by_bucket': [_serialize_rollup(r) for r in traffic_rows],
        'latency_top': [
            {
                'proxy_id': proxy_id,
                'host': str(host),
                'avg_latency_hour_ms': float(lat_hour) if lat_hour is not None else None,
                'avg_latency_day_ms': float(lat_day) if lat_day is not None else None,
            }
            for proxy_id, host, lat_hour, lat_day in latency_rows
        ],
        'speed_top': [
            {
                'proxy_id': proxy_id,
                'host': str(host),
                'country_code': country_code,
                'avg_download_day_mbps': float(down) if down is not None else None,
                'avg_upload_day_mbps': float(up) if up is not None else None,
                'composite_score': float(score) if score is not None else None,
            }
            for proxy_id, host, country_code, down, up, score in speed_rows
        ],
        'country_distribution': [
            {
                'country_code': c.country_code,
                'working_proxies': c.working_proxies,
                'online_proxies': c.online_proxies,
                'active_sessions': c.active_sessions,
                'avg_latency_day_ms': float(c.avg_latency_day_ms) if c.avg_latency_day_ms is not None else None,
            }
            for c in countries
        ],
    }
