from fastapi import APIRouter

router = APIRouter()

@router.get('/global')
async def global_stats():
    return {"traffic": {}, "sessions": {}, "proxies": {}}

@router.get('/traffic')
async def traffic_stats(scope_type: str = 'global', scope_id: str | None = None):
    return {"scope_type": scope_type, "scope_id": scope_id, "items": []}

@router.get('/countries')
async def country_stats():
    return {"items": []}

@router.get('/accounts')
async def account_stats():
    return {"items": []}

@router.get('/proxies/top')
async def top_proxies(limit: int = 20):
    return {"items": [], "limit": limit}

@router.get('/proxies/worst')
async def worst_proxies(limit: int = 20):
    return {"items": [], "limit": limit}

@router.get('/ab')
async def ab_stats():
    return {"A": {"sessions": 0}, "B": {"sessions": 0}}
