"""처리 API 의 요청·응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# --- 처리 (Phase 3) ---------------------------------------------------------


class StepParamOut(BaseModel):
    """단계 하나의 입력 칸. **화면의 폼 필드가 여기서 생성된다.**

    프론트에 목록을 하드코딩하지 않는 이유: 계산을 추가할 때 두 곳을 고쳐야 하고,
    그러면 한 곳을 빠뜨린다. `matcore.ParamSpec` 을 그대로 내보낸다.
    """

    name: str
    label: str
    type: str
    default: Any = None
    choices: list[str] = []
    choice_labels: dict[str, str] = {}
    """값 → 사람이 읽는 이름. 값 자체는 레시피에 저장되는 계약이라 안 바꾼다."""
    unit: str | None = None
    dimension: str | None = None
    """단위만으로 못 가르는 것을 가른다 — 변형률은 %, tan δ 는 그대로."""
    help: str | None = None
    when: dict[str, list[str]] = {}
    """이 칸이 쓰이는 조건. 비어 있으면 늘 쓰인다."""


class ProcessingStepOut(BaseModel):
    id: str
    label: str
    version: str
    """계산이 바뀌면 올라간다. 결과에 기록해 "이 값은 v1 계산이다" 를 남긴다."""
    applies_to: list[str]
    params: list[StepParamOut]


class ProcessingScalarOut(BaseModel):
    key: str
    label: str
    value: float
    si_unit: str
    dimension: str | None = None
    """단위만으로 못 가르는 것을 가른다 — 변형률은 %, 개수는 그대로."""


class ProcessingStageOut(BaseModel):
    """단계 하나가 끝난 시점. **근거가 여기 산다.**

    화면이 단계별로 접어 보여 준다 — "정렬에서 몇 점이 합쳐졌나", "탄성계수를
    어느 구간의 몇 점으로 쟀나" 가 값 옆에 없으면, 반년 뒤 그 값을 설명할 수 없다.
    """

    index: int
    plugin: str
    label: str
    version: str
    options: dict[str, Any]
    notes: list[str]
    row_count: int
    columns: list[str]
    scalars: list[ProcessingScalarOut]


class ProcessingRunRequest(BaseModel):
    test_run_id: uuid.UUID
    source_curve_key: str | None = None
    """어느 곡선인가. 비우면 첫 번째 — 표가 하나뿐인 파일이 대부분이다."""
    steps: list[dict[str, Any]]
    """`[{"plugin": ..., "options": {...}}]`. 저장된 레시피 없이도 돌린다."""
    recipe_key: str | None = None
    """저장된 레시피로 돌렸으면 그 키. 결과에 이름을 남기려고 받는다."""


class ProcessingPreviewOut(BaseModel):
    source_curve_key: str
    source_row_count: int
    row_count: int
    columns: list[str]
    units: dict[str, str]
    stages: list[ProcessingStageOut]
    scalars: list[ProcessingScalarOut]
    notes: list[str]
    points: list[tuple[float, float]]


class ProcessingResultOut(BaseModel):
    id: uuid.UUID
    is_adopted: bool = False
    """**이 시험의 물성으로 삼은 것인가.** 시험당 하나뿐이다(ADR 0007)."""
    test_run_id: uuid.UUID
    source_curve_key: str
    recipe_key: str | None
    recipe_label: str | None
    steps: list[dict[str, Any]]
    """**그때의 단계 그대로다.** 레시피가 나중에 바뀌어도 이 값은 안 바뀐다."""
    stages: list[ProcessingStageOut]
    scalars: list[ProcessingScalarOut]
    row_count: int
    columns: list[str]
    created_at: datetime


class RecipeSaveRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str | None = None
    test_type_key: str
    steps: list[dict[str, Any]]
    is_active: bool = True


class RecipeCreateRequest(RecipeSaveRequest):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    owner_workspace_slug: str | None = None
    """비우면 전역 — **시스템 관리자만** 할 수 있다."""


class RecipeOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    description: str | None
    owner_workspace_slug: str | None
    owner_workspace_name: str | None
    is_global: bool
    test_type_key: str
    test_type_label: str
    steps: list[dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- 배치 --------------------------------------------------------------------


class BatchRequest(BaseModel):
    test_run_ids: list[uuid.UUID] = Field(min_length=1)
    source_curve_key: str | None = None
    steps: list[dict[str, Any]]
    recipe_key: str | None = None
    adopt: bool = True
    """성공한 것을 바로 채택할지. **기본이 참인 이유:** 배치를 돌리는 사람은
    이미 한 건으로 단계를 맞춰 본 뒤다. 여기서 또 하나씩 채택하게 하면 배치를
    쓴 의미가 절반이 된다."""


class BatchItemOut(BaseModel):
    test_run_id: uuid.UUID
    record_name: str
    status: str
    """`ok` | `failed`."""
    result_id: uuid.UUID | None = None
    adopted: bool = False
    error: str | None = None
    """어디서 왜 막혔는지. **건별로 다르다** — 시편 치수가 없는 것, 탄성 구간에
    점이 없는 것, 채널 이름이 다른 것이 한 배치에 섞여 온다."""
    scalars: list[ProcessingScalarOut] = []


class BatchOut(BaseModel):
    requested: int
    succeeded: int
    failed: int
    items: list[BatchItemOut]
