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
선언은 점의 `temperature_k` · `frequency_hz`, 문헌은 `standard_conditions.catalog_keys`(값
검색과 같은 표). 표준에 안 이어진 조건은 지도에 안 나온다 — 그것은 「이 시험만의 조건」 이다.

**권한은 부르는 쪽이 판정한다**(`visible_materials`). 여기는 값만 안다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogValue,
)
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.grouping.models import GroupResult
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestConditionField, TestRun
from app.modules.vocabulary.models import VocabularyTerm
from app.shared import declared_approval, declared_conditions, standard_conditions, tiers
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
class Counts:
    """**「없다」 를 한 번에 답하게 하는 셈**(2026-09-18).

    기준선 4차에서 드러났다: 「시험으로 잰 값과 문헌값이 각각 뭐가 있나」 에 AI 가
    `property_coverage` 로 바로 답을 받고도 `get_statistics`·`list_test_runs`·
    `get_material` 을 더 불러 **「정말 없나」 를 확인했다**(6호출, 예산 5). 지도에
    안 보이는 것이 「없는 것」 인지 「안 이어진 것」 인지 지도만 봐서는 알 수 없었기
    때문이다 — `unmapped` 를 둔 이유와 같은 물음이고, 그 답이 이 셈이다.

    시편이 0 이면 잰 값이 없는 것이 **당연하다.** 그 줄이 있으면 사람도 AI 도 「시험
    목록을 뒤져 보자」 로 가지 않는다.
    """

    samples: int
    specimens: int
    test_runs: int
    adopted_results: int
    """채택된 결과. **여기가 0 이면 잰 값은 없다** — 시험이 있어도 채택이 없으면
    통계에도 카드에도 안 실린다(그 판단은 사람만 한다)."""
    measured: int
    """`origin == "measured"` 인 줄 수."""
    internal: int
    """선언 물성에서 온 줄 수."""
    catalog: int
    """이어진 문헌 재료에서 온 줄 수."""


@dataclass(frozen=True)
class Coverage:
    material_id: str
    properties: tuple[PropertyRow, ...]
    counts: Counts
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


@dataclass(frozen=True)
class ItemLinks:
    """사내 물성 항목 → **같은 물성(`same_as`)으로** 이어진 문헌 키, 눈금별(`property_links`).

    **이 다리를 두 곳에 두지 않는다.** 커버리지가 「잰 값과 문헌값이 같은 물성인가」
    를 묻는 데 쓰고, 카드 채우기(`declared_slots`)가 「적어 둔 값이 어느 칸에 가나」
    를 묻는 데 쓴다 — 둘이 갈라지면 화면이 이었다고 한 것이 카드에는 안 실린다.

    **아무거나 하나를 고르지 않는다**(2026-10-04). 전에는 항목 → 키를 사전에 접어 넣어서,
    연결이 넷인 「경도」(HV · HB · HRC · HRB)가 그중 **DB 가 마지막에 준 줄**의 키 하나로
    갔다 — HRC 로 적은 경도가 비커스 자리로 갈 수 있었다. 연결 종류도 안 봐서 「더 좁은」 ·
    「관련」 연결도 같은 물성으로 읽었다(`property_names.item_meanings` 는 진작 같은 물성만
    본다). 이제 같은 물성 연결만, **값의 눈금으로** 고르고, 하나로 안 정해지면 잇지 않는다.
    """

    by_item: dict[str, dict[str | None, frozenset[str]]]

    def key_of(self, item: str, scale: str | None = None) -> str | None:
        """이 항목 · 눈금의 값이 어느 키인가. **하나로 안 정해지면 `None`** — 짐작으로
        잇지 않는다. 눈금이 같은 연결이 먼저, 없으면 눈금을 안 가리는 연결(`scale` 빈칸)이다.
        """
        scales = self.by_item.get(item) or {}
        for wanted in (scale, None) if scale else (None,):
            found = scales.get(wanted)
            if found:
                return next(iter(found)) if len(found) == 1 else None
        return None

    def keys_of(self, item: str) -> frozenset[str]:
        """이 항목이 같은 물성으로 이어진 키 전부 — 눈금을 안 가리고."""
        return frozenset().union(*(self.by_item.get(item) or {}).values())


def item_links(db: Session) -> ItemLinks:
    """사내 물성 항목 → 문헌 키 다리를 한 번에 읽는다."""
    found: dict[str, dict[str | None, set[str]]] = {}
    for item, key, scale in db.execute(
        select(VocabularyTerm.value, PropertyLink.property_key, PropertyLink.scale)
        .join(VocabularyTerm, VocabularyTerm.id == PropertyLink.term_id)
        .where(PropertyLink.kind == "same_as")
    ).all():
        found.setdefault(str(item), {}).setdefault(scale or None, set()).add(str(key))
    return ItemLinks(
        {
            item: {scale: frozenset(keys) for scale, keys in scales.items()}
            for item, scales in found.items()
        }
    )


def _catalog_condition(conditions: dict[str, Any] | None) -> dict[str, float]:
    """문헌 `conditions` 에서 표준 조건만 SI 로 — 값 검색과 같은 표를 읽는다.

    전에는 키를 소문자로 접어 별칭만 봤다 — 값 검색(대소문자를 가린다)과 답이 갈렸고,
    `frequency_MHz` 같은 이름은 어느 쪽도 못 읽었다(2026-10-04).
    """
    out: dict[str, float] = {}
    for key in standard_conditions.STANDARD:
        value = standard_conditions.read_catalog(conditions, key)
        if value is not None:
            out[key] = value
    return out


