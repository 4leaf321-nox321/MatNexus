"""물성 분석 — **다섯 화면이 같은 관측 하나를 다르게 본다.**

    비교        재료 몇 개를 나란히
    분포        사업부·재료군별 흩어짐
    사양 대비   선언한 값과 잰 값의 차이
    추이        해가 가며 값이 흐르는가
    커버리지    무엇을 아직 안 쟀는가
    카드 항목   어느 재료에서 무엇까지 볼 수 있나 (요약 · 전체 · 칸)

앞 넷은 전부 **채택된 처리 결과의 스칼라**를 재료·사업부·시간으로 접은 것이다.
그래서 모으는 코드는 하나고(`collect`), 화면마다 접는 방법만 다르다 — 각자 질의를
쓰면 「비교의 인장강도」 와 「분포의 인장강도」 가 다른 수를 말하는 날이 온다.

## 무엇을 세는가

**채택된 결과(`TestRun.adopted_result_id`)만.** 채택은 「이 시험의 물성은 이것」 이라는
사람의 결정이고(ADR 0007), 그것을 안 거친 값은 아직 물성이 아니다. 안 채택된 것은
세지 않되 **몇 건이 빠졌는지 함께 돌려준다** — 조용히 빼면 n 이 왜 이 수인지 모른다.

커버리지만 스칼라를 안 본다. 「쟀는가」 는 시험이 있는가지 값이 나왔는가가 아니다.
카드 항목은 스칼라가 아니라 **물성 카드**를 본다 — 점탄성·경화식·소성 표는 스칼라가
아니라서 앞의 화면들에는 안 나온다.
"""

from __future__ import annotations

import statistics as stats
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, String, case, column, func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun, TestType
from app.shared import declared_slots, permissions
from app.shared import divisions as divisions_order
from app.shared.coverage import item_property_map
from app.shared.errors import NotFound
from matcore import cards


@dataclass(frozen=True)
class Observation:
    """잰 값 하나 — **어느 재료의, 어느 사업부가, 언제, 무엇을.**"""

    run_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    family: str
    category: str
    division: str
    test_type_key: str
    test_type_label: str
    orientation: str
    tested_at: datetime | None
    scalar_key: str
    scalar_label: str
    si_unit: str
    value: float


@dataclass(frozen=True)
class Collected:
    observations: list[Observation]
    skipped_unadopted: int
    """채택 안 돼 빠진 시험 수. **화면이 이 수를 보여야** n 이 설명된다."""


def _runs(db: Session, user: User) -> Select[Any]:
    return permissions.visible_runs(db, user)


def collect(
    db: Session,
    user: User,
    *,
    material_ids: Sequence[uuid.UUID] | None = None,
    scalar_keys: Sequence[str] | None = None,
) -> Collected:
    """채택된 결과의 스칼라를 관측으로 편다. **다섯 화면이 이것만 쓴다.**

    한 질의로 시험·시편·시료·재료·종류를 함께 가져온다 — 시험이 수백이면 N+1 은
    화면이 안 뜨는 것과 같다.
    """
    runs = _runs(db, user).subquery()
    query = (
        select(TestRun, Specimen, Sample, Material, TestType)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .join(Material, Material.id == Sample.material_id)
        .join(TestType, TestType.id == TestRun.test_type_id)
        .where(
            TestRun.id.in_(select(runs.c.id)),
            Specimen.deleted_at.is_(None),
            Sample.deleted_at.is_(None),
            Material.deleted_at.is_(None),
        )
    )
    if material_ids is not None:
        if not material_ids:
            return Collected([], 0)
        query = query.where(Material.id.in_(list(material_ids)))
    rows = db.execute(query).all()

    adopted_ids = [run.adopted_result_id for run, *_ in rows if run.adopted_result_id]
    results = {
        item.id: item
        for item in db.scalars(
            select(ProcessingResult).where(ProcessingResult.id.in_(adopted_ids))
        )
    }

    wanted = set(scalar_keys) if scalar_keys else None
    out: list[Observation] = []
    skipped = 0
    for run, specimen, _sample, material, test_type in rows:
        result = results.get(run.adopted_result_id) if run.adopted_result_id else None
        if result is None:
            skipped += 1
            continue
        for scalar in result.scalars:
            key = str(scalar.get("key", ""))
            value = scalar.get("value")
            if not key or not isinstance(value, int | float):
                continue
            if wanted is not None and key not in wanted:
                continue
            out.append(
                Observation(
                    run_id=run.id,
                    material_id=material.id,
                    material_name=material.record_name,
                    family=material.family,
                    category=material.category,
                    division=run.division or divisions_order.UNSET,
                    test_type_key=test_type.key,
                    test_type_label=test_type.label,
                    orientation=specimen.orientation,
                    tested_at=run.tested_at or run.created_at,
                    scalar_key=key,
                    scalar_label=str(scalar.get("label") or key),
                    si_unit=str(scalar.get("si_unit") or "1"),
                    value=float(value),
                )
            )
    return Collected(out, skipped)


