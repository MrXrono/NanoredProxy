from fastapi import APIRouter
from app.schemas.common import OkResponse

router = APIRouter()

@router.get('')
async def list_accounts():
    return {"items": [{"id": 1, "username": "all", "password": "all", "account_type": "all", "country_code": None, "is_enabled": True, "active_sessions": 0, "working_proxies": 0}]}

@router.get('/{account_id}')
async def get_account(account_id: int):
    return {"id": account_id}

@router.post('')
async def create_account(payload: dict):
    return {"ok": True, "account": payload}

@router.patch('/{account_id}', response_model=OkResponse)
async def patch_account(account_id: int, payload: dict):
    return OkResponse()

@router.post('/{account_id}/enable', response_model=OkResponse)
async def enable_account(account_id: int):
    return OkResponse()

@router.post('/{account_id}/disable', response_model=OkResponse)
async def disable_account(account_id: int):
    return OkResponse()

@router.post('/reconcile', response_model=OkResponse)
async def reconcile_accounts():
    return OkResponse()
