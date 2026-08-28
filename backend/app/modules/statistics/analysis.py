"""물성 분석 — **다섯 화면이 같은 관측 하나를 다르게 본다.**

    비교        재료 몇 개를 나란히
    분포        사업부·재료군별 흩어짐
    사양 대비   선언한 값과 잰 값의 차이
    추이        해가 가며 값이 흐르는가
    커버리지    무엇을 아직 안 쟀는가

앞 넷은 전부 **채택된 처리 결과의 스칼라**를 재료·사업부·시간으로 접은 것이다.
그래서 모으는 코드는 하나고(`collect`), 화면마다 접는 방법만 다르다 — 각자 질의를
쓰면 「비교의 인장강도」 와 「분포의 인장강도」 가 다른 수를 말하는 날이 온다.

## 무엇을 세는가

**채택된 결과(`TestRun.adopted_result_id`)만.** 채택은 「이 시험의 물성은 이것」 이라는
사람의 결정이고(ADR 0007), 그것을 안 거친 값은 아직 물성이 아니다. 안 채택된 것은
세지 않되 **몇 건이 빠졌는지 함께 돌려준다** — 조용히 빼면 n 이 왜 이 수인지 모른다.

커버리지만 스칼라를 안 본다. 「쟀는가」 는 시험이 있는가지 값이 나왔는가가 아니다.
"""

from __future__ import annotations

import statistics as stats
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun, TestType
from app.shared import divisions as divisions_order
from app.shared import permissions


@dataclass(frozen=True)
class Observation:
    """잰 값 하나 — **어느 재료의, 어느 사업부가, 언제, 무엇을.**"""

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
    """재료-시험종류 격자. **빈 칸이 다음에 할 시험이다.**

    스칼라를 안 본다 — 「쟀는가」 는 시험이 있는가지 값이 나왔는가가 아니다. 다만
    **채택까지 간 수를 따로 센다**: 올리기만 하고 처리를 안 한 것과 물성이 나온
    것은 다르고, 그 차이가 곧 남은 일이다.
    """
    runs = _runs(db, user).subquery()
    rows = db.execute(
        select(
            Material.id,
            Material.record_name,
            Material.family,
            TestType.key,
            TestType.label,
            func.count(TestRun.id),
            func.count(TestRun.adopted_result_id),
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
        .group_by(
            Material.id,
            Material.record_name,
            Material.family,
            TestType.key,
            TestType.label,
        )
    ).all()

    types: dict[str, str] = {}
    materials: dict[uuid.UUID, dict[str, Any]] = {}
    for material_id, name, family, type_key, type_label, total, adopted in rows:
        types[str(type_key)] = str(type_label)
        entry = materials.setdefault(
            material_id,
            {"material_id": material_id, "material_name": name, "family": family, "cells": {}},
        )
        entry["cells"][str(type_key)] = {
            "run_count": int(total),
            "adopted_count": int(adopted),
        }
    return {
        "test_types": [{"key": key, "label": label} for key, label in sorted(types.items())],
        "materials": sorted(materials.values(), key=lambda one: str(one["material_name"])),
    }