# --- 요약 ------------------------------------------------------------------------


@dataclass(frozen=True)
class Spread:
    """흩어짐 한 벌 — 상자그림이 그리는 것."""

    count: int
    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    mean: float
    outliers: list[float]


def spread(values: Iterable[float]) -> Spread | None:
    """사분위와 이상치. **2건 미만이면 없다** — 상자를 그릴 수 없다.

    이상치는 `1.5 * IQR` 바깥. 상자그림의 관례를 그대로 쓴다 — 이 저장소의 다른
    이상치 판정(MAD, ADR 0008)과 다르지만, 저쪽은 「빼고 평균낼까」 를 묻는 자리고
    여기는 **눈으로 보는 그림**이다. 그림의 관례를 바꾸면 읽는 사람이 오해한다.
    """
    ordered = sorted(values)
    if len(ordered) < 2:
        return None
    quantiles = stats.quantiles(ordered, n=4, method="inclusive")
    q1, median, q3 = quantiles[0], quantiles[1], quantiles[2]
    gap = q3 - q1
    low, high = q1 - 1.5 * gap, q3 + 1.5 * gap
    inside = [one for one in ordered if low <= one <= high] or ordered
    return Spread(
        count=len(ordered),
        minimum=inside[0],
        q1=q1,
        median=median,
        q3=q3,
        maximum=inside[-1],
        mean=stats.fmean(ordered),
        outliers=[one for one in ordered if one < low or one > high],
    )


def material_choices(observations: Sequence[Observation]) -> list[dict[str, Any]]:
    """비교에 담을 수 있는 재료 — **채택된 물성이 있는 것만.**

    전체 목록에서 고르게 하면 물성이 없는 재료를 담고 빈 줄을 본다. 무엇을 몇 건
    갖고 있는지 함께 줘서 담기 전에 보이게 한다.
    """
    facts: dict[uuid.UUID, dict[str, Any]] = {}
    for one in observations:
        entry = facts.setdefault(
            one.material_id,
            {
                "material_id": one.material_id,
                "material_name": one.material_name,
                "family": one.family,
                "category": one.category,
                "scalars": set(),
                "runs": set(),
            },
        )
        entry["scalars"].add(one.scalar_key)
        entry["runs"].add(one.run_id)
    return sorted(
        (
            {
                "material_id": one["material_id"],
                "material_name": one["material_name"],
                "family": one["family"],
                "category": one["category"],
                "scalar_count": len(one["scalars"]),
                "run_count": len(one["runs"]),
            }
            for one in facts.values()
        ),
        key=lambda one: str(one["material_name"]),
    )


