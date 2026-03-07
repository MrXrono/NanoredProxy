from fastapi import APIRouter
from app.schemas.common import OkResponse

router = APIRouter()

@router.get('')
async def list_sessions():
    return {"items": [], "total": 0}

@router.get('/{session_id}')
async def get_session(session_id: str):
    return {"id": session_id, "status": "active"}

@router.get('/{session_id}/connections')
async def get_session_connections(session_id: str):
    return {"items": []}

@router.get('/{session_id}/routing-events')
async def get_session_routing_events(session_id: str):
    return {"items": []}

@router.post('/{session_id}/kill', response_model=OkResponse)
async def kill_session(session_id: str, payload: dict | None = None):
    return OkResponse()

@router.post('/{session_id}/disconnect-connections', response_model=OkResponse)
async def disconnect_connections(session_id: str):
    return OkResponse()
