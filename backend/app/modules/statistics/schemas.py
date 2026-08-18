"""통계 API 의 요청·응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OutlierOut(BaseModel):
    """이상치 **후보**. 버려지지 않았다."""

    test_run_id: uuid.UUID
    record_name: str
    value: float
    score: float | None
    """modified z-score. 흩어짐이 0 이면 낼 수 없어 비어 있다."""
    reason: str


class ScalarStatsOut(BaseModel):
    key: str
    label: str
    si_unit: str
    dimension: str | None
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    sample_sd: float | None
    """흩어짐. **1건이면 없다** — 0 이 아니라 없는 것이다.

    0 을 넣으면 "완벽히 일정하다" 로 읽힌다. 한 번밖에 안 재서 모르는 것과
    여러 번 재서 같았던 것은 전혀 다른 말이다.
    """
    mad: float | None
    iqr: float | None
    coefficient_of_variation: float | None
    ci95_low: float | None
    ci95_high: float | None
    outliers: list[OutlierOut]


class CurveStatsOut(BaseModel):
    x: str
    y: str
    mean: list[tuple[float, float]]
    median: list[tuple[float, float]]
    sd: list[tuple[float, float]]
    count: list[tuple[float, float]]
    """점마다 몇 개로 냈는지. 공통 구간 밖은 애초에 계산하지 않는다."""


class GroupOut(BaseModel):
    """묶음 하나 — **재료 + 시험종류 + 방향.**"""

    test_type_key: str
    test_type_label: str
    orientation: str
    sample_count: int
    skipped_unadopted: int
    """채택되지 않아 빠진 시험 수. **조용히 빼면 n 이 왜 이 수인지 모른다.**"""
    test_run_ids: list[uuid.UUID]
    record_names: list[str]
    scalars: list[ScalarStatsOut]
    curve: CurveStatsOut | None
    notes: list[str]
    """왜 여기까지인지, 무엇이 어긋났는지. 곡선이 없으면 이유가 여기 있다."""


class MaterialStatisticsOut(BaseModel):
    material_id: uuid.UUID
    material_name: str
    groups: list[GroupOut]


class EnsembleSaveRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str


class EnsembleResultOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    sample_count: int
    test_run_ids: list[uuid.UUID]
    created_at: datetime
