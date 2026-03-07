from fastapi import APIRouter

router = APIRouter()

SAMPLE = """# Unified proxychains profiles
[profile:all]
socks5 127.0.0.1 1080 all all
"""

@router.get('/proxychains')
async def get_proxychains(download: bool = False):
    return {"filename": "proxychains-all-countries.conf", "content": SAMPLE, "download": download}

@router.get('/proxychains/preview')
async def proxychains_preview():
    return {"content": SAMPLE}
