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


class ImportableCurveOut(BaseModel):
    """장비가 계산해 준 표 하나. **못 쓰는 것도 이유와 함께 나온다.**

    `derived` 에는 마스터커브와 이동인자 표가 함께 들어온다. 못 쓰는 것을 목록에서
    빼면 「내 파일의 그 표가 왜 안 보이지」 가 되고, 그냥 두면 골라 놓고 나서야
    거절을 본다.
    """

    curve_key: str
    label: str | None
    row_count: int
    channels: list[str]
    usable: bool
    """주파수·저장 탄성률 열이 둘 다 있는가."""
    note: str | None
    """못 쓰는 이유. 쓸 수 있으면 비어 있다."""


class MasterCurveImportRequest(BaseModel):
    """**장비가 이미 겹쳐 준 곡선**을 그대로 등록한다.

    TA TRIOS 같은 장비는 시간-온도 중첩을 제 소프트웨어에서 하고 마스터커브를
    함께 내보낸다. 그런 파일에는 겹칠 원본이 없거나, 있어도 장비가 쓴 이동인자를
    우리가 모른다 — **다시 겹치면 다른 곡선이 나오는데 둘 다 그럴듯하다.**
    """

    curve_key: str
    """어느 곡선인가. 프로파일이 `derived` 로 읽어 둔 표들 중 하나다."""

    reference_temperature_k: float
    """**사람이 적는다.** 표 이름에 있는 일이 많지만 장비마다 다르고, 틀린 온도로
    등록하면 그 덱은 조용히 다른 온도의 해석에 쓰인다 — 짐작하지 않는다."""


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
    is_primary: bool = False
    """**이 시험의 대표인가.** 재료의 글로벌 피팅이 이 곡선을 읽는다."""
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