def scalar_catalog(observations: Sequence[Observation]) -> list[dict[str, Any]]:
    """고를 수 있는 항목 — **실제로 값이 있는 것만.**

    전체 목록을 보여 주면 골랐는데 빈 화면이 나온다. 건수를 함께 줘서 고르기 전에
    몇 건인지 보이게 한다.
    """
    tally: dict[str, dict[str, Any]] = {}
    for one in observations:
        entry = tally.setdefault(
            one.scalar_key,
            {
                "key": one.scalar_key,
                "label": one.scalar_label,
                "si_unit": one.si_unit,
                "count": 0,
            },
        )
        entry["count"] = int(entry["count"]) + 1
    return sorted(tally.values(), key=lambda one: (-int(one["count"]), str(one["label"])))


# --- 커버리지 ---------------------------------------------------------------------


def coverage(db: Session, user: User) -> dict[str, Any]:
    """분류(재료군-분류) x 시험종류 격자. **빈 칸이 다음에 할 시험이다.**

    재료마다 한 줄이면 94줄이 되고 그 표에서는 「무엇을 안 쟀나」 가 안 읽힌다.
    분류로 접으면 「Metal/Steel 은 인장은 했고 점탄성은 안 했다」 가 한 줄에 온다.

    스칼라를 안 본다 — 「쟀는가」 는 시험이 있는가지 값이 나왔는가가 아니다. 다만
    **채택까지 간 수와 재료 수를 따로 센다**: 올리기만 한 것과 물성이 나온 것은
    다르고, 분류에 재료가 10개인데 1개만 쟀으면 「쟀다」 로 읽히면 안 된다.
    """
    runs = _runs(db, user).subquery()
    rows = db.execute(
        select(
            Material.family,
            Material.category,
            TestType.key,
            TestType.label,
            func.count(TestRun.id),
            func.count(TestRun.adopted_result_id),
            func.count(func.distinct(Material.id)),
        )
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .join(Material, Material.id == Sample.material_id)
        .join(TestType, TestType.id == TestRun.test_type_id)
        .where(
            TestRun.id.in_(select(runs.c.id)),
            Specimen.deleted_at.is_(None),
            Sample.deleted_at.is_(None),
            Material.deleted_at.is_(None),
        )
        .group_by(Material.family, Material.category, TestType.key, TestType.label)
    ).all()

    # **분류의 재료 수는 시험과 무관하다.** 시험 쪽에서 세면 「시험한 재료 수」 가
    # 되고, 그러면 0/10 인 분류가 표에서 아예 사라진다 — 그 줄이 요점인데.
    totals = db.execute(
        select(Material.family, Material.category, func.count(Material.id))
        .where(
            Material.id.in_(permissions.visible_material_ids(db, user)),
            Material.deleted_at.is_(None),
        )
        .group_by(Material.family, Material.category)
    ).all()

    types: dict[str, str] = {}
    groups: dict[tuple[str, str], dict[str, Any]] = {
        (str(family), str(category)): {
            "family": str(family),
            "category": str(category),
            "material_count": int(count),
            "cells": {},
        }
        for family, category, count in totals
    }
    for family, category, type_key, type_label, total, adopted, materials in rows:
        types[str(type_key)] = str(type_label)
        entry = groups.setdefault(
            (str(family), str(category)),
            {
                "family": str(family),
                "category": str(category),
                "material_count": 0,
                "cells": {},
            },
        )
        entry["cells"][str(type_key)] = {
            "run_count": int(total),
            "adopted_count": int(adopted),
            "material_count": int(materials),
        }
    return {
        "test_types": [{"key": key, "label": label} for key, label in sorted(types.items())],
        "groups": sorted(groups.values(), key=lambda one: (one["family"], one["category"])),
    }


