from fastapi import APIRouter

router = APIRouter()

@router.get('/summary')
async def summary():
    return {
        "proxies_total": 0,
        "proxies_online": 0,
        "proxies_degraded": 0,
        "proxies_offline": 0,
        "proxies_quarantine": 0,
        "country_unknown": 0,
        "accounts_total": 1,
        "accounts_enabled": 1,
        "active_sessions": 0,
        "active_connections": 0,
        "traffic_bytes_in": 0,
        "traffic_bytes_out": 0,
    }

@router.get('/charts')
async def charts(period: str = '24h'):
    return {"period": period, "traffic_by_hour": [], "sessions_by_hour": [], "latency_by_hour": [], "speed_by_day": [], "country_distribution": []}
