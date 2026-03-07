from sqlalchemy import func, select
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.models import Account, AccountAggregate, CountryAggregate, Proxy, ProxyAggregate, Session as SessionModel, TrafficRollup

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
async def traffic_stats(scope_type: str = 'global', scope_id: str | None = None, bucket_type: str = 'hour', db: Session = Depends(get_db)):
    stmt = select(TrafficRollup).where(TrafficRollup.scope_type == scope_type, TrafficRollup.bucket_type == bucket_type).order_by(TrafficRollup.bucket_start.desc()).limit(200)
    if scope_id is not None:
        stmt = stmt.where(TrafficRollup.scope_id == scope_id)
    items = db.scalars(stmt).all()
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
async def top_proxies(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(select(Proxy.id, Proxy.host, ProxyAggregate.composite_score, ProxyAggregate.stability_score).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True).order_by(ProxyAggregate.composite_score.desc().nullslast()).limit(limit)).all()
    return {'items': [{'id': id_, 'host': str(host), 'composite_score': float(score) if score is not None else None, 'stability_score': float(stability) if stability is not None else None} for id_, host, score, stability in rows], 'limit': limit}


@router.get('/proxies/worst')
async def worst_proxies(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(select(Proxy.id, Proxy.host, ProxyAggregate.composite_score, ProxyAggregate.stability_score).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True).order_by(ProxyAggregate.composite_score.asc().nullslast()).limit(limit)).all()
    return {'items': [{'id': id_, 'host': str(host), 'composite_score': float(score) if score is not None else None, 'stability_score': float(stability) if stability is not None else None} for id_, host, score, stability in rows], 'limit': limit}


@router.get('/ab')
async def ab_stats(db: Session = Depends(get_db)):
    rows = db.execute(select(SessionModel.strategy_variant, func.count(), func.avg(SessionModel.bytes_in + SessionModel.bytes_out)).group_by(SessionModel.strategy_variant)).all()
    out = {'A': {'sessions': 0, 'avg_total_bytes': 0}, 'B': {'sessions': 0, 'avg_total_bytes': 0}}
    for variant, count, avg_total_bytes in rows:
        out[variant] = {'sessions': count, 'avg_total_bytes': float(avg_total_bytes or 0)}
    return out
