import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.redis import EVENT_CHANNEL, redis_pubsub
from app.core.security import verify_token

router = APIRouter()


@router.websocket('/ws/events')
async def websocket_events(websocket: WebSocket, token: str = Query(...)):
    verify_token(token)
    await websocket.accept()
    pubsub = redis_pubsub()
    if pubsub is None:
        await websocket.send_json({'type': 'system.error', 'payload': {'message': 'redis unavailable'}})
        await websocket.close(code=1011)
        return
    pubsub.subscribe(EVENT_CHANNEL)
    await websocket.send_json({'type': 'system.connected', 'payload': {'channel': EVENT_CHANNEL}})
    try:
        while True:
            message = pubsub.get_message(timeout=1.0)
            if message and message.get('type') == 'message' and message.get('data'):
                try:
                    payload = json.loads(message['data'])
                except Exception:
                    payload = {'type': 'system.raw', 'payload': {'data': message['data']}}
                await websocket.send_json(payload)
            else:
                await websocket.send_json({'type': 'system.heartbeat', 'payload': {}})
                await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            pubsub.unsubscribe(EVENT_CHANNEL)
            pubsub.close()
        except Exception:
            pass