def measured_entries(
    db: Session, material_id: uuid.UUID
) -> tuple[dict[str, list[Entry]], list[str]]:
    """시험으로 잰 값을 물성별로 — 채택된 처리 결과와 **묶음 결과**. 이어지지 않은 스칼라 키는
    따로 돌려준다."""
    scalar_map = _scalar_property_map()
    grouped = group_entries(db, material_id)
    rows = db.execute(
        select(TestRun, ProcessingResult)
        .join(ProcessingResult, ProcessingResult.id == TestRun.adopted_result_id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(Sample.material_id == material_id, TestRun.deleted_at.is_(None))
    ).all()
    if not rows:
        return grouped, []
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
    for property_key, entries in grouped.items():
        made[property_key].extend(entries)
    return made, sorted(unmapped)


def group_entries(db: Session, material_id: uuid.UUID) -> dict[str, list[Entry]]:
    """**묶음 결과**가 낸 값 — 재료마다 묶음 종류별 가장 최근 결과 하나(2026-10-08).

    Cowper-Symonds · Johnson-Cook · Basquin · Prony 처럼 여러 시험을 묶어 맞춘 값은 처리 결과가
    아니라 묶음 결과에 산다. 전에는 처리 결과만 읽어 문헌 키를 달아도 물성 지도에 안 섰다.
    다시 돌린 옛 결과는 세지 않는다 — 처리 결과에서 채택된 것만 보는 것과 같은 이유.
    조건은 비운다 — 묶음에는 시험 한 건의 조건이 없다.
    """
    rows = db.scalars(
        select(GroupResult)
        .where(GroupResult.material_id == material_id)
        .distinct(GroupResult.plugin_id)
        .order_by(GroupResult.plugin_id, GroupResult.created_at.desc())
    ).all()
    made: dict[str, list[Entry]] = defaultdict(list)
    for row in rows:
        try:
            plugin = registry.get(row.plugin_id)
        except KeyError:  # 등록이 사라진 확장의 옛 결과
            continue
        count = max(len(row.used or []), 1)
        for produced in plugin.makes_values:
            value = (row.values or {}).get(produced.key)
            if not produced.property_key or not isinstance(value, int | float):
                continue
            if isinstance(value, bool):
                continue
            made[produced.property_key].append(
                Entry(
                    origin="measured",
                    tier=tiers.measured_tier(count),
                    value_si=float(value),
                    count=count,
                    spread_si=None,
                    conditions={},
                    method=f"{plugin.label} · {produced.label}",
                    ref_kind="group_result",
                    ref_id=str(row.id),
                    ref_label=plugin.label,
                )
            )
    return made


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
    links = item_links(db)
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
            property_key = links.key_of(item, entry.get("scale"))
            if property_key is None:
                if item:
                    unmapped_items.add(item)
                continue
            # 승인한 값은 한 단계 위(ADR 0049) — 등급은 출처와 승인에서 센다.
            tier = declared_approval.tier(entry)
            for point in entry.get("points") or []:
                value = point.get("value_si")
                if not isinstance(value, int | float) or isinstance(value, bool):
                    continue
                # 주파수를 타는 항목(유전율)은 주파수가 조건이다 — 값 검색과 같은 짝
                # (`declared_conditions.POINT_KEY_OF_STANDARD`).
                conditions: dict[str, float] = {}
                for standard, point_key in declared_conditions.POINT_KEY_OF_STANDARD.items():
                    at = point.get(point_key)
                    if isinstance(at, int | float) and not isinstance(at, bool):
                        conditions[standard] = float(at)
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
        .where(
            CatalogValue.material_id.in_(linked),
            CatalogValue.value_num.is_not(None),
            # 원본에서 빠진 값은 「문헌이 채운다」 의 근거가 아니다(`mt_import.mark_missing`).
            CatalogValue.source_missing_at.is_(None),
        )
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
    return Coverage(
        material_id=str(material_id),
        properties=properties,
        counts=_counts(db, material_id, by_property),
        unmapped=unmapped,
    )


def _counts(
    db: Session, material_id: uuid.UUID, by_property: dict[str, list[Entry]]
) -> Counts:
    """한 질의로 센다 — 지도 한 장에 셈 네 번을 더 붙이면 그것대로 비용이다."""
    row = db.execute(
        select(
            func.count(func.distinct(Sample.id)),
            func.count(func.distinct(Specimen.id)),
            func.count(func.distinct(TestRun.id)),
            func.count(func.distinct(TestRun.adopted_result_id)),
        )
        .select_from(Sample)
        .outerjoin(Specimen, (Specimen.sample_id == Sample.id) & Specimen.deleted_at.is_(None))
        .outerjoin(
            TestRun, (TestRun.specimen_id == Specimen.id) & TestRun.deleted_at.is_(None)
        )
        .where(Sample.material_id == material_id, Sample.deleted_at.is_(None))
    ).one()
    origins = [entry.origin for entries in by_property.values() for entry in entries]
    return Counts(
        samples=int(row[0] or 0),
        specimens=int(row[1] or 0),
        test_runs=int(row[2] or 0),
        adopted_results=int(row[3] or 0),
        measured=sum(1 for one in origins if one == "measured"),
        internal=sum(1 for one in origins if one == "internal"),
        catalog=sum(1 for one in origins if one == "catalog"),
    )
