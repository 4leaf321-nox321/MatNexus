"""VOC API 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VocOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    status: str
    page_path: str | None
    created_at: datetime
    created_by: str | None
    """작성자 이름. 누가 겪은 문제인지 알아야 되물을 수 있다."""
    reply: str | None
    replied_at: datetime | None


class VocCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    page_path: str | None = Field(default=None, max_length=300)


class VocReplyRequest(BaseModel):
    reply: str = Field(min_length=1)
    status: str = "resolved"
