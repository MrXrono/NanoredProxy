from fastapi import APIRouter, UploadFile, File
from app.schemas.proxy import ProxyImportTextRequest, ProxySetCountryRequest, ProxyUpdateRequest
from app.schemas.common import OkResponse
from app.services.proxy_parser import parse_proxy_text

router = APIRouter()
_FAKE_DB = []

@router.get('')
async def list_proxies():
    return {"items": _FAKE_DB, "total": len(_FAKE_DB), "page": 1, "page_size": 50}

@router.post('/import/text')
async def import_text(payload: ProxyImportTextRequest):
    items = parse_proxy_text(payload.text)
    _FAKE_DB.extend(items)
    return {"ok": True, "parsed": len(items), "inserted": len(items), "duplicates": 0, "queued_for_check": len(items)}

@router.post('/import/file')
async def import_file(file: UploadFile = File(...)):
    content = (await file.read()).decode('utf-8', errors='ignore')
    items = parse_proxy_text(content)
    _FAKE_DB.extend(items)
    return {"ok": True, "parsed": len(items), "inserted": len(items), "duplicates": 0}

@router.get('/{proxy_id}')
async def get_proxy(proxy_id: int):
    return {"id": proxy_id, "status": "new"}

@router.patch('/{proxy_id}', response_model=OkResponse)
async def patch_proxy(proxy_id: int, payload: ProxyUpdateRequest):
    return OkResponse()

@router.post('/{proxy_id}/set-country', response_model=OkResponse)
async def set_country(proxy_id: int, payload: ProxySetCountryRequest):
    return OkResponse()

@router.post('/{proxy_id}/clear-country', response_model=OkResponse)
async def clear_country(proxy_id: int):
    return OkResponse()

@router.post('/{proxy_id}/enable', response_model=OkResponse)
async def enable_proxy(proxy_id: int):
    return OkResponse()

@router.post('/{proxy_id}/disable', response_model=OkResponse)
async def disable_proxy(proxy_id: int):
    return OkResponse()

@router.post('/{proxy_id}/quarantine', response_model=OkResponse)
async def quarantine_proxy(proxy_id: int):
    return OkResponse()

@router.post('/{proxy_id}/unquarantine', response_model=OkResponse)
async def unquarantine_proxy(proxy_id: int):
    return OkResponse()

@router.post('/{proxy_id}/recheck', response_model=OkResponse)
async def recheck_proxy(proxy_id: int):
    return OkResponse()

@router.post('/{proxy_id}/speedtest', response_model=OkResponse)
async def speedtest_proxy(proxy_id: int):
    return OkResponse()

@router.get('/{proxy_id}/checks')
async def proxy_checks(proxy_id: int):
    return {"items": []}

@router.get('/{proxy_id}/speedtests')
async def proxy_speedtests(proxy_id: int):
    return {"items": []}

@router.get('/{proxy_id}/geo-attempts')
async def proxy_geo_attempts(proxy_id: int):
    return {"items": []}

@router.get('/{proxy_id}/routing-usage')
async def proxy_routing_usage(proxy_id: int):
    return {"items": []}
