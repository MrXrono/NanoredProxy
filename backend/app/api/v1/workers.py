from fastapi import APIRouter
from app.schemas.common import OkResponse

router = APIRouter()

@router.get('')
async def list_workers():
    return {"items": [
        {"worker_name": "availability_checker", "status": "idle"},
        {"worker_name": "speedtest_runner", "status": "idle"},
        {"worker_name": "geo_resolver", "status": "idle"},
        {"worker_name": "aggregate_recalculator", "status": "idle"},
        {"worker_name": "account_reconciler", "status": "idle"},
    ]}

@router.post('/{worker_name}/pause', response_model=OkResponse)
async def pause_worker(worker_name: str):
    return OkResponse()

@router.post('/{worker_name}/resume', response_model=OkResponse)
async def resume_worker(worker_name: str):
    return OkResponse()

@router.post('/{worker_name}/run-now', response_model=OkResponse)
async def run_worker(worker_name: str):
    return OkResponse()
