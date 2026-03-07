from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProxyImportTextRequest(BaseModel):
    text: str


class ProxySetCountryRequest(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)


class ProxyUpdateRequest(BaseModel):
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    notes: Optional[str] = None


class ProxyRead(BaseModel):
    id: int
    host: str
    port: int
    has_auth: bool
    status: str
    country_code: str | None = None
    country_source: str | None = None
    country_manual_override: bool = False
    is_enabled: bool = True
    is_quarantined: bool = False
    avg_latency_day_ms: float | None = None
    avg_download_day_mbps: float | None = None
    avg_upload_day_mbps: float | None = None
    stability_score: float | None = None
    composite_score: float | None = None
    last_checked_at: datetime | None = None


class ProxyImportResponse(BaseModel):
    ok: bool = True
    parsed: int
    inserted: int
    duplicates: int
    queued_for_check: int | None = None
