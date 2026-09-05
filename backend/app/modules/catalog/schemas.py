"""카탈로그 API 스키마."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


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
