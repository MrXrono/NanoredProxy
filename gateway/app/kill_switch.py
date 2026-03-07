from app.auth import session_state


async def kill_requested(session_id: str) -> bool:
    state = await session_state(session_id)
    return bool(state.get('kill_requested'))
