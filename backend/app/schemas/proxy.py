from pydantic import BaseModel
from typing import Optional

class ProxyImportTextRequest(BaseModel):
    text: str

class ProxySetCountryRequest(BaseModel):
    country_code: str

class ProxyUpdateRequest(BaseModel):
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    notes: Optional[str] = None
