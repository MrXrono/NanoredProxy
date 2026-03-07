from fastapi import APIRouter
from app.schemas.common import OkResponse

router = APIRouter()
_SETTINGS = {
    "latency_threshold_ms": 1500,
    "speedtest_interval_hours": 6,
    "speedtest_pause_between_tests_minutes": 5,
    "speedtest_resume_after_idle_minutes": 10,
    "quarantine_batch_size": 10,
    "quarantine_window_size": 5,
    "quarantine_pause_seconds": 2,
}

@router.get('')
async def get_settings():
    return _SETTINGS

@router.patch('', response_model=OkResponse)
async def patch_settings(payload: dict):
    _SETTINGS.update(payload)
    return OkResponse()
