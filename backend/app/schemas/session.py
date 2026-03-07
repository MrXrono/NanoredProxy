from pydantic import BaseModel


class SessionKillRequest(BaseModel):
    reason: str | None = None
