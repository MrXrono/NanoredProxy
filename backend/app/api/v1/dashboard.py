from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.services.dashboard_service import get_summary

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('/summary')
async def summary(db: Session = Depends(get_db)):
    return get_summary(db)


@router.get('/charts')
async def charts(period: str = '24h', db: Session = Depends(get_db)):
    return {'period': period, 'traffic_by_hour': [], 'sessions_by_hour': [], 'latency_by_hour': [], 'speed_by_day': [], 'country_distribution': []}