# --- 카드 항목 ---------------------------------------------------------------------
#
# **재료가 수천이면 한 장에 못 편다.** 재료마다 한 줄에 칸마다 카드 값까지 싣던 첫 판을
# 가짜 1만 개로 재 보니 응답 10 MB · 표가 뜨는 데 3.6 초 · 화면 요소 14만이었다
# (2026-09-24). 그래서 셋으로 나눈다:
#
#     요약   재료군·분류마다 항목란별 재료 수 — 줄이 분류 수라 재료 수와 무관하다
#     전체   재료 줄을 서버가 거르고 잘라 준다(한 번에 `pagination.MAX_LIMIT` 까지)
#     칸     누른 칸 하나의 카드 값 · 시험 · 선언 — 누를 때만 받는다
#
# 셋이 **같은 판정**(`_book`)을 쓴다 — 요약의 「점탄성 4」 를 누르면 전체에 네 줄이 떠야
# 한다. 판정에 드는 것은 SQL 이 센 것만 가져온다: 카드는 (재료, 항목란, 상태별 장 수),
# 선언은 (재료, 항목 이름) — 카드의 표나 선언 물성 전체를 나르지 않는다.

#: 칸의 상태가 앞서는 차례 — 확정 카드가 하나라도 있으면 그 칸은 「확정」 이다.
_STATUS_RANK = {"published": 0, "draft": 1, "deprecated": 2}

#: 칸의 상태. `source` 는 카드는 없고 그 항목란을 내는 시험의 채택 결과
#: (`BlockSpec.from_tests`) 나 그 칸으로 갈 선언 물성(`declared_slots`)만 있는 칸이다.
STATES = ("published", "draft", "deprecated", "source")


@dataclass(frozen=True)
class _Material:
    id: uuid.UUID
    name: str
    family: str
    category: str


@dataclass(frozen=True)
class _Cell:
    state: str
    card_count: int
    tests: bool
    """그 항목란을 내는 시험의 채택 결과가 있나."""
    declared: bool
    """그 칸으로 갈 선언 물성이 있나."""


@dataclass(frozen=True)
class _Book:
    """볼 수 있는 재료 전부의 칸 상태 — 요약 · 전체 · 칸이 같은 판정을 본다."""

    specs: dict[str, cards.BlockSpec]
    keys: list[str]
    """열의 차례 — 레지스트리 차례, 그 뒤에 레지스트리가 모르는 항목란."""
    materials: list[_Material]
    """재료군 · 분류 · 이름 차례. 칸이 없는 재료도 든다(요약의 재료 수)."""
    cells: dict[uuid.UUID, dict[str, _Cell]]
    """칸이 있는 것만."""
    test_names: dict[str, str]


def _card_block_each() -> Any:
    """카드의 항목란을 줄로 펴는 lateral — `blocks` 의 한 칸이 한 줄이다."""
    blocks = case(
        (func.jsonb_typeof(PropertyCard.blocks) == "object", PropertyCard.blocks),
        else_=func.jsonb_build_object(),
    )
    return (
        func.jsonb_each(blocks)
        .table_valued(column("key", String), column("value", JSONB))
        .lateral("card_block")
    )


def _row_count(each: Any) -> Any:
    """항목란 표의 줄 수 — **줄은 안 나르고 DB 에서 길이만 잰다.** 소성 표 하나가 수천 점."""
    rows = each.c.value["rows"]
    return case((func.jsonb_typeof(rows) == "array", func.jsonb_array_length(rows)), else_=0)


def _has_values_sql(each: Any) -> Any:
    """값이 하나라도 있나 — SQL 로. **`_has_values` 와 같은 뜻이다**: `null` 과 빈 글자는
    값이 아니고, `_source`·`_reference` 는 값에 딸린 말이라 안 센다."""
    values = each.c.value["values"]
    slot = (
        func.jsonb_each(
            case(
                (func.jsonb_typeof(values) == "object", values),
                else_=func.jsonb_build_object(),
            )
        )
        .table_valued(column("key", String), column("value", JSONB))
        .alias("slot")
    )
    return (
        select(literal(1))
        .select_from(slot)
        .where(
            ~slot.c.key.endswith("_source", autoescape=True),
            ~slot.c.key.endswith("_reference", autoescape=True),
            func.jsonb_typeof(slot.c.value) != "null",
            slot.c.value != literal("", JSONB),
        )
        .exists()
    )


