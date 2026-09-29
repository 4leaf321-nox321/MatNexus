"""시편의 두께가 **재료의 기준 두께와 얼마나 다른가**(2026-09-29).

두께가 다른 재료에 잘못 넣은 시편을 찾는 자리다 — 찾으면 「다른 두께로 옮기기」
(ADR 0042)로 옮긴다. 개발 DB 에서 기준과 20% 넘게 다른 시편 7개 가운데 6개는 **시험
파일이 잰 두께**에서만 드러났다(시편 칸에는 안 적혀 있었다). 그래서 둘 다 본다.

## 무엇을 견주나

    실측    시편에 적은 두께(치수 칸 → 옛 두께 칸 순, `specimen_size` 와 같은 순서)
            + 시험마다 파일이 잰 두께(`TestRun.dimensions`)
    기준    재료의 스펙 두께(`Material.spec_thickness_m`) — 없거나 0 이면 견주지 않는다

규격의 공칭과 재료에서 물려받은 두께는 **잰 것이 아니라서** 뺀다. 물려받은 두께는 기준
그 자체라 늘 0% 다.

실측이 여럿이면(시험 셋이 잰 값) **가장 크게 어긋난 것**으로 판정하고 그 값을 낸다 —
하나라도 크게 어긋나면 그 시편은 살펴볼 까닭이 있다.

## 거르기 · 줄마다의 표시 · 선택지 옆의 수가 **같은 식**을 탄다

셋이 따로 계산되면 「10% 이상 (3)」 을 골랐는데 두 줄이 나오는 일이 생긴다. 그래서 식은
여기 하나다(`worst`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Float,
    Select,
    String,
    Subquery,
    case,
    func,
    literal_column,
    select,
    union_all,
)
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import TestRun

#: 거르기 선택지. **판재 압연 공차는 대개 몇 % 안쪽이다** — 개발 DB 의 실측은 거의
#: 2% 안에 들었고, 다른 두께에 넣은 것은 20~25% 로 나왔다(0.8t 재료에 1.0 mm).
STEPS = (0.05, 0.10, 0.20)

#: 경계의 부동소수. 0.9 mm / 1.0 mm 는 0.09999999999999998 로 나와 「10% 이상」 에서
#: 빠진다 — 사람에게는 정확히 10% 다.
EPSILON = 1e-9


@dataclass(frozen=True)
class Gap:
    """시편 하나의 판정 — **잰 값 가운데 가장 크게 어긋난 것.**"""

    spec: float
    """재료의 기준 두께(m)."""
    value: float
    """견준 실측 두께(m)."""
    deviation: float
    """(실측 - 기준) / 기준. 부호가 있다 — +0.2 는 20% 두껍다."""
    source: str
    """`measured` 시편에 적은 값 · `run` 시험 파일이 잰 값."""


def _number(element: Any) -> ColumnElement[float]:
    """JSON 칸의 숫자. **`CASE` 로 감싼다** — `WHERE a AND b` 는 계산 순서를 보장하지 않아서,
    숫자가 아닌 값이 하나라도 있으면 형 검사보다 변환이 먼저 돌아 쿼리가 통째로 터진다."""
    return case(
        (func.jsonb_typeof(element) == "number", element.astext.cast(Float)), else_=None
    )


def _own_thickness() -> ColumnElement[float]:
    """시편에 적은 두께 — 치수 칸이 먼저, 없으면 옛 두께 칸(`specimen_size._sizes` 와 같다)."""
    return func.coalesce(
        _number(Specimen.dimensions["thickness"]), func.nullif(Specimen.thickness_m, 0)
    )


def _candidates(ids: Sequence[uuid.UUID] | None) -> Subquery:
    """견줄 실측 두께 전부 — 시편 하나에 여럿일 수 있다(시험마다 잰 값)."""
    own = _own_thickness()
    # 0 은 두께가 아니다 — 「안 적었다」 와 같다(`specimen_size._spec_thickness`).
    mine: Select[tuple[uuid.UUID, float, str]] = select(
        Specimen.id.label("specimen_id"),
        own.label("value"),
        literal_column("'measured'", String).label("source"),
    ).where(own > 0)
    measured = _number(TestRun.dimensions["thickness"])
    runs: Select[tuple[uuid.UUID, float, str]] = select(
        TestRun.specimen_id.label("specimen_id"),
        measured.label("value"),
        literal_column("'run'", String).label("source"),
    ).where(TestRun.deleted_at.is_(None), measured > 0)
    if ids is not None:
        mine = mine.where(Specimen.id.in_(ids))
        runs = runs.where(TestRun.specimen_id.in_(ids))
    return union_all(mine, runs).subquery("thickness_candidates")


def worst(ids: Sequence[uuid.UUID] | None = None) -> Subquery:
    """시편마다 **가장 크게 어긋난** 실측 하나 — `specimen_id · value · source · spec ·
    deviation · gap`. 기준 두께가 없는 재료의 시편은 안 나온다."""
    found = _candidates(ids)
    spec = Material.spec_thickness_m
    deviation = (found.c.value - spec) / spec
    gap = func.abs(deviation)
    return (
        select(
            found.c.specimen_id,
            found.c.value,
            found.c.source,
            spec.label("spec"),
            deviation.label("deviation"),
            gap.label("gap"),
        )
        .select_from(found)
        .join(Specimen, Specimen.id == found.c.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .join(Material, Material.id == Sample.material_id)
        .where(spec > 0)
        # 같으면 시편에 적은 값이 먼저다(`measured` < `run`) — 사람이 적은 것을 보인다.
        .distinct(found.c.specimen_id)
        .order_by(found.c.specimen_id, gap.desc(), found.c.source)
        .subquery("thickness_gap")
    )


def at_least(
    query: Select[tuple[Specimen, Sample, Material]], step: float
) -> Select[tuple[Specimen, Sample, Material]]:
    """기준 두께와 `step`(비율) 이상 다른 시편만. **서버가 거른다** — 화면이 이 쪽에서
    거르면 다음 쪽의 것이 조용히 빠진다."""
    gaps = worst()
    return query.join(gaps, gaps.c.specimen_id == Specimen.id).where(
        gaps.c.gap >= step - EPSILON
    )


def gaps_for(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Gap]:
    """이 쪽에 실린 시편들의 판정 — **한 번에 읽는다**(시편마다 물으면 N+1)."""
    if not ids:
        return {}
    gaps = worst(ids)
    return {
        row.specimen_id: Gap(
            spec=float(row.spec),
            value=float(row.value),
            deviation=float(row.deviation),
            source=str(row.source),
        )
        for row in db.execute(select(gaps))
    }


def tally(db: Session, scope: Sequence[ColumnElement[bool]]) -> list[tuple[float, int]]:
    """선택지마다 몇 개인가 — `scope` 는 시편 목록의 가시 범위(시편·시료·재료)."""
    gaps = worst()
    row = db.execute(
        select(*[func.count().filter(gaps.c.gap >= step - EPSILON) for step in STEPS])
        .select_from(Specimen)
        .join(Sample, Specimen.sample_id == Sample.id)
        .join(Material, Sample.material_id == Material.id)
        .join(gaps, gaps.c.specimen_id == Specimen.id)
        .where(*scope)
    ).one()
    return [(step, int(count)) for step, count in zip(STEPS, row, strict=True)]
