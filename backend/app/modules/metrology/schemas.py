"""측정법 API 스키마."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class MetrologySummaryOut(BaseModel):
    instruments: int
    """장비 카탈로그의 장비 수 — **보유 수가 아니다.**"""
    instruments_owned: int
    capabilities: int
    properties_covered: int
    """측정 능력이 하나라도 이어진 카탈로그 물성 수."""
    properties_total: int
    categories: dict[str, int]
    """장비 분류(thermal·mechanical·…) → 장비 수."""


class MetrologyCoverageRowOut(BaseModel):
    property_key: str
    name: str
    domain: str
    symbol: str | None
    si_unit: str | None
    technique_count: int
    instrument_count: int
    owned_instrument_count: int
    """보유 장비만 센 수 — 0 이면 「카탈로그에는 있지만 우리는 못 잰다」."""
    value_count: int
    """문헌 카탈로그에 실린 값 수 — 잴 이유가 얼마나 쌓여 있는가."""


class MetrologyCoverageOut(BaseModel):
    covered: list[MetrologyCoverageRowOut]
    gaps: list[MetrologyCoverageRowOut]
    """측정 능력이 하나도 안 이어진 물성 — 빈 칸을 숨기지 않는다."""


class MetrologyInstrumentOut(BaseModel):
    id: uuid.UUID
    vendor: str
    model: str
    category: str
    owned: bool
    owned_note: str | None
    owner_name: str | None


class MetrologyCapabilityOut(BaseModel):
    id: uuid.UUID
    instrument: MetrologyInstrumentOut
    standard: str | None
    range_min: float | None
    range_max: float | None
    range_unit: str | None
    resolution: str | None
    accuracy: str | None
    temperature_min_k: float | None
    temperature_max_k: float | None
    specimen: str | None
    mapping_confidence: str | None
    """high·medium·low — high 가 아니면 화면이 표시를 단다."""
    source_detail: str | None
    notes: str | None


class MetrologyTechniqueGroupOut(BaseModel):
    technique: str | None
    """원본이 기법을 못 정한 능력도 있다 — None 그룹으로 그대로 보인다."""
    capabilities: list[MetrologyCapabilityOut]


class MetrologyPropertyOut(BaseModel):
    property_key: str
    name: str
    domain: str
    symbol: str | None
    si_unit: str | None
    test_standard: str | None
    techniques: list[MetrologyTechniqueGroupOut]
