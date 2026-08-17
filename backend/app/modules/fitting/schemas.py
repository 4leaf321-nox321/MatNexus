"""적합·물성 카드 API 의 요청·응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FamilyOut(BaseModel):
    key: str
    label: str
    describe: str
    parameter_names: list[str]
    parameter_units: list[str]


class FittedParameterOut(BaseModel):
    name: str
    value: float
    si_unit: str
    lower: float
    upper: float
    initial: float
    """**경계와 초기값을 함께 준다.** 비선형 적합은 여기에 따라 다른 답에 수렴한다."""


class FitOut(BaseModel):
    family: str
    label: str
    parameters: list[FittedParameterOut]
    rmse: float
    relative_rmse: float
    r_squared: float
    max_residual: float
    point_count: int
    strain_min: float
    strain_max: float
    """**적합 구간.** 이 밖은 외삽이고 식마다 전혀 다른 값이 나온다."""
    notes: list[str]
    curve: list[tuple[float, float]]
    """적합된 식을 그린 것. 데이터와 겹쳐 봐야 맞는지 눈으로 판단할 수 있다."""


class FitPreviewRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    families: list[str] = []
    """비우면 등록된 식 전부를 견준다."""


class FitPreviewOut(BaseModel):
    source_points: list[tuple[float, float]]
    """적합에 쓴 점(소성변형률, 진응력). 대표 곡선에서 왔다."""
    sample_count: int
    fits: list[FitOut]
    notes: list[str]


class PropertyCardSaveRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    label: str = Field(min_length=1, max_length=120)
    family: str | None = None
    """비우면 표만 저장한다 — 식이 안 맞는 재료에서는 표가 더 정확하다."""
    poisson_ratio: float | None = Field(default=None, gt=0, lt=0.5)
    """**인장시험이 주지 않는 값이다.** 없으면 없는 채로 둔다 — 0.3 으로 채우면
    그것이 측정값인지 기본값인지 나중에 알 수 없다."""
    density: float | None = Field(default=None, gt=0)
    note: str | None = None


class ExportFormatOut(BaseModel):
    key: str
    label: str
    extension: str
    describe: str
    requires: list[str]
    """이 형식에 반드시 있어야 하는 값. **화면이 미리 알려 줄 수 있어야 한다** —
    내려받기를 누른 뒤에 "푸아송비가 없습니다" 를 보는 것은 늦다."""


class PropertyCardOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    test_type_key: str
    orientation: str
    label: str
    status: str
    """`draft` | `published` | `deprecated`. 전환 권한은 D8·D12 참조."""
    source: dict[str, Any]
    elastic: dict[str, Any]
    hardening: dict[str, Any]
    table: list[dict[str, Any]]
    point_count: int
    note: str | None
    published_at: datetime | None
    created_at: datetime
