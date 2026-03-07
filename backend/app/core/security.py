import time
import jwt
from fastapi import HTTPException, status
from app.core.config import settings

ALGO = "HS256"

def create_access_token(subject: str) -> str:
    payload = {"sub": subject, "iat": int(time.time()), "exp": int(time.time()) + 60 * 60 * 12}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGO)

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGO])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
