from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.models import SchedulerState
from app.schemas.common import OkResponse
from app.services.runtime_state import get_worker_runtime, set_worker_runtime

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('')
async def list_workers(db: Session = Depends(get_db)):
    items = db.scalars(select(SchedulerState).order_by(SchedulerState.worker_name.asc())).all()
    out = []
    for w in items:
        runtime = get_worker_runtime(w.worker_name)
        out.append({'worker_name': w.worker_name, 'status': runtime.get('status', w.status), 'last_started_at': w.last_started_at, 'last_finished_at': w.last_finished_at, 'pause_reason': runtime.get('pause_reason', w.pause_reason)})
    return {'items': out}


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
    set_worker_runtime(worker_name, 'paused', worker.pause_reason)
    db.commit()
    return OkResponse()


@router.post('/{worker_name}/resume', response_model=OkResponse)
async def resume_worker(worker_name: str, db: Session = Depends(get_db)):
    worker = _worker(db, worker_name)
    worker.status = 'idle'
    worker.pause_reason = None
    set_worker_runtime(worker_name, 'idle', None)
    db.commit()
    return OkResponse()


@router.post('/{worker_name}/run-now', response_model=OkResponse)
async def run_worker(worker_name: str, db: Session = Depends(get_db)):
    worker = _worker(db, worker_name)
    worker.status = 'running'
    worker.last_started_at = datetime.now(timezone.utc)
    set_worker_runtime(worker_name, 'running', None)
    db.commit()
    return OkResponse()
