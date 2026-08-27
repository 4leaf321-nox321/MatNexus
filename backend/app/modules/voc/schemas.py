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
    is_mine: bool
    """내가 낸 것인가. **이름으로 짐작하지 않는다** — 동명이인이면 남의 것에
    고치기 단추가 달린다. 화면은 이 값과 `reply` 로 서버와 같은 판단을 한다."""
    reply: str | None
    replied_at: datetime | None


class VocCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    page_path: str | None = Field(default=None, max_length=300)


class VocUpdateRequest(BaseModel):
    """낸 것을 고친다. **안 보낸 칸은 안 건드린다.**

    셋 다 실어 보내게 하면 화면이 한 칸만 고칠 때도 나머지를 다시 실어야 하고,
    그 사이에 남이 고친 값이 있으면 그것이 되돌아간다. `None` 은 「안 보냄」 이다 —
    제목·본문은 `min_length=1` 이라 「비웠다」 는 애초에 못 보낸다.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)


class VocReplyRequest(BaseModel):
    reply: str = Field(min_length=1)
    status: str = "resolved"
