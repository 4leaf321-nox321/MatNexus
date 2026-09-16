"""물성 지도 — **이 재료에 어떤 물성이 어떤 조건에 어떤 등급으로 있나, 한 장.**

값 검색(`property_search`)이 「이 값 근처인 재료」 를 답하는 반대 방향이다 — 재료
하나를 놓고 무엇이 있고 무엇이 없는지를 본다. 전에는 카탈로그(`CatalogCoveragePage`)에만
있었고 사내 재료는 시험·카드·선언을 각자 열어 봐야 했다(2026-09-16, [계획] 온톨로지
고도화 §2-E).

세 세계를 **같은 줄 모양**으로 편다 — 물성 키 · 출처 · 등급 · 값(SI) · 표준 조건:

    measured   채택된 처리 결과의 스칼라 (재료·물성·방법·조건별로 묶어 평균·표본 수)
    internal   선언 물성의 점 (재료 층 + 시료 층)
    catalog    이어진 문헌 재료(`catalog_links`)의 값

물성 이름은 문헌 정의 키(`catalog_definitions.key`)를 공용어로 쓴다 — 시험 스칼라는
`Produced.property_key`, 선언 항목은 `property_links` 로 그 키에 이어진다. 이어지지
않은 스칼라·항목은 **빠지지 않고 `unmapped` 에 센다** — 지도에서 사라지면 없는 줄 안다.

조건은 표준 조건 키(`standard_conditions`)로만 적는다. 시험은 조건 칸의 `canonical_key`,
선언은 점의 `temperature_k`, 문헌은 `temperature_c/k` 별칭. 표준에 안 이어진 조건은
지도에 안 나온다 — 그것은 「이 시험만의 조건」 이다.

**권한은 부르는 쪽이 판정한다**(`visible_materials`). 여기는 값만 안다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogValue,
)
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestConditionField, TestRun
from app.modules.vocabulary.models import VocabularyTerm
from app.shared import standard_conditions, tiers
from matcore import registry


@dataclass(frozen=True)
class Entry:
    origin: str
    """`measured` · `internal` · `catalog`."""
    tier: int
    value_si: float
    count: int
    spread_si: float | None
    conditions: dict[str, float]
    """표준 조건 키 → SI 값. 비어 있으면 조건을 적지 않은 값."""
    method: str | None
    """잰 값의 방법(스칼라 키·계산 옵션) · 선언의 출처 · 문헌의 출처 요약."""
    ref_kind: str
    """`test_run` · `material` · `sample` · `catalog_value` — 누르면 어디로 가나."""
    ref_id: str
    ref_label: str


@dataclass(frozen=True)
class PropertyRow:
    key: str
    name: str
    si_unit: str | None
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class Coverage:
    material_id: str
    properties: tuple[PropertyRow, ...]
    unmapped: dict[str, list[str]] = field(default_factory=dict)
    """공용어에 안 이어진 것 — `{"scalars": [...], "items": [...]}`. 물성 매핑에서 잇는다."""


def _round_conditions(found: dict[str, float]) -> tuple[tuple[str, float], ...]:
    """묶음 키 — 296.149 와 296.151 을 한 줄로. 온도는 0.1 K, 나머지는 유효숫자 셋."""
    out = []
    for key, value in sorted(found.items()):
        if key == "temperature":
            out.append((key, round(value, 1)))
        else:
            out.append((key, float(f"{value:.3g}")))
    return tuple(out)


def _scalar_property_map() -> dict[str, str]:
    """시험 스칼라 키 → 문헌 물성 키. 계산이 선언한다(`Produced.property_key`)."""
    found: dict[str, str] = {}
    for plugin in registry.list_plugins():
        if plugin.kind not in ("processing", "grouping"):
            continue
        for made in plugin.makes_values:
            if made.property_key:
                found.setdefault(made.key, made.property_key)
    return found


def _item_property_map(db: Session) -> dict[str, str]:
    """사내 물성 항목 이름 → 문헌 물성 키(`property_links`)."""
    rows = db.execute(
        select(VocabularyTerm.value, PropertyLink.property_key).join(
            VocabularyTerm, VocabularyTerm.id == PropertyLink.term_id
        )
    ).all()
    return {str(value): str(key) for value, key in rows}


def _catalog_condition(conditions: dict[str, Any] | None) -> dict[str, float]:
    """문헌 `conditions` 에서 표준 조건만 SI 로."""
    if not conditions:
        return {}
    out: dict[str, float] = {}
    for raw_key, raw in conditions.items():
        if not isinstance(raw, int | float) or isinstance(raw, bool):
            continue
        key = str(raw_key).lower()
        canonical = standard_conditions.resolve(key)
        if canonical is None or canonical in out:
            continue
        value = float(raw)
        if canonical == "temperature" and key == "temperature_c":
            value += 273.15
        out[canonical] = value
    return out


def measured_entries(
    db: Session, material_id: uuid.UUID
) -> tuple[dict[str, list[Entry]], list[str]]:
    """시험으로 잰 값을 물성별로. 이어지지 않은 스칼라 키는 따로 돌려준다."""
    scalar_map = _scalar_property_map()
    rows = db.execute(
        select(TestRun, ProcessingResult)
        .join(ProcessingResult, ProcessingResult.id == TestRun.adopted_result_id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(Sample.material_id == material_id, TestRun.deleted_at.is_(None))
    ).all()
    if not rows:
        return {}, []
    type_ids = {run.test_type_id for run, _ in rows}
    fields = db.execute(
        select(
            TestConditionField.test_type_id,
            TestConditionField.key,
            TestConditionField.canonical_key,
        )
        .where(TestConditionField.test_type_id.in_(type_ids))
        .where(TestConditionField.canonical_key.is_not(None))
    ).all()
    canonical_of: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    for type_id, key, canonical in fields:
        canonical_of[type_id][key] = canonical

    bucket: dict[
        tuple[str, str, tuple[tuple[str, float], ...]], list[tuple[float, TestRun]]
    ] = defaultdict(list)
    unmapped: set[str] = set()
    for run, result in rows:
        found: dict[str, float] = {}
        for key, canonical in canonical_of.get(run.test_type_id, {}).items():
            raw = (run.conditions or {}).get(key)
            if isinstance(raw, int | float) and not isinstance(raw, bool):
                found[canonical] = float(raw)
        for scalar in result.scalars or []:
            key = str(scalar.get("key", ""))
            value = scalar.get("value")
            if not isinstance(value, int | float) or isinstance(value, bool):
                continue
            property_key = scalar_map.get(key)
            if property_key is None:
                unmapped.add(key)
                continue
            method = f"{key}"
            bucket[(property_key, method, _round_conditions(found))].append(
                (float(value), run)
            )

    made: dict[str, list[Entry]] = defaultdict(list)
    for (property_key, method, cond_key), values in bucket.items():
        numbers = [one for one, _ in values]
        mean = sum(numbers) / len(numbers)
        spread = (
            (sum((one - mean) ** 2 for one in numbers) / (len(numbers) - 1)) ** 0.5
            if len(numbers) > 1
            else None
        )
        first = values[0][1]
        made[property_key].append(
            Entry(
                origin="measured",
                tier=tiers.measured_tier(len(numbers)),
                value_si=mean,
                count=len(numbers),
                spread_si=spread,
                conditions=dict(cond_key),
                method=method,
                ref_kind="test_run",
                ref_id=str(first.id),
                ref_label=first.record_name,
            )
        )
    return made, sorted(unmapped)


def collect(db: Session, material_id: uuid.UUID) -> Coverage:
    """세 세계를 물성별로 모아 한 장으로."""
    by_property: dict[str, list[Entry]] = defaultdict(list)
    unmapped: dict[str, list[str]] = {}

    # ── 시험으로 잰 값
    measured, unmapped_scalars = measured_entries(db, material_id)
    for key, entries in measured.items():
        by_property[key].extend(entries)
    if unmapped_scalars:
        unmapped["scalars"] = unmapped_scalars

    # ── 선언 물성 (재료 층 + 시료 층)
    item_map = _item_property_map(db)
    unmapped_items: set[str] = set()
    material = db.get(Material, material_id)
    holders: list[tuple[str, str, str, list[dict[str, Any]]]] = []
    if material is not None:
        holders.append(
            (
                "material",
                str(material.id),
                material.record_name,
                material.declared_properties or [],
            )
        )
    for sample in db.scalars(
        select(Sample).where(Sample.material_id == material_id, Sample.deleted_at.is_(None))
    ):
        holders.append(
            ("sample", str(sample.id), sample.record_name, sample.declared_properties or [])
        )
    for ref_kind, ref_id, ref_label, declared in holders:
        for entry in declared:
            item = str(entry.get("item") or "")
            property_key = item_map.get(item)
            if property_key is None:
                if item:
                    unmapped_items.add(item)
                continue
            tier = tiers.declared_tier(entry.get("source"))
            for point in entry.get("points") or []:
                value = point.get("value_si")
                if not isinstance(value, int | float) or isinstance(value, bool):
                    continue
                conditions: dict[str, float] = {}
                at = point.get("temperature_k")
                if isinstance(at, int | float) and not isinstance(at, bool):
                    conditions["temperature"] = float(at)
                by_property[property_key].append(
                    Entry(
                        origin="internal",
                        tier=tier,
                        value_si=float(value),
                        count=1,
                        spread_si=None,
                        conditions=conditions,
                        method=" · ".join(
                            part
                            for part in (
                                str(entry.get("source") or ""),
                                str(entry.get("reference") or ""),
                            )
                            if part
                        )
                        or None,
                        ref_kind=ref_kind,
                        ref_id=ref_id,
                        ref_label=ref_label,
                    )
                )
    if unmapped_items:
        unmapped["items"] = sorted(unmapped_items)

    # ── 이어진 문헌 재료의 값
    linked = select(CatalogLink.catalog_material_id).where(
        CatalogLink.material_id == material_id
    )
    for value, catalog_material in db.execute(
        select(CatalogValue, CatalogMaterial)
        .join(CatalogMaterial, CatalogMaterial.id == CatalogValue.material_id)
        .where(CatalogValue.material_id.in_(linked), CatalogValue.value_num.is_not(None))
    ).all():
        by_property[value.property_key].append(
            Entry(
                origin="catalog",
                tier=int(value.quality_tier),
                value_si=float(value.value_num),
                count=1,
                spread_si=None,
                conditions=_catalog_condition(value.conditions),
                method=value.source_detail or None,
                ref_kind="catalog_value",
                ref_id=str(value.id),
                ref_label=catalog_material.name,
            )
        )

    # ── 이름·단위
    keys = sorted(by_property)
    defs = {
        one.key: one
        for one in db.scalars(select(CatalogDefinition).where(CatalogDefinition.key.in_(keys)))
    }
    properties = tuple(
        PropertyRow(
            key=key,
            name=defs[key].name if key in defs else key,
            si_unit=defs[key].si_unit if key in defs else None,
            entries=tuple(
                sorted(by_property[key], key=lambda one: (one.tier, one.origin, one.value_si))
            ),
        )
        for key in keys
    )
    return Coverage(material_id=str(material_id), properties=properties, unmapped=unmapped)
