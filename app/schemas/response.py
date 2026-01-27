from typing import Any
from pydantic import BaseModel


class Meta(BaseModel):
    offset: int
    limit: int
    total: int


class OkResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any


class ListResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: list[Any]
    meta: Meta


class ErrorResponse(BaseModel):
    code: int
    message: str
    details: Any | None = None
