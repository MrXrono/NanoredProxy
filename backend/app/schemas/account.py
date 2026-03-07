from pydantic import BaseModel


class AccountCreate(BaseModel):
    username: str
    password: str
    account_type: str
    country_code: str | None = None
    is_enabled: bool = True


class AccountPatch(BaseModel):
    password: str | None = None
    is_enabled: bool | None = None
    country_code: str | None = None
