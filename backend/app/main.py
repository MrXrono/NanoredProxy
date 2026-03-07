from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.internal.gateway import router as gateway_internal_router
from app.services.db_init import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title='NanoredProxy API', version='0.3.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(api_router, prefix='/api/v1')
app.include_router(gateway_internal_router)


@app.get('/')
async def root():
    return {'service': 'nanoredproxy-backend', 'status': 'ok'}
