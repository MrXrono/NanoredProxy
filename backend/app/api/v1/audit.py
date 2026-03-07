from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AuditLog

router = APIRouter()


@router.get('/logs')
async def audit_logs(limit: int = 100, db: Session = Depends(get_db)):
    items = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return {'items': [{'id': x.id, 'actor_type': x.actor_type, 'actor_id': x.actor_id, 'action': x.action, 'target_type': x.target_type, 'target_id': x.target_id, 'payload': x.payload, 'created_at': x.created_at} for x in items]}
