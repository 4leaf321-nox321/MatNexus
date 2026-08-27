"""휴지통 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TrashItemOut(BaseModel):
    """지운 것 한 줄."""

    kind: str
    """`material` · `sample` · `specimen` · `test_run`."""
    kind_label: str
    """사람이 읽는 종류 이름. **서버가 준다** — 화면이 표를 또 들면 둘이 갈라진다."""
    id: uuid.UUID
    name: str
    deleted_at: datetime
    workspace_id: uuid.UUID | None

    below: dict[str, int]
    """이 줄을 되살리면 **함께 돌아오는 것.** 사람이 누를 근거다."""

    blocked: str | None
    """되살릴 수 없으면 그 이유. **버튼을 그냥 끄지 않는다** — 왜 안 되는지가
    안 보이면 사람은 그 자리에서 막힌다(처리 화면에서 같은 실패를 했다)."""


class TrashDoneOut(BaseModel):
    """되살렸거나 영영 지운 결과."""

    name: str
    counts: dict[str, int]
    said: str
    """`시료 2건, 시편 6건` — 화면이 그대로 보여 준다."""