def _card_tally(
    db: Session, material_ids: Select[Any]
) -> dict[tuple[uuid.UUID, str], tuple[int, int, int]]:
    """(재료, 항목란) → (확정 장 수, 초안 장 수, 모든 장 수). **이름만 있는 항목란은 안 센다**
    — 값도 표도 비었으면 볼 것이 없다."""
    each = _card_block_each()
    found: dict[tuple[uuid.UUID, str], tuple[int, int, int]] = {}
    for material_id, key, published, draft, total in db.execute(
        select(
            PropertyCard.material_id,
            each.c.key,
            func.count().filter(PropertyCard.status == "published"),
            func.count().filter(PropertyCard.status == "draft"),
            func.count(),
        )
        .select_from(PropertyCard)
        .join(each, true())
        .where(
            PropertyCard.material_id.in_(material_ids),
            or_(_row_count(each) > 0, _has_values_sql(each)),
        )
        .group_by(PropertyCard.material_id, each.c.key)
    ).all():
        found[(material_id, str(key))] = (int(published), int(draft), int(total))
    return found


def _declared_items(db: Session, material_ids: Select[Any]) -> dict[uuid.UUID, set[str]]:
    """재료 → 값이 적힌 선언 항목의 이름. **선언 물성 전체를 안 나른다** — 이름만.

    `declared_slots._declared_by_key` 와 같은 조건이다: 첫 점에 SI 값이 숫자로 있어야 한다.
    """
    rows = case(
        (
            func.jsonb_typeof(Material.declared_properties) == "array",
            Material.declared_properties,
        ),
        else_=func.jsonb_build_array(),
    )
    row = (
        func.jsonb_array_elements(rows).table_valued(column("value", JSONB)).lateral("stated")
    )
    found: dict[uuid.UUID, set[str]] = {}
    for material_id, item in db.execute(
        select(Material.id, row.c.value["item"].astext)
        .select_from(Material)
        .join(row, true())
        .where(
            Material.id.in_(material_ids),
            func.jsonb_typeof(row.c.value["points"][0]["value_si"]) == "number",
        )
        .distinct()
    ).all():
        if item:
            found.setdefault(material_id, set()).add(str(item))
    return found


def _item_blocks(db: Session, specs: dict[str, cards.BlockSpec]) -> dict[str, set[str]]:
    """선언 항목 이름 → 그 값이 갈 항목란들. 이름 → 물성 키(`property_links`) → 그 키를
    든 칸 — `declared_slots.fillable` 이 걷는 사슬 그대로다."""
    by_key: dict[str, set[str]] = {}
    for spec in specs.values():
        for slot in spec.produces:
            if slot.property_key:
                by_key.setdefault(slot.property_key, set()).add(spec.key)
    return {item: by_key[key] for item, key in item_property_map(db).items() if key in by_key}


def _adopted_by_material(
    db: Session, user: User, *, material_id: uuid.UUID | None = None
) -> dict[uuid.UUID, dict[str, tuple[str, int]]]:
    """재료 → 시험 종류 key → (이름, 채택된 시험 수). **채택된 것만** — 채택 전 값은
    카드에도 통계에도 안 실린다(ADR 0007)."""
    runs = _runs(db, user).subquery()
    query = (
        select(Sample.material_id, TestType.key, TestType.label, func.count(TestRun.id))
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .join(TestType, TestType.id == TestRun.test_type_id)
        .where(
            TestRun.id.in_(select(runs.c.id)),
            TestRun.adopted_result_id.is_not(None),
            Specimen.deleted_at.is_(None),
            Sample.deleted_at.is_(None),
        )
        .group_by(Sample.material_id, TestType.key, TestType.label)
    )
    if material_id is not None:
        query = query.where(Sample.material_id == material_id)
    out: dict[uuid.UUID, dict[str, tuple[str, int]]] = {}
    for found_id, key, label, count in db.execute(query).all():
        # 같은 key 의 시험 종류가 부서마다 있을 수 있다 — key 로 합친다.
        mine = out.setdefault(found_id, {})
        name, before = mine.get(str(key), (str(label), 0))
        mine[str(key)] = (name, before + int(count))
    return out


