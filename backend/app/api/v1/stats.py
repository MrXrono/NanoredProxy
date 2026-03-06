from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.models import Account, AccountAggregate, CountryAggregate, Proxy, ProxyAggregate, ProxyCurrentDayStat, Session as SessionModel, TrafficRollup

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('/global')
async def global_stats(db: Session = Depends(get_db)):
    return {
        'traffic': {
            'bytes_in': db.scalar(select(func.coalesce(func.sum(SessionModel.bytes_in), 0))) or 0,
            'bytes_out': db.scalar(select(func.coalesce(func.sum(SessionModel.bytes_out), 0))) or 0,
        },
        'sessions': {
            'active': db.scalar(select(func.count()).select_from(SessionModel).where(SessionModel.status == 'active')) or 0,
            'total': db.scalar(select(func.count()).select_from(SessionModel)) or 0,
        },
        'proxies': {
            'total': db.scalar(select(func.count()).select_from(Proxy)) or 0,
            'online': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'online')) or 0,
        },
    }


@router.get('/traffic')
async def traffic_stats(
    scope_type: str = 'global',
    scope_id: str | None = None,
    bucket_type: str = 'hour',
    from_ts: datetime | None = Query(default=None, alias='from'),
    to_ts: datetime | None = Query(default=None, alias='to'),
    db: Session = Depends(get_db),
):
    stmt = select(TrafficRollup).where(TrafficRollup.scope_type == scope_type, TrafficRollup.bucket_type == bucket_type)
    if scope_id is not None:
        stmt = stmt.where(TrafficRollup.scope_id == scope_id)
    if from_ts is not None:
        stmt = stmt.where(TrafficRollup.bucket_start >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(TrafficRollup.bucket_start <= to_ts)
    items = db.scalars(stmt.order_by(TrafficRollup.bucket_start.desc()).limit(500)).all()
    return {'scope_type': scope_type, 'scope_id': scope_id, 'bucket_type': bucket_type, 'items': [{'bucket_start': x.bucket_start, 'bytes_in': x.bytes_in, 'bytes_out': x.bytes_out, 'total_bytes': x.bytes_in + x.bytes_out, 'sessions_count': x.sessions_count, 'connections_count': x.connections_count} for x in items]}


@router.get('/countries')
async def country_stats(db: Session = Depends(get_db)):
    rows = db.scalars(select(CountryAggregate).order_by(CountryAggregate.working_proxies.desc(), CountryAggregate.country_code.asc())).all()
    return {'items': [{'country_code': x.country_code, 'total_proxies': x.total_proxies, 'working_proxies': x.working_proxies, 'online_proxies': x.online_proxies, 'degraded_proxies': x.degraded_proxies, 'quarantined_proxies': x.quarantined_proxies, 'avg_latency_day_ms': float(x.avg_latency_day_ms) if x.avg_latency_day_ms is not None else None, 'avg_download_day_mbps': float(x.avg_download_day_mbps) if x.avg_download_day_mbps is not None else None, 'avg_upload_day_mbps': float(x.avg_upload_day_mbps) if x.avg_upload_day_mbps is not None else None, 'active_sessions': x.active_sessions, 'bytes_in': x.bytes_in, 'bytes_out': x.bytes_out} for x in rows]}


@router.get('/accounts')
async def account_stats(db: Session = Depends(get_db)):
    rows = db.execute(select(Account, AccountAggregate).join(AccountAggregate, AccountAggregate.account_id == Account.id, isouter=True).order_by(Account.username.asc())).all()
    return {'items': [{'username': account.username, 'account_type': account.account_type, 'country_code': account.country_code, 'active_sessions': agg.active_sessions if agg else 0, 'total_sessions': agg.total_sessions if agg else 0, 'total_connections': agg.total_connections if agg else 0, 'bytes_in': agg.bytes_in if agg else 0, 'bytes_out': agg.bytes_out if agg else 0, 'avg_speed_mbps': float(agg.avg_speed_mbps) if agg and agg.avg_speed_mbps is not None else None} for account, agg in rows]}


@router.get('/proxies/top')
async def top_proxies(limit: int = 20, country_code: str | None = None, sort_by: str = 'composite_score', db: Session = Depends(get_db)):
    sort_col = {
        'composite_score': ProxyAggregate.composite_score,
        'stability_score': ProxyAggregate.stability_score,
        'avg_latency_day_ms': ProxyAggregate.avg_latency_day_ms,
        'avg_download_day_mbps': ProxyAggregate.avg_download_day_mbps,
    }.get(sort_by, ProxyAggregate.composite_score)
    stmt = select(Proxy.id, Proxy.host, Proxy.country_code, ProxyAggregate.composite_score, ProxyAggregate.stability_score, ProxyAggregate.avg_latency_day_ms, ProxyAggregate.avg_download_day_mbps).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True)
    if country_code:
        stmt = stmt.where(Proxy.country_code == country_code)
    order = sort_col.asc().nullslast() if sort_by == 'avg_latency_day_ms' else sort_col.desc().nullslast()
    rows = db.execute(stmt.order_by(order).limit(limit)).all()
    return {'items': [{'id': id_, 'host': str(host), 'country_code': cc, 'composite_score': float(score) if score is not None else None, 'stability_score': float(stability) if stability is not None else None, 'avg_latency_day_ms': float(lat) if lat is not None else None, 'avg_download_day_mbps': float(down) if down is not None else None} for id_, host, cc, score, stability, lat, down in rows], 'limit': limit, 'sort_by': sort_by}


