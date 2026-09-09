"""감사 로그 응답."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    """`card.published` 처럼 `<대상>.<한 일>`. **과거형이다** — 일어난 일의 기록이다."""
    actor_id: uuid.UUID | None
    actor_label: str
    """그때의 사람 이름. **계정이 지워져도 남는다.**"""
    target_table: str
    target_id: uuid.UUID | None
    target_label: str
    workspace_id: uuid.UUID | None
    changes: dict[str, Any]
    """`{키: {"before": ..., "after": ...}}`. 바뀐 것만 담긴다."""
    reason: str | None
    request_id: str | None
    """접근 로그·파일 로그와 잇는 끈."""
    client: str = ""
    """**어느 길로 들어온 변경인가** — `mcp` · `pylon` · `script`, 빈 값이면 화면.

    사람이 한 것과 AI 가 한 것을 가르는 표시다."""
    created_at: datetime
