from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import SystemSetting
from app.schemas.common import OkResponse

router = APIRouter()


@router.get('')
async def get_settings(db: Session = Depends(get_db)):
    rows = db.scalars(select(SystemSetting).order_by(SystemSetting.key.asc())).all()
    return {row.key: row.value for row in rows}


@router.patch('', response_model=OkResponse)
async def patch_settings(payload: dict, db: Session = Depends(get_db)):
    for key, value in payload.items():
        row = db.get(SystemSetting, key)
        if row:
            row.value = value if isinstance(value, dict) else {'value': value}
    db.commit()
    return OkResponse()