def _book(db: Session, user: User) -> _Book:
    """볼 수 있는 재료 전부의 칸 상태. 요약 · 전체 · 칸이 **같은 판정**을 쓰게 한 곳에 둔다."""
    cards.load_builtin()
    specs = {spec.key: spec for spec in cards.list_blocks()}
    visible = permissions.visible_material_ids(db, user)
    materials = [
        _Material(id=found, name=str(name), family=str(family), category=str(category))
        for found, name, family, category in db.execute(
            select(Material.id, Material.record_name, Material.family, Material.category)
            .where(Material.id.in_(visible), Material.deleted_at.is_(None))
            .order_by(Material.family, Material.category, Material.record_name)
        ).all()
    ]
    tally = _card_tally(db, visible)
    adopted = _adopted_by_material(db, user)
    stated = _declared_items(db, visible)
    item_blocks = _item_blocks(db, specs)

    # **레지스트리가 모르는 항목란도 열로 세운다** — 꺼진 항목란이나 사라진 확장의 것이
    # 카드에 남아 있으면, 빼는 순간 그 카드는 「그 항목이 없다」 로 읽힌다.
    keys = list(specs) + sorted({key for _, key in tally} - set(specs))
    cells: dict[uuid.UUID, dict[str, _Cell]] = {}
    for material in materials:
        tests_here = adopted.get(material.id, {})
        declared_here: set[str] = set()
        for item in stated.get(material.id, ()):
            declared_here |= item_blocks.get(item, set())
        mine: dict[str, _Cell] = {}
        for key in keys:
            spec = specs.get(key)
            tests = spec is not None and any(test in tests_here for test in spec.from_tests)
            declared = key in declared_here
            found = tally.get((material.id, key))
            if found:
                published, draft, total = found
                state = "published" if published else "draft" if draft else "deprecated"
                mine[key] = _Cell(state, total, tests=tests, declared=declared)
            elif tests or declared:
                mine[key] = _Cell("source", 0, tests=tests, declared=declared)
        if mine:
            cells[material.id] = mine

    test_names = {
        str(key): str(label)
        for key, label in db.execute(
            select(TestType.key, TestType.label)
            .where(TestType.is_active.is_(True))
            .order_by(TestType.label)
        ).all()
    }
    return _Book(
        specs=specs, keys=keys, materials=materials, cells=cells, test_names=test_names
    )


def _columns(book: _Book, material_ids: Iterable[uuid.UUID]) -> list[dict[str, Any]]:
    """열 — 항목란마다 **주어진 재료 가운데** 상태별 재료 수. 아무 재료에도 없어도 선다."""
    counts: dict[str, dict[str, int]] = {key: dict.fromkeys(STATES, 0) for key in book.keys}
    for material_id in material_ids:
        for key, cell in book.cells.get(material_id, {}).items():
            counts[key][cell.state] += 1
    out: list[dict[str, Any]] = []
    for key in book.keys:
        spec = book.specs.get(key)
        tally = counts[key]
        out.append(
            {
                "key": key,
                "label": spec.label if spec else key,
                "help": spec.help
                if spec
                else "등록되지 않은 항목란입니다 — 꺼졌거나 만든 확장이 사라졌습니다.",
                "tests": [
                    book.test_names.get(test, test)
                    for test in (spec.from_tests if spec else ())
                ],
                "registered": spec is not None,
                "published_materials": tally["published"],
                "card_materials": tally["published"] + tally["draft"],
                "deprecated_materials": tally["deprecated"],
                "source_materials": tally["source"],
            }
        )
    return out


def _has_card(cells: dict[str, _Cell]) -> bool:
    """카드에 든 칸이 하나라도 있나 — 사용 중지한 카드뿐이어도 「있었다」 로 센다."""
    return any(cell.state != "source" for cell in cells.values())


