from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.common import OkResponse

router = APIRouter()

@router.post('/login', response_model=LoginResponse)
async def login(payload: LoginRequest):
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = create_access_token(payload.username)
    return LoginResponse(access_token=token, admin={"username": payload.username, "id": 1})

@router.post('/logout', response_model=OkResponse)
async def logout():
    return OkResponse()

@router.get('/me')
async def me():
    return {"id": 1, "username": settings.admin_username, "is_active": True}