@router.get('/proxies/worst')
async def worst_proxies(limit: int = 20, country_code: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Proxy.id, Proxy.host, Proxy.country_code, ProxyAggregate.composite_score, ProxyAggregate.stability_score).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True)
    if country_code:
        stmt = stmt.where(Proxy.country_code == country_code)
    rows = db.execute(stmt.order_by(ProxyAggregate.composite_score.asc().nullslast()).limit(limit)).all()
    return {'items': [{'id': id_, 'host': str(host), 'country_code': cc, 'composite_score': float(score) if score is not None else None, 'stability_score': float(stability) if stability is not None else None} for id_, host, cc, score, stability in rows], 'limit': limit}


@router.get('/ab')
async def ab_stats(db: Session = Depends(get_db)):
    rows = db.execute(select(SessionModel.strategy_variant, func.count(), func.avg(SessionModel.bytes_in + SessionModel.bytes_out)).group_by(SessionModel.strategy_variant)).all()
    out = {'A': {'sessions': 0, 'avg_total_bytes': 0}, 'B': {'sessions': 0, 'avg_total_bytes': 0}}
    for variant, count, avg_total_bytes in rows:
        out[variant] = {'sessions': count, 'avg_total_bytes': float(avg_total_bytes or 0)}
    return out


@router.get('/rating')
async def rating_table(
    limit: int = 100,
    country_code: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Proxy rating table sorted by rating_score DESC."""
    stmt = (
        select(
            Proxy.id, func.host(Proxy.host).label('host'), Proxy.port,
            Proxy.status, Proxy.country_code, Proxy.is_quarantined,
            ProxyAggregate.rating_score,
            ProxyAggregate.ping_avg_ms_today,
            ProxyAggregate.ping_success_rate_today,
            ProxyAggregate.auth_avg_ms_today,
            ProxyAggregate.auth_success_rate_today,
            ProxyAggregate.avg_download_day_mbps,
            ProxyAggregate.avg_upload_day_mbps,
        )
        .join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True)
        .where(Proxy.is_enabled.is_(True))
    )
    if country_code:
        stmt = stmt.where(Proxy.country_code == country_code)
    if status:
        stmt = stmt.where(Proxy.status == status)
    rows = db.execute(
        stmt.order_by(func.coalesce(ProxyAggregate.rating_score, 0).desc()).limit(limit)
    ).all()
    return {
        'items': [
            {
                'id': r.id,
                'host': r.host,
                'port': r.port,
                'status': r.status,
                'country': r.country_code or '-',
                'quarantined': r.is_quarantined,
                'rating': int(r.rating_score) if r.rating_score is not None else 0,
                'ping_ms': round(float(r.ping_avg_ms_today), 1) if r.ping_avg_ms_today is not None else None,
                'ping_rate': round(float(r.ping_success_rate_today) * 100, 1) if r.ping_success_rate_today is not None else None,
                'auth_ms': round(float(r.auth_avg_ms_today), 1) if r.auth_avg_ms_today is not None else None,
                'auth_rate': round(float(r.auth_success_rate_today) * 100, 1) if r.auth_success_rate_today is not None else None,
                'download': round(float(r.avg_download_day_mbps), 2) if r.avg_download_day_mbps is not None else None,
                'upload': round(float(r.avg_upload_day_mbps), 2) if r.avg_upload_day_mbps is not None else None,
            }
            for r in rows
        ],
        'total': len(rows),
    }
