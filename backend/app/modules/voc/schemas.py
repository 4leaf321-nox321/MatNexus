"""VOC API 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class VocOut(BaseModel):
    """게시판 한 줄. **상세는 `VocDetailOut`** — 목록에 본문과 이력을 다 실으면
    100건짜리 화면이 느려지고, 그 느림은 목록에서만 보인다."""

    id: uuid.UUID
    seq: int
    """게시판 번호. 「VOC 12번」."""
    title: str
    status: str
    status_label: str
    """상태를 사람이 읽는 말. 화면이 표를 갖지 않는다 — 상태가 늘면 서버가 안다."""
    page_path: str | None
    created_at: datetime
    created_by: str | None
    """낸 사람. 누가 겪은 문제인지 알아야 되물을 수 있다."""
    status_at: datetime
    """지금 상태가 된 때 — 목록의 「최근 처리」."""
    status_by: str | None
    """지금 상태로 옮긴 사람."""
    is_mine: bool
    """내가 낸 것인가. **이름으로 짐작하지 않는다** — 동명이인이면 남의 것에
    고치기 단추가 달린다."""
    can_edit: bool
    """고치거나 지울 수 있는가. 서버가 정한다(`_editable`) — 화면이 규칙을 두 벌로
    갖지 않게."""
    event_count: int
    """등록을 뺀 이벤트 수. 목록에서 「말이 오간 건」 을 구별한다."""


class VocStatusOut(BaseModel):
    key: str
    label: str


class VocEventOut(BaseModel):
    id: uuid.UUID
    at: datetime
    by: str | None
    from_status: str | None
    to_status: str
    to_status_label: str
    note: str | None


class VocDetailOut(VocOut):
    body: str
    events: list[VocEventOut]
    """등록부터 지금까지, 시간순."""
    allowed: list[str]
    """**이 사람이 지금 옮길 수 있는 상태.** 관리자와 낸 사람이 다르고 지금 상태에
    따라 다르다 — 화면이 규칙을 외우면 서버와 어긋나는 날이 온다."""
    allowed_labels: dict[str, str]
    can_delete_events: bool = False
    """이력 한 줄을 지울 수 있는가 — **시스템 관리자만.** 상태를 잘못 옮긴 줄을
    되돌릴 길이 없었다(VOC 2026-09-13). 등록 줄은 못 지운다."""
    """`allowed` 의 각 상태로 옮기는 단추에 적을 말. 「해결」 이 아니라 「해결로 옮김」
    처럼 동사가 붙는다."""
    note_required: list[str]
    """`allowed` 가운데 말을 반드시 적어야 하는 것."""


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


class VocEventRequest(BaseModel):
    """상태를 옮기거나 말을 보탠다. **둘 중 하나는 있어야 한다.**

    `status` 를 비우면 댓글이다. `note` 를 비우고 상태만 옮기는 것은 상태에 따라
    막힌다(`NOTE_REQUIRED`) — 「해결」 만 찍힌 건은 무엇이 바뀌었는지 아무도 모른다.
    """

    status: str | None = None
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _something(self) -> VocEventRequest:
        if self.status is None and not (self.note or "").strip():
            raise ValueError("상태를 옮기거나 말을 적어야 합니다.")
        return self
