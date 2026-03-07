from sqlalchemy import func, select
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.models import Account, Proxy, ProxyAggregate, Session as SessionModel

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
async def traffic_stats(scope_type: str = 'global', scope_id: str | None = None):
    return {'scope_type': scope_type, 'scope_id': scope_id, 'items': []}


@router.get('/countries')
async def country_stats(db: Session = Depends(get_db)):
    rows = db.execute(select(Proxy.country_code, func.count()).group_by(Proxy.country_code)).all()
    return {'items': [{'country_code': cc, 'count': count} for cc, count in rows]}


@router.get('/accounts')
async def account_stats(db: Session = Depends(get_db)):
    rows = db.execute(select(Account.username, func.count(SessionModel.id)).join(SessionModel, SessionModel.account_id == Account.id, isouter=True).group_by(Account.username)).all()
    return {'items': [{'username': username, 'sessions': count} for username, count in rows]}


@router.get('/proxies/top')
async def top_proxies(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(select(Proxy.id, Proxy.host, ProxyAggregate.composite_score).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True).order_by(ProxyAggregate.composite_score.desc().nullslast()).limit(limit)).all()
    return {'items': [{'id': id_, 'host': str(host), 'composite_score': float(score) if score is not None else None} for id_, host, score in rows], 'limit': limit}


@router.get('/proxies/worst')
async def worst_proxies(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(select(Proxy.id, Proxy.host, ProxyAggregate.composite_score).join(ProxyAggregate, ProxyAggregate.proxy_id == Proxy.id, isouter=True).order_by(ProxyAggregate.composite_score.asc().nullslast()).limit(limit)).all()
    return {'items': [{'id': id_, 'host': str(host), 'composite_score': float(score) if score is not None else None} for id_, host, score in rows], 'limit': limit}


@router.get('/ab')
async def ab_stats(db: Session = Depends(get_db)):
    rows = db.execute(select(SessionModel.strategy_variant, func.count()).group_by(SessionModel.strategy_variant)).all()
    out = {'A': {'sessions': 0}, 'B': {'sessions': 0}}
    for variant, count in rows:
        out[variant] = {'sessions': count}
    return out
