from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, require_admin
from app.models import AdminUser
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.common import OkResponse

router = APIRouter()


@router.post('/login', response_model=LoginResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    admin = db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    now = datetime.now(timezone.utc)
    if admin:
        admin.last_login_at = now
    token = create_access_token(payload.username)
    db.commit()
    return LoginResponse(access_token=token, admin={"username": payload.username, "id": 1})


@router.post('/logout', response_model=OkResponse)
async def logout(_admin: dict = Depends(require_admin)):
    return OkResponse()


@router.get('/me')
async def me(admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.scalar(select(AdminUser).where(AdminUser.username == admin['username']))
    return {"id": 1, "username": admin['username'], "is_active": True, 'last_login_at': row.last_login_at if row else None}
