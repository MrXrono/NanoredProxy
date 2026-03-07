from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import SchedulerState
from app.schemas.common import OkResponse

router = APIRouter()


@router.get('')
async def list_workers(db: Session = Depends(get_db)):
    items = db.scalars(select(SchedulerState).order_by(SchedulerState.worker_name.asc())).all()
    return {'items': [{'worker_name': w.worker_name, 'status': w.status, 'last_started_at': w.last_started_at, 'last_finished_at': w.last_finished_at, 'pause_reason': w.pause_reason} for w in items]}


def _worker(db: Session, worker_name: str) -> SchedulerState:
    worker = db.get(SchedulerState, worker_name)
    if not worker:
        raise HTTPException(status_code=404, detail='Worker not found')
    return worker


@router.post('/{worker_name}/pause', response_model=OkResponse)
async def pause_worker(worker_name: str, db: Session = Depends(get_db)):
    worker = _worker(db, worker_name)
    worker.status = 'paused'
    worker.pause_reason = 'paused by admin'
    db.commit()
    return OkResponse()


@router.post('/{worker_name}/resume', response_model=OkResponse)
async def resume_worker(worker_name: str, db: Session = Depends(get_db)):
    worker = _worker(db, worker_name)
    worker.status = 'idle'
    worker.pause_reason = None
    db.commit()
    return OkResponse()


@router.post('/{worker_name}/run-now', response_model=OkResponse)
async def run_worker(worker_name: str, db: Session = Depends(get_db)):
    worker = _worker(db, worker_name)
    worker.status = 'running'
    worker.last_started_at = datetime.utcnow()
    db.commit()
    return OkResponse()
