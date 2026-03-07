from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.schemas.common import OkResponse
from app.schemas.proxy import ProxyImportResponse, ProxyImportTextRequest, ProxySetCountryRequest, ProxyUpdateRequest
from app.services.event_service import publish_event
from app.services.proxy_parser import parse_proxy_text
from app.services.proxy_service import (
    create_proxy_if_missing,
    get_proxy as db_get_proxy,
    list_proxies as db_list_proxies,
    proxy_to_dict,
    recent_checks,
    recent_geo_attempts,
    recent_speedtests,
    set_country as svc_set_country,
    toggle_proxy,
    update_proxy,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('')
async def list_proxies(
    status: str | None = None,
    country_code: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    items = [proxy_to_dict(p) for p in db_list_proxies(db, status=status, country_code=country_code, search=search)]
    return {'items': items, 'total': len(items), 'page': 1, 'page_size': len(items) or 50}


@router.post('/import/text', response_model=ProxyImportResponse)
async def import_text(payload: ProxyImportTextRequest, db: Session = Depends(get_db), admin: dict = Depends(require_admin)):
    items = parse_proxy_text(payload.text)
    inserted = 0
    duplicates = 0
    for item in items:
        proxy, created = create_proxy_if_missing(db, item)
        inserted += int(created)
        duplicates += int(not created)
        if created:
            publish_event('proxy.imported', {'proxy_id': proxy.id, 'host': item['host'], 'port': item['port']})
    db.commit()
    return ProxyImportResponse(parsed=len(items), inserted=inserted, duplicates=duplicates, queued_for_check=inserted)


@router.post('/import/file', response_model=ProxyImportResponse)
async def import_file(file: UploadFile = File(...), db: Session = Depends(get_db), admin: dict = Depends(require_admin)):
    content = (await file.read()).decode('utf-8', errors='ignore')
    items = parse_proxy_text(content)
    inserted = 0
    duplicates = 0
    for item in items:
        proxy, created = create_proxy_if_missing(db, item)
        inserted += int(created)
        duplicates += int(not created)
        if created:
            publish_event('proxy.imported', {'proxy_id': proxy.id, 'host': item['host'], 'port': item['port']})
    db.commit()
    return ProxyImportResponse(parsed=len(items), inserted=inserted, duplicates=duplicates, queued_for_check=inserted)


@router.get('/{proxy_id}')
async def get_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    data = proxy_to_dict(proxy)
    data['aggregates'] = {
        'avg_latency_all_ms': float(proxy.aggregate.avg_latency_all_ms) if proxy.aggregate and proxy.aggregate.avg_latency_all_ms is not None else None,
        'avg_latency_day_ms': data['avg_latency_day_ms'],
        'avg_latency_hour_ms': float(proxy.aggregate.avg_latency_hour_ms) if proxy.aggregate and proxy.aggregate.avg_latency_hour_ms is not None else None,
        'success_rate_day': float(proxy.aggregate.success_rate_day) if proxy.aggregate and proxy.aggregate.success_rate_day is not None else None,
        'avg_download_day_mbps': data['avg_download_day_mbps'],
        'avg_upload_day_mbps': data['avg_upload_day_mbps'],
        'stability_score': data['stability_score'],
        'composite_score': data['composite_score'],
        'quarantine_score': float(proxy.aggregate.quarantine_score) if proxy.aggregate and proxy.aggregate.quarantine_score is not None else None,
        'real_traffic_avg_speed_mbps': float(proxy.aggregate.real_traffic_avg_speed_mbps) if proxy.aggregate and proxy.aggregate.real_traffic_avg_speed_mbps is not None else None,
    }
    return data


@router.patch('/{proxy_id}', response_model=OkResponse)
async def patch_proxy(proxy_id: int, payload: ProxyUpdateRequest, db: Session = Depends(get_db), admin: dict = Depends(require_admin)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    update_proxy(db, proxy, payload, actor_id=str(admin.get('id', 1)))
    publish_event('proxy.updated', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/set-country', response_model=OkResponse)
async def set_country(proxy_id: int, payload: ProxySetCountryRequest, db: Session = Depends(get_db), admin: dict = Depends(require_admin)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    svc_set_country(db, proxy, payload.country_code, True, actor_id=str(admin.get('id', 1)))
    publish_event('proxy.country_set', {'proxy_id': proxy.id, 'country_code': payload.country_code})
    return OkResponse()


@router.post('/{proxy_id}/clear-country', response_model=OkResponse)
async def clear_country(proxy_id: int, db: Session = Depends(get_db), admin: dict = Depends(require_admin)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    svc_set_country(db, proxy, None, False, actor_id=str(admin.get('id', 1)))
    publish_event('proxy.country_cleared', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/enable', response_model=OkResponse)
async def enable_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    toggle_proxy(db, proxy, enabled=True)
    publish_event('proxy.enabled', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/disable', response_model=OkResponse)
async def disable_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    toggle_proxy(db, proxy, enabled=False)
    publish_event('proxy.disabled', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/quarantine', response_model=OkResponse)
async def quarantine_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    toggle_proxy(db, proxy, quarantine=True)
    publish_event('proxy.quarantined', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/unquarantine', response_model=OkResponse)
async def unquarantine_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    toggle_proxy(db, proxy, quarantine=False)
    publish_event('proxy.unquarantined', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/recheck', response_model=OkResponse)
async def recheck_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    proxy.status = 'checking'
    db.commit()
    publish_event('proxy.recheck_requested', {'proxy_id': proxy.id})
    return OkResponse()


@router.post('/{proxy_id}/speedtest', response_model=OkResponse)
async def speedtest_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db_get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')
    publish_event('proxy.speedtest_requested', {'proxy_id': proxy.id})
    return OkResponse()


@router.get('/{proxy_id}/checks')
async def proxy_checks(proxy_id: int, limit: int = Query(default=50, le=500), db: Session = Depends(get_db)):
    return {'items': [{'id': x.id, 'success': x.success, 'latency_ms': x.latency_ms, 'checked_at': x.checked_at, 'error_code': x.error_code} for x in recent_checks(db, proxy_id, limit)]}


@router.get('/{proxy_id}/speedtests')
async def proxy_speedtests(proxy_id: int, limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    return {'items': [{'id': x.id, 'success': x.success, 'partial_success': x.partial_success, 'download_mbps': float(x.download_mbps) if x.download_mbps is not None else None, 'upload_mbps': float(x.upload_mbps) if x.upload_mbps is not None else None, 'ping_ms': float(x.ping_ms) if x.ping_ms is not None else None, 'started_at': x.started_at} for x in recent_speedtests(db, proxy_id, limit)]}


@router.get('/{proxy_id}/geo-attempts')
async def proxy_geo_attempts(proxy_id: int, limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    return {'items': [{'id': x.id, 'success': x.success, 'detected_country_code': x.detected_country_code, 'source': x.source, 'attempted_at': x.attempted_at} for x in recent_geo_attempts(db, proxy_id, limit)]}


@router.get('/{proxy_id}/routing-usage')
async def proxy_routing_usage(proxy_id: int, db: Session = Depends(get_db)):
    return {'items': [], 'proxy_id': proxy_id}
