from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.config_service import build_proxychains_bundle

router = APIRouter()


@router.get('/proxychains')
async def get_proxychains(download: bool = False, db: Session = Depends(get_db)):
    content = build_proxychains_bundle(db)
    if download:
        return PlainTextResponse(content=content, media_type='text/plain', headers={'Content-Disposition': 'attachment; filename=proxychains-all-countries.conf'})
    return {'filename': 'proxychains-all-countries.conf', 'content': content}


@router.get('/proxychains/preview')
async def proxychains_preview(db: Session = Depends(get_db)):
    return {'content': build_proxychains_bundle(db)}
