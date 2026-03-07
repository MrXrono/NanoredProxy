from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.services.dashboard_service import get_charts, get_summary

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('/summary')
async def summary(db: Session = Depends(get_db)):
    return get_summary(db)


@router.get('/charts')
async def charts(period: str = '24h', db: Session = Depends(get_db)):
    return get_charts(db, period=period)
