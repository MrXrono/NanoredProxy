from fastapi import FastAPI
from app.api.v1.router import api_router
from app.internal.gateway import router as gateway_internal_router

app = FastAPI(title="NanoredProxy API", version="0.1.0")
app.include_router(api_router, prefix="/api/v1")
app.include_router(gateway_internal_router)

@app.get("/")
async def root():
    return {"service": "nanoredproxy-backend", "status": "ok"}
