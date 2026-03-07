from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.internal.gateway import router as gateway_internal_router
from app.services.db_init import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title='NanoredProxy API', version='0.2.0', lifespan=lifespan)
app.include_router(api_router, prefix='/api/v1')
app.include_router(gateway_internal_router)


@app.get('/')
async def root():
    return {'service': 'nanoredproxy-backend', 'status': 'ok'}
