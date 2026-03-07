import time
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

ALGO = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(subject: str) -> str:
    payload = {"sub": subject, "iat": int(time.time()), "exp": int(time.time()) + 60 * 60 * 12}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGO)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGO])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_current_admin(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing bearer token')
    payload = verify_token(credentials.credentials)
    subject = payload.get('sub')
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token subject')
    return {'username': subject, 'id': 1}


def require_admin(admin: Annotated[dict, Depends(get_current_admin)]):
    return admin
