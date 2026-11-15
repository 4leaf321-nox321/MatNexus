"""휴지통 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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

    files_cleaned: int = 0
    """함께 돌아올 시험 가운데 **보존기간이 지나 파일이 정리된** 것의 수. 되살리기를 막지는
    않는다 — 그 시험은 곡선 없이 돌아온다(`services` 머리말)."""

    notice: str | None = None
    """그 안내 한 줄(「파일이 정리된 시험 N건 — …」). 없으면 비운다. 화면이 되살리기 전에
    묻는다."""


class TrashDoneOut(BaseModel):
    """되살렸거나 영영 지운 결과."""

    name: str
    counts: dict[str, int]
    said: str
    """`시료 2건, 시편 6건` — 화면이 그대로 보여 준다."""
    files_cleaned: int = 0
    """되살린 시험 가운데 파일이 정리돼 **곡선 없이 돌아온** 것. 영구 삭제는 0."""
    notice: str | None = None
    """그 안내 한 줄 — 되살리고 나서도 화면이 그대로 보여 준다."""


class TrashRef(BaseModel):
    """지울 줄 하나를 가리킨다."""

    kind: str
    id: uuid.UUID


class TrashPurgeManyIn(BaseModel):
    """고른 줄을 한꺼번에 영영 지운다.

    **`confirm` 을 여기서도 받는다.** 한 줄짜리와 같은 이유다 — 이 길은 API 로도
    열려 있고, 스크립트가 실수로 부르면 그 데이터는 돌아오지 않는다. 여럿이라
    잘못 불렀을 때 잃는 것이 더 크다.
    """

    items: list[TrashRef] = Field(min_length=1, max_length=200)
    """**상한을 서버가 강제한다.** 한 번에 지우는 수가 늘수록 트랜잭션이 길어지고,
    그 안에서 곡선 파일까지 지우므로 도중에 끊기면 정리가 어렵다."""
    confirm: bool = False


class TrashPurgedManyOut(BaseModel):
    """여럿을 지운 결과."""

    requested: int
    purged: int
    skipped: int
    """**앞서 지운 것에 딸려 이미 사라진** 줄. 재료와 그 아래 시료를 함께 고르면
    나온다 — 사고가 아니다."""
    counts: dict[str, int]
    said: str
