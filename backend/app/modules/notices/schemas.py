"""공지 API 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NoticeOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    is_published: bool
    is_popup: bool
    created_at: datetime
    published_at: datetime | None
    is_read: bool


class NoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    is_popup: bool = False
    is_published: bool = True


class NoticeUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    is_popup: bool | None = None
    is_published: bool | None = None
