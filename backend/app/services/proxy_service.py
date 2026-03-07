from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Proxy, ProxyAggregate, ProxyCheck, ProxyGeoAttempt, ProxySpeedtest
from app.schemas.proxy import ProxyUpdateRequest


def _aggregate_dict(proxy: Proxy) -> dict:
    agg = proxy.aggregate
    return {
        'avg_latency_day_ms': float(agg.avg_latency_day_ms) if agg and agg.avg_latency_day_ms is not None else None,
        'avg_download_day_mbps': float(agg.avg_download_day_mbps) if agg and agg.avg_download_day_mbps is not None else None,
        'avg_upload_day_mbps': float(agg.avg_upload_day_mbps) if agg and agg.avg_upload_day_mbps is not None else None,
        'stability_score': float(agg.stability_score) if agg and agg.stability_score is not None else None,
        'composite_score': float(agg.composite_score) if agg and agg.composite_score is not None else None,
    }


def proxy_to_dict(proxy: Proxy) -> dict:
    base = {
        'id': proxy.id,
        'host': str(proxy.host),
        'port': proxy.port,
        'auth_username': proxy.auth_username,
        'auth_password': proxy.auth_password,
        'has_auth': proxy.has_auth,
        'status': proxy.status,
        'country_code': proxy.country_code,
        'country_source': proxy.country_source,
        'country_manual_override': proxy.country_manual_override,
        'is_enabled': proxy.is_enabled,
        'is_quarantined': proxy.is_quarantined,
        'notes': proxy.notes,
        'last_checked_at': proxy.last_checked_at,
    }
    base.update(_aggregate_dict(proxy))
    return base


def list_proxies(db: Session, *, status: str | None = None, country_code: str | None = None, search: str | None = None) -> list[Proxy]:
    stmt = select(Proxy).order_by(Proxy.id.desc())
    if status:
        stmt = stmt.where(Proxy.status == status)
    if country_code:
        stmt = stmt.where(Proxy.country_code == country_code)
    if search:
        like = f'%{search}%'
        stmt = stmt.where(cast(Proxy.host, String).ilike(like) | func.coalesce(Proxy.country_code, '').ilike(like))
    return list(db.scalars(stmt).unique())


def get_proxy(db: Session, proxy_id: int) -> Proxy | None:
    return db.get(Proxy, proxy_id)


def create_proxy_if_missing(db: Session, payload: dict) -> tuple[Proxy, bool]:
    stmt = select(Proxy).where(
        Proxy.host == payload['host'],
        Proxy.port == payload['port'],
        Proxy.auth_username.is_(payload.get('auth_username')) if payload.get('auth_username') is None else Proxy.auth_username == payload.get('auth_username'),
        Proxy.auth_password.is_(payload.get('auth_password')) if payload.get('auth_password') is None else Proxy.auth_password == payload.get('auth_password'),
    )
    existing = db.scalar(stmt)
    if existing:
        return existing, False
    proxy = Proxy(**payload, status='new', country_source='unknown')
    db.add(proxy)
    db.flush()
    db.add(ProxyAggregate(proxy_id=proxy.id))
    db.add(AuditLog(actor_type='admin', actor_id='1', action='proxy_imported', target_type='proxy', target_id=str(proxy.id), payload={'host': payload['host'], 'port': payload['port']}))
    return proxy, True


def update_proxy(db: Session, proxy: Proxy, payload: ProxyUpdateRequest, actor_id: str = '1') -> Proxy:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(proxy, key, value)
    db.add(AuditLog(actor_type='admin', actor_id=actor_id, action='proxy_updated', target_type='proxy', target_id=str(proxy.id), payload=data))
    db.commit()
    db.refresh(proxy)
    return proxy


def set_country(db: Session, proxy: Proxy, country_code: str | None, manual: bool, actor_id: str = '1') -> Proxy:
    proxy.country_code = country_code.lower() if country_code else None
    proxy.country_source = 'manual' if manual and country_code else 'unknown'
    proxy.country_manual_override = bool(manual and country_code)
    proxy.last_geo_attempt_at = datetime.utcnow()
    db.add(ProxyGeoAttempt(proxy_id=proxy.id, success=bool(country_code), detected_country_code=proxy.country_code, source='manual' if manual else 'auto'))
    db.add(AuditLog(actor_type='admin', actor_id=actor_id, action='proxy_country_set_manual' if manual else 'proxy_country_cleared', target_type='proxy', target_id=str(proxy.id), payload={'country_code': proxy.country_code}))
    db.commit()
    db.refresh(proxy)
    return proxy


def toggle_proxy(db: Session, proxy: Proxy, *, enabled: bool | None = None, quarantine: bool | None = None) -> Proxy:
    if enabled is not None:
        proxy.is_enabled = enabled
        if not enabled:
            proxy.status = 'disabled'
    if quarantine is not None:
        proxy.is_quarantined = quarantine
        if quarantine:
            proxy.status = 'quarantine'
        elif proxy.status == 'quarantine':
            proxy.status = 'checking'
    db.commit()
    db.refresh(proxy)
    return proxy


def recent_checks(db: Session, proxy_id: int, limit: int = 50):
    stmt = select(ProxyCheck).where(ProxyCheck.proxy_id == proxy_id).order_by(ProxyCheck.checked_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def recent_speedtests(db: Session, proxy_id: int, limit: int = 50):
    stmt = select(ProxySpeedtest).where(ProxySpeedtest.proxy_id == proxy_id).order_by(ProxySpeedtest.started_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def recent_geo_attempts(db: Session, proxy_id: int, limit: int = 50):
    stmt = select(ProxyGeoAttempt).where(ProxyGeoAttempt.proxy_id == proxy_id).order_by(ProxyGeoAttempt.attempted_at.desc()).limit(limit)
    return list(db.scalars(stmt))
