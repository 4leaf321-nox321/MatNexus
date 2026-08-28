"""묶음 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

#: 한 번에 묶을 수 있는 시험 수. 시편 수십 장이 정상인 물성이 있다(피로).
MAX_MEMBERS = 200


class GroupingSpecOut(BaseModel):
    """고를 수 있는 묶음 하나. **화면이 목록을 적어 두지 않게 한다.**"""

    id: str
    label: str
    applies_to: list[str]
    params: list[dict[str, Any]]
    makes_values: list[dict[str, Any]]


class GroupCreateRequest(BaseModel):
    plugin_id: str
    run_ids: list[uuid.UUID] = Field(min_length=2, max_length=MAX_MEMBERS)
    """**둘 이상이다.** 하나를 「묶었다」 고 부르면 그 결과가 묶음인지 한 건인지
    나중에 구별할 수 없다."""
    options: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class GroupResultOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    plugin_id: str
    plugin_version: str
    options: dict[str, Any]

    members: list[dict[str, Any]]
    used: list[str]
    """**실제로 쓴 것.** 고른 것과 다를 수 있다 — 대표를 고르면 하나만 쓴다."""

    values: dict[str, float]
    detail: dict[str, Any]
    warnings: list[str]
    note: str | None
    created_at: datetime
