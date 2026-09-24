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
    created_by: str | None = None
    """쓴 사람(표시 이름). 계정이 지워졌거나 배포가 넣은 글이면 비어 있다."""
    from_release: bool = False
    """**배포에 실려 온 안내**인가(`seeds/notices`). 쓴 사람이 없는 글이라, 화면이 「알 수
    없음」 대신 무엇이라 적을지 여기서 안다."""


class NoticeUnreadOut(BaseModel):
    """안 읽은 공지 수 — **발행된 것만** 센다(초안은 아직 아무에게도 안 알렸다)."""

    unread: int


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
