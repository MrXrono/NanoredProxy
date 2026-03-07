from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_admin
from app.models import Account
from app.schemas.account import AccountCreate, AccountPatch
from app.schemas.common import OkResponse
from app.services.account_service import list_accounts as svc_list_accounts, reconcile_accounts as svc_reconcile_accounts

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get('')
async def list_accounts(db: Session = Depends(get_db)):
    items = svc_list_accounts(db)
    return {'items': items, 'total': len(items)}


@router.get('/{account_id}')
async def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail='Account not found')
    return {'id': account.id, 'username': account.username, 'password': account.password, 'account_type': account.account_type, 'country_code': account.country_code, 'is_enabled': account.is_enabled}


@router.post('')
async def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return {'ok': True, 'account': {'id': account.id, 'username': account.username}}


@router.patch('/{account_id}', response_model=OkResponse)
async def patch_account(account_id: int, payload: AccountPatch, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail='Account not found')
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    db.commit()
    return OkResponse()


@router.post('/{account_id}/enable', response_model=OkResponse)
async def enable_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail='Account not found')
    account.is_enabled = True
    db.commit()
    return OkResponse()


@router.post('/{account_id}/disable', response_model=OkResponse)
async def disable_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail='Account not found')
    account.is_enabled = False
    db.commit()
    return OkResponse()


@router.post('/reconcile', response_model=OkResponse)
async def reconcile_accounts(db: Session = Depends(get_db)):
    svc_reconcile_accounts(db)
    return OkResponse()
