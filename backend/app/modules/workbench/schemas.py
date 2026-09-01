"""워크벤치 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.workbench.models import ITEM_KINDS

#: 한 작업에 담을 수 있는 수. **막는 값이 아니라 사고를 막는 값이다** — 실수로
#: 전부 고른 채 담으면 화면이 수백 줄을 그린다.
MAX_ITEMS = 500

KIND_PATTERN = "^(" + "|".join(ITEM_KINDS) + ")$"


class RunCreateRequest(BaseModel):
    workflow_key: str = Field(min_length=1, max_length=50)
    """어떤 일인가. **뜻은 화면이 안다**(ADR 0025)."""
    title: str = Field(min_length=1, max_length=200)
    note: str | None = None


class RunPatchRequest(BaseModel):
    """부분 수정. **안 보낸 것과 비운 것을 구별한다** — 안 그러면 저장할 때마다
    값이 지워진다(CLAUDE.md 의 규칙)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(running|finished|dropped)$")
    steps: dict[str, Any] | None = None
    note: str | None = None


class ItemAddRequest(BaseModel):
    """담기. **여럿을 한 번에** — 목록에서 골라 담는 일이라 한 건씩이면 왕복이 는다."""

    kind: str = Field(pattern=KIND_PATTERN)
    target_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_ITEMS)
    note: str | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    target_id: uuid.UUID
    label: str
    """사람이 읽을 이름. 사라진 것은 「사라졌습니다」 로 온다."""
    detail: str | None = None
    """한 줄 더. 시험이면 시편·상태, 카드면 재료·상태."""
    missing: bool = False
    """**가리키던 것이 사라졌다.** 담아 두는 것은 메모라서 대상이 지워질 수 있고,
    그 사실이 보여야 한다(ADR 0025) — 줄이 조용히 사라지면 「여덟 건이 왜 일곱이지」
    가 된다."""
    note: str | None = None
    added_at: datetime


class RunOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    owner_id: uuid.UUID | None
    owner_name: str | None
    workflow_key: str
    title: str
    status: str
    steps: dict[str, Any]
    note: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class RunDetailOut(RunOut):
    items: list[ItemOut]
