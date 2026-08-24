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


class ObservationOut(BaseModel):
    """값 하나가 어떻게 됐는가. **없는 것과 못 쓰는 것을 가른다.**"""

    specimen_label: str
    status: str
    """`observed` · `missing` · `non_finite` · `censored`"""
    value: float | None


class DistributionCandidateOut(BaseModel):
    """분포 하나를 맞춰 본 결과. **실패한 것도 목록에 남는다.**"""

    key: str
    label: str
    status: str
    """`succeeded` · `not_eligible` · `failed`.

    **셋을 한 칸에 넣지 않는다.** `not_eligible` 은 표본이 모자라 물음이 성립하지
    않는 것이고 `failed` 는 물었는데 답이 안 나온 것이다 — 섞으면 "와이블이 안
    맞는 재료" 와 "시편이 모자란 재료" 가 같은 색으로 보인다."""
    reason: str | None
    parameters: list[float]
    parameter_names: list[str]
    parameter_labels: list[str]
    log_likelihood: float | None
    aicc: float | None
    """유한표본 보정 AIC. **작을수록 낫다.** 후보끼리만 뜻이 있다 — 전부 안 맞아도
    하나는 1등이 된다."""
    delta_aicc: float | None
    """1등과의 차이. 2 미만이면 이 데이터로는 구별되지 않는다."""
    anderson_darling: float | None
    p_value: float | None
    """모수 부트스트랩 p. **작으면 이 분포가 아니라는 뜻이다.** 큰 p 가 "맞다" 는
    증명은 아니다 — 표본이 작으면 무엇으로도 안 갈린다."""
    quantiles: dict[str, float]
    """`p05`·`p50`·`p95`. **이 응답의 쓸모가 여기 있다** — 설계가 묻는 것은
    파라미터가 아니라 하위 5% 다."""


class DistributionReportOut(BaseModel):
    """한 항목에 대한 분포 적합 한 벌."""

    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    scalar_key: str
    scalar_label: str
    si_unit: str
    count: int
    """실제로 쓴 값의 개수. 시편 수가 아니다."""
    observations: list[ObservationOut]
    candidates: list[DistributionCandidateOut]
    best: str | None
    notes: list[str]


class DistributableKeyOut(BaseModel):
    """분포를 물어볼 수 있는 항목 하나."""

    key: str
    label: str
    si_unit: str
    count: int
    """값이 있는 시편 수. **`MIN_ELIGIBLE` 미만이면 화면이 미리 말해 준다** —
    눌러 보고 나서 "모자랍니다" 를 받는 것보다 낫다."""
