from fastapi import APIRouter, status
from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.redis import get_redis

router = APIRouter()


@router.get('/live')
async def live():
    return {'status': 'ok', 'service': 'nanoredproxy-backend'}


@router.get('/ready')
async def ready():
    db_ok = False
    redis_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text('select 1'))
            db_ok = True
    except Exception:
        db_ok = False
    try:
        redis = get_redis()
        if redis is not None:
            redis.ping()
            redis_ok = True
    except Exception:
        redis_ok = False
    payload = {'status': 'ok' if db_ok and redis_ok else 'degraded', 'checks': {'database': db_ok, 'redis': redis_ok}}
    if db_ok and redis_ok:
        return payload
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
