import httpx
from app.config import BACKEND_URL

async def resolve_auth(username: str, password: str, client_ip: str):
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BACKEND_URL}/internal/v1/gateway/auth-resolve", json={"username": username, "password": password, "client_ip": client_ip})
        return resp.json()