def card_item_summary(db: Session, user: User) -> dict[str, Any]:
    """요약 — 재료군·분류 x 카드 항목란. **줄은 분류다**: 재료가 1만이어도 줄은 분류 수다.

    칸은 상태별 재료 수(`STATES`). 분류의 재료 수는 칸이 없는 재료까지 센다 — 시험 쪽에서
    세면 카드가 하나도 없는 분류가 표에서 사라지는데, 그 줄이 요점이다(`coverage` 와 같은
    판단).
    """
    book = _book(db, user)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    with_cards = 0
    for material in book.materials:
        group = groups.setdefault(
            (material.family, material.category),
            {
                "family": material.family,
                "category": material.category,
                "material_count": 0,
                "card_materials": 0,
                "source_only_materials": 0,
                "cells": {},
            },
        )
        group["material_count"] += 1
        mine = book.cells.get(material.id, {})
        if _has_card(mine):
            group["card_materials"] += 1
            with_cards += 1
        elif mine:
            group["source_only_materials"] += 1
        for key, cell in mine.items():
            tally = group["cells"].setdefault(key, dict.fromkeys(STATES, 0))
            tally[cell.state] += 1
    return {
        "columns": _columns(book, (one.id for one in book.materials)),
        "groups": list(groups.values()),
        "material_total": len(book.materials),
        "card_material_count": with_cards,
        "source_only_count": len(book.cells) - with_cards,
    }


