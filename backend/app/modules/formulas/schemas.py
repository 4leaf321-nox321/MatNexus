"""계산식 API 스키마."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FormulaVariableIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    unit: str = "1"
    label: str | None = None


class FormulaParameterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    unit: str = "1"
    initial: float = 1.0
    lower: float | None = None
    upper: float | None = None


class FormulaResultIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    si_unit: str = "1"


class FormulaCreate(BaseModel):
    """계산식 하나. **자리(kind)에 따라 필요한 칸이 다르다** — 서버가 검사한다."""

    key: str = Field(min_length=2, max_length=60)
    """`formula.<key>` 의 뒷부분. 영문 snake_case. 한 번 나가면 안 바뀐다."""
    kind: str
    """`family`(적합식) · `scalar_step`(값 단계) · `column_step`(열 단계)."""
    label: str = Field(min_length=1, max_length=120)
    expression: str = Field(min_length=1, max_length=1000)
    describe: str | None = None
    variables: list[FormulaVariableIn] = Field(default_factory=list)
    """입력. 적합식은 `x` 하나, 값 단계는 앞 단계 스칼라들, 열 단계는 프레임 열들."""
    parameters: list[FormulaParameterIn] = Field(default_factory=list)
    """적합식만 — 구할 계수."""
    result: FormulaResultIn | None = None
    """단계만 — 내는 값의 이름·단위."""
    x_column: str | None = None
    y_column: str | None = None
    block: str | None = None
    applies_to: list[str] = Field(default_factory=list)


class FormulaUpdate(BaseModel):
    """안 보낸 것과 비운 것을 가른다 — 보낸 칸만 바뀐다. 식이 바뀌면 판이 오른다."""

    label: str | None = Field(default=None, min_length=1, max_length=120)
    expression: str | None = Field(default=None, min_length=1, max_length=1000)
    describe: str | None = None
    variables: list[FormulaVariableIn] | None = None
    parameters: list[FormulaParameterIn] | None = None
    result: FormulaResultIn | None = None
    x_column: str | None = None
    y_column: str | None = None
    block: str | None = None
    applies_to: list[str] | None = None
    enabled: bool | None = None


class FormulaOut(BaseModel):
    id: uuid.UUID
    key: str
    registry_key: str
    kind: str
    kind_label: str
    label: str
    expression: str
    describe: str | None
    variables: list[dict[str, Any]]
    parameters: list[dict[str, Any]]
    result: dict[str, Any] | None
    x_column: str | None
    y_column: str | None
    block: str | None
    applies_to: list[str]
    version: int
    enabled: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    references: dict[str, int] = Field(default_factory=dict)
    """이 식을 쓰는 레시피·처리 결과·카드 수. 0 이 아니면 못 지운다."""


class FormulaPreviewIn(BaseModel):
    """저장 전에 **실제 채택 결과 하나로** 돌려 본다 (D6)."""

    spec: FormulaCreate
    result_id: uuid.UUID
    """처리 결과 id — 적합식은 그 곡선에 맞추고, 열 단계는 그 열로 계산하고, 값 단계는
    그 스칼라를 받는다."""


class FormulaPreviewOut(BaseModel):
    kind: str
    ok: bool
    message: str
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    """적합식: 구한 계수와 적합도."""
    r_squared: float | None = None
    value: float | None = None
    """값 단계: 나온 값."""
    sample: list[dict[str, float]] = Field(default_factory=list)
    """열 단계: 앞 몇 점 — 입력 열과 새 열."""
    notes: list[str] = Field(default_factory=list)


class FormulaVocabularyOut(BaseModel):
    """식을 적을 때 고를 수 있는 것 — 열·스칼라·블록·함수. 계약서와 같은 어휘."""

    columns: list[dict[str, str]]
    scalars: list[dict[str, str]]
    blocks: list[dict[str, str]]
    functions: list[str]
    constants: list[str]
