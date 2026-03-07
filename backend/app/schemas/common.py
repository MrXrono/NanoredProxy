from typing import Any

from pydantic import BaseModel


class OkResponse(BaseModel):
    ok: bool = True


class ListResponse(BaseModel):
    items: list[Any]
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
