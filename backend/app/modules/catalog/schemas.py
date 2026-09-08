"""카탈로그 API 스키마."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class CatalogSummaryOut(BaseModel):
    materials: int
    values: int
    sources: int
    definitions: int
    subsystems: dict[str, int]
    categories: dict[str, int]
    domains: dict[str, int]
    tiers: dict[int, int]


class CatalogMaterialOut(BaseModel):
    id: uuid.UUID
    name: str
    material_code: str | None
    category: str
    subsystem: str | None
    role: str | None
    manufacturer: str | None
    material_class: str | None
    grade: str | None
    value_count: int = 0


class CatalogMaterialPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CatalogMaterialOut]


class CatalogSourceOut(BaseModel):
    id: uuid.UUID
    kind: str
    doi: str | None
    url: str | None
    title: str | None
    year: int | None
    publisher: str | None
    license: str | None


class CatalogValueOut(BaseModel):
    id: uuid.UUID
    property_key: str
    property_name: str
    domain: str
    symbol: str | None
    value_num: float | None
    value_text: str | None
    unit: str | None
    uncertainty: float | None
    conditions: dict[str, Any] | None
    method: str | None
    quality_tier: int
    source: CatalogSourceOut | None
    source_detail: str | None
    notes: str | None
    representative: bool = False
    """같은 물성의 후보 중 대표로 뽑힌 값인가. **진 후보도 함께 온다** — 화면이
    이유와 같이 보여 준다."""
    n_candidates: int = 1
    separated_by: str | None = None
    """대표에게 밀린 자리(상태·등급·수치·온도·조건 수·입력 순서). 대표는 None."""


class CatalogLinkIn(BaseModel):
    catalog_material_id: uuid.UUID


class CatalogLinkOut(BaseModel):
    """사내 재료의 문헌 연결 — 비면 전부 None. 화면이 한 번에 그릴 요약까지."""

    catalog_material_id: uuid.UUID | None = None
    name: str | None = None
    category: str | None = None
    subsystem: str | None = None
    value_count: int = 0


class DeckMatchIn(BaseModel):
    text: str
    """붙여넣은 줄들 — `MID, 이름` 또는 `이름`."""


class DeckCandidateOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    value_count: int
    score: int
    """정확 일치 3 > 앞부분 2 > 포함 1. 고르는 것은 사람이다."""


class DeckMatchRowOut(BaseModel):
    query: str
    mid: int | None
    candidates: list[DeckCandidateOut]


class DeckBuildItemIn(BaseModel):
    mid: int
    catalog_material_id: uuid.UUID


class DeckBuildIn(BaseModel):
    items: list[DeckBuildItemIn]
    format: str = "dyna_elastic"
    units: str | None = None
    """단위계 key. 비우면 SI."""


class DeckSkippedOut(BaseModel):
    mid: int
    name: str
    missing: list[str]


class DeckBuiltOut(BaseModel):
    filename: str
    text: str
    material_count: int
    skipped: list[DeckSkippedOut]
    notes: list[str]


class CatalogCompareCellOut(BaseModel):
    """비교 표의 칸 하나 — 그 재료의 그 물성 대표값. 없으면 None 칸."""

    value_num: float | None = None
    value_text: str | None = None
    quality_tier: int | None = None
    n_candidates: int = 0
    conditions: dict[str, Any] | None = None


class CatalogCompareRowOut(BaseModel):
    property_key: str
    name: str
    domain: str
    symbol: str | None
    unit: str | None
    cells: list[CatalogCompareCellOut]


class CatalogCompareOut(BaseModel):
    materials: list[CatalogMaterialOut]
    rows: list[CatalogCompareRowOut]
    """도메인·키 차례. ≥1 재료가 값을 가진 물성만."""


class AshbyAxisOut(BaseModel):
    key: str
    name: str
    domain: str
    unit: str | None
    material_count: int
    """이 물성의 수치 대표값을 가진 재료 수 — 축으로 쓸 만한지의 근거."""


class AshbyPointOut(BaseModel):
    id: uuid.UUID
    name: str
    group: str
    x: float
    y: float


class AshbyOut(BaseModel):
    x_unit: str | None
    y_unit: str | None
    points: list[AshbyPointOut]


class CatalogCoverageOut(BaseModel):
    """계통-도메인 값 수 격자. 빈 계통은 「미분류」("") 로 온다."""

    domains: list[str]
    subsystems: list[str]
    cells: dict[str, dict[str, int]]
    """subsystem → domain → 값 수."""


class CatalogMaterialDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    material_code: str | None
    category: str
    description: str | None
    subsystem: str | None
    role: str | None
    manufacturer: str | None
    material_class: str | None
    grade: str | None
    attributes: dict[str, Any] | None
    values: list[CatalogValueOut]


class PropertyCandidateOut(BaseModel):
    """물성 후보 하나 — **값을 묻기 전에 필요한 것을 다 들고 있다.**

    단위를 필드 이름에 박지 않고 값으로 싣는다(`si_unit`). 알루미늄 밀도가
    `2.68e-09 kg/m3` 로 나간 적이 있다 — 이름에 단위를 박은 탓이었다.
    """

    key: str
    name: str
    domain: str
    si_unit: str
    symbol: str | None
    value_count: int
    """값이 몇 건인가. 0이면 이 물성으로는 아무것도 못 찾는다."""
    internal_items: list[str]
    """이어진 사내 물성 항목. 있으면 우리가 실제로 쓰는 물성이다."""
    matched_by: str
    """`alias` · `name` · `symbol` · `key` · `alias_partial` · `partial`."""
    matched_text: str | None
    notes: list[str]


class PropertyResolveOut(BaseModel):
    query: str
    ambiguous: bool
    """**참이면 하나를 고르면 안 된다.** 도메인이 다른 후보가 나란히 섰다는 뜻이다."""
    candidates: list[PropertyCandidateOut]


class PropertyAliasOut(BaseModel):
    id: uuid.UUID
    property_key: str
    alias: str
    source: str
    note: str | None

    model_config = {"from_attributes": True}


class PropertyAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    source: str = "manual"
    note: str | None = None


class PropertyLinkOut(BaseModel):
    id: uuid.UUID
    property_key: str
    term_id: uuid.UUID
    item: str
    """사내 물성 항목 이름 — 화면이 기준정보를 따로 안 부르게."""
    kind: str
    note: str | None


class PropertyLinkCreate(BaseModel):
    property_key: str
    item: str
    """사내 물성 항목 **이름**으로 받는다 — 사람이 폼에 id 를 적지 않는다."""
    kind: str = "same_as"
    note: str | None = None


class PropertyHitOut(BaseModel):
    """값 하나와 그것을 든 재료. **값과 단위를 함께 싣는다.**"""

    world: str
    """`catalog`(문헌) · `internal`(사내)."""
    material_id: uuid.UUID
    material_name: str
    value: float
    """**물어본 단위로 되돌린 값.** SI 원본은 `value_si`."""
    unit: str
    value_si: float
    quality_tier: int | None = None
    source_detail: str | None = None
    category: str | None = None


class PropertySearchOut(BaseModel):
    """값 검색 결과.

    **후보가 갈렸으면 값을 안 찾고 되묻는다** — 어느 물성인지 모른 채 찾은 값은
    엉뚱한 물성의 정답이다.
    """

    query: str
    resolved: PropertyCandidateOut | None = None
    ambiguous: bool = False
    candidates: list[PropertyCandidateOut] = Field(default_factory=list)
    """`ambiguous` 일 때만 채워진다 — 사용자가 고를 것들."""

    unit: str | None = None
    range_si: list[float] | None = None
    """실제로 건 범위(SI). **AI 가 자기가 무엇을 물었는지 되짚을 수 있어야 한다.**"""
    total: int = 0
    hits: list[PropertyHitOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
