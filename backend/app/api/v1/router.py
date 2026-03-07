from fastapi import APIRouter
from app.api.v1 import admin_auth, dashboard, proxies, accounts, sessions, stats, config, workers, settings, audit

api_router = APIRouter()
api_router.include_router(admin_auth.router, prefix="/admin/auth", tags=["admin-auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(proxies.router, prefix="/proxies", tags=["proxies"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(workers.router, prefix="/system/workers", tags=["workers"])
api_router.include_router(settings.router, prefix="/system/settings", tags=["settings"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