def card_item_rows(
    db: Session,
    user: User,
    *,
    q: str | None,
    family: str | None,
    category: str | None,
    item: str | None,
    with_sources: bool,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """전체 — 재료 줄. **서버가 거르고 자른다**: 한 번에 `limit` 줄, 거른 뒤의 수는 `total`.

    시험·선언만 있는 칸은 `with_sources` 일 때만 센다 — 줄에도, 열의 재료 수에도. 열은
    **거른 재료 가운데**서 센다: 분류로 들어오면 「이 분류에서 점탄성이 있는 재료」 가 된다.
    """

    def shown(cell: _Cell | None) -> bool:
        return cell is not None and (with_sources or cell.state != "source")

    book = _book(db, user)
    needle = (q or "").strip().lower()
    picked: list[_Material] = []
    for material in book.materials:
        mine = book.cells.get(material.id, {})
        if not any(shown(cell) for cell in mine.values()):
            continue
        if family is not None and material.family != family:
            continue
        if category is not None and material.category != category:
            continue
        if item and not shown(mine.get(item)):
            continue
        if needle and not any(
            needle in text.lower()
            for text in (material.name, material.family, material.category)
        ):
            continue
        picked.append(material)

    return {
        "columns": _columns(book, (one.id for one in picked)),
        "rows": [
            {
                "material_id": one.id,
                "material_name": one.name,
                "family": one.family,
                "category": one.category,
                "cells": {
                    key: {
                        "state": cell.state,
                        "card_count": cell.card_count,
                        "tests": cell.tests,
                        "declared": cell.declared,
                    }
                    for key, cell in book.cells[one.id].items()
                    if shown(cell)
                },
            }
            for one in picked[offset : offset + limit]
        ],
        "total": len(picked),
        "limit": limit,
        "offset": offset,
    }


@dataclass(frozen=True)
class _CardBlock:
    """카드 한 장에 든 항목란 하나 — 표는 줄 수만."""

    card_id: uuid.UUID
    card_label: str
    status: str
    values: dict[str, Any]
    row_count: int


def _card_blocks(db: Session, material_id: uuid.UUID, key: str) -> list[_CardBlock]:
    """재료 하나의 카드들에서 항목란 하나 — 값은 꺼내고 **표는 줄 수만.**"""
    each = _card_block_each()
    found: list[_CardBlock] = []
    for card_id, label, status, values, count in db.execute(
        select(
            PropertyCard.id,
            PropertyCard.label,
            PropertyCard.status,
            each.c.value["values"],
            _row_count(each),
        )
        .select_from(PropertyCard)
        .join(each, true())
        .where(PropertyCard.material_id == material_id, each.c.key == key)
    ).all():
        values = dict(values) if isinstance(values, dict) else {}
        count = int(count or 0)
        if not count and not _has_values(values):
            continue
        found.append(
            _CardBlock(
                card_id=card_id,
                card_label=str(label),
                status=str(status),
                values=values,
                row_count=count,
            )
        )
    return sorted(found, key=lambda one: (_STATUS_RANK.get(one.status, 9), one.card_label))


def _has_values(values: dict[str, Any]) -> bool:
    """값이 하나라도 있나. **`_has_values_sql` 과 같은 뜻이다** — 요약이 센 칸을 누르면
    그 카드가 떠야 한다."""
    return any(
        value not in (None, "")
        for key, value in values.items()
        if not key.endswith(("_source", "_reference"))
    )


def _shown_values(
    spec: cards.BlockSpec | None, values: dict[str, Any]
) -> list[dict[str, Any]]:
    """카드에 **실제로 든** 값 — 항목란이 선언한 이름으로, 선언 차례대로.

    선언 안 한 키는 화면에 안 뜬다(`BlockSpec.produces` 의 규칙). 레지스트리가 모르는
    항목란(꺼졌거나 사라진 확장)은 이름도 단위도 모르므로 키만 적는다 — 단위를 모르는
    SI 숫자를 그대로 보이면 Pa 를 MPa 로 읽는다.
    """
    if spec is None:
        return [
            {"label": key, "value": None, "si_unit": "1"}
            for key, value in values.items()
            if value not in (None, "") and not key.endswith(("_source", "_reference"))
        ]
    out: list[dict[str, Any]] = []
    for item in spec.produces:
        value = values.get(item.key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            out.append({"label": item.label, "value": float(value), "si_unit": item.si_unit})
        elif isinstance(value, str) and value.strip():
            out.append({"label": item.label, "value": value.strip(), "si_unit": "1"})
    return out


def card_item_cell(
    db: Session, user: User, material_id: uuid.UUID, key: str
) -> dict[str, Any]:
    """칸 하나 — **무엇까지 들어 있나.** 누를 때만 받는다: 카드마다 든 값, 그 항목란을
    내는 시험의 채택 결과, 그 칸으로 갈 선언 물성.

    요약 · 전체와 같은 판정이다 — 칸의 상태는 `_book` 과 같은 규칙으로 정한다.
    """
    material = db.scalar(
        select(Material).where(
            Material.id == material_id,
            Material.id.in_(permissions.visible_material_ids(db, user)),
        )
    )
    if material is None:
        raise NotFound("MNX-STATISTICS-0005", "재료를 찾을 수 없습니다.")
    cards.load_builtin()
    spec = next((one for one in cards.list_blocks() if one.key == key), None)
    found = _card_blocks(db, material_id, key)
    tests_here = _adopted_by_material(db, user, material_id=material_id).get(material_id, {})
    tests = [
        {"key": test, "label": tests_here[test][0], "adopted_count": tests_here[test][1]}
        for test in (spec.from_tests if spec else ())
        if test in tests_here
    ]
    fills = {one.key: one for one in declared_slots.fillable(db, material)}
    stated = [
        {"label": slot[1], "value": slot[3], "si_unit": slot[2]}
        for slot in (fills[key].slots if key in fills else ())
    ]
    if not found and not tests and not stated:
        raise NotFound(
            "MNX-STATISTICS-0006",
            "이 재료의 그 항목에는 카드도, 그 항목을 내는 시험도, 그 칸으로 갈 선언 물성도 "
            "없습니다.",
        )
    if found:
        state = min((one.status for one in found), key=lambda one: _STATUS_RANK.get(one, 9))
        if state not in _STATUS_RANK:
            state = "deprecated"
    else:
        state = "source"
    return {
        "state": state,
        "cards": [
            {
                "id": one.card_id,
                "label": one.card_label,
                "status": one.status,
                "values": _shown_values(spec, one.values),
                "row_count": one.row_count,
            }
            for one in found
        ],
        "tests": tests,
        "declared": stated,
    }
