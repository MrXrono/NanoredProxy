def kill_requested(session_state: dict) -> bool:
    return bool(session_state.get('kill_requested'))
