"""점탄성 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SweepOut(BaseModel):
    """겹칠 후보. 화면이 온도를 보고 기준을 고른다."""

    curve_key: str
    label: str | None = None
    temperature_k: float
    point_count: int
    minimum_frequency_hz: float
    maximum_frequency_hz: float


class SweepListOut(BaseModel):
    items: list[SweepOut]
    warnings: list[str] = []
    """뺀 곡선과 그 이유. **말없이 빼면 "왜 6벌인데 4벌만 겹쳤지" 가 된다.**"""


class ShiftOut(BaseModel):
    temperature_k: float
    log10_a_t: float
    source: str
    observed_log10_a_t: float | None = None
    residual: float | None = None
    """맞춘 값에서 관측값을 뺀 것. **벌어지면 그 모델이 이 재료에 안 맞는다.**"""
    overlap_rmse: float | None = None


class MasterCurveRequest(BaseModel):
    reference_temperature_k: float
    """**잰 온도 중에 있어야 한다.** 없는 온도의 곡선을 지어내지 않는다."""
    method: str = Field(default="wlf", pattern="^(wlf|arrhenius|manual)$")
    manual_shifts: dict[str, float] | None = None
    """`manual` 일 때 온도(K) → log10 a_T. 장비가 준 이동인자를 넣는 자리다.
    JSON 키가 문자열이라 온도를 문자열로 받는다."""
    curve_keys: list[str] | None = None
    """겹칠 곡선. 안 주면 측정 곡선 전부."""


class MasterCurveOut(BaseModel):
    id: uuid.UUID
    test_run_id: uuid.UUID
    source_curve_keys: list[str]
    reference_temperature_k: float
    method: str
    parameters: dict[str, float]
    shifts: list[ShiftOut]
    notes: list[str]
    point_count: int
    minimum_frequency_hz: float
    maximum_frequency_hz: float
    created_at: datetime


class PronyTermOut(BaseModel):
    modulus_pa: float
    relaxation_time_s: float


class PronyCandidateOut(BaseModel):
    term_count: int
    equilibrium_pa: float
    instantaneous_pa: float
    normalized_rmse: float
    bic: float
    """**작을수록 좋다.** 항을 늘리면 잔차는 언제나 줄지만 계수도 는다."""
    terms: list[PronyTermOut]
    at_bound: list[float]


class PronyRequest(BaseModel):
    terms: int | None = Field(default=None, ge=1, le=12)
    """정하면 그 항 수로 한 벌만. 안 주면 후보를 재고 BIC 로 고른다."""


class PronyFitOut(BaseModel):
    id: uuid.UUID
    master_curve_id: uuid.UUID
    equilibrium_pa: float
    instantaneous_pa: float
    terms: list[PronyTermOut]
    normalized_rmse: float
    bic: float
    at_bound: list[float]
    """경계에 붙은 완화시간. 있으면 **관측 밖을 외삽하고 있다.**"""
    candidates: list[PronyCandidateOut]
    """재 본 것 전부. 고른 것만 주면 사람이 다시 고를 수 없다."""
    created_at: datetime
