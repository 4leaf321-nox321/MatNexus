"""워크벤치 — 담긴 것을 **읽을 때 푼다.**

담을 때는 `kind` 와 `target_id` 만 적는다(ADR 0025 — 외래키를 안 건다). 그래서 이름과
상태는 **읽는 순간** 찾아야 한다.

## 사라진 것을 사라졌다고 말한다

가리키던 시험이 지워졌으면 그 줄은 「사라졌습니다」 로 온다. 빼 버리면 「내가 담았던
여덟 건이 왜 일곱이지」 에 답할 데가 없다.

## 한 번에 읽는다

종류마다 한 번씩만 조회한다 — 담긴 것이 스무 건이면 스무 번 부르는 것이 N+1 이고,
그 규칙은 이 저장소가 목록마다 지켜 온 것이다.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.modules.tests.models import TestRun
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.modules.workbench.models import WorkbenchItem
from app.modules.workbench.schemas import ItemOut


@dataclass(frozen=True)
class Resolved:
    """푼 결과 하나 — 이름·한 줄·**판정에 쓸 사실**.

    `facts` 를 서버가 채우는 이유: 화면이 「이 단계는 끝났나」 를 판정하려면 숫자가
    필요한데, 워크벤치가 그것을 도메인 API 로 직접 가져오면 **남의 도메인을 알게
    된다**(ADR 0024 의 경계). 세는 곳을 한 곳에 두고 그 결과만 건넨다.
    """

    label: str
    detail: str = ""
    facts: dict[str, int] = field(default_factory=dict)


def _count_by_run(
    db: Session, column: Any, model: Any, runs: list[TestRun]
) -> dict[uuid.UUID, int]:
    if not runs:
        return {}
    rows = db.execute(
        select(column, func.count())
        .where(column.in_([one.id for one in runs]))
        .group_by(column)
    )
    return {run_id: int(count) for run_id, count in rows}


def _prony_by_run(db: Session, runs: list[TestRun]) -> dict[uuid.UUID, int]:
    """맞춘 계수 수. **마스터커브를 거쳐 시험에 매달린다.**"""
    if not runs:
        return {}
    rows = db.execute(
        select(MasterCurve.test_run_id, func.count())
        .join(PronyFit, PronyFit.master_curve_id == MasterCurve.id)
        .where(MasterCurve.test_run_id.in_([one.id for one in runs]))
        .group_by(MasterCurve.test_run_id)
    )
    return {run_id: int(count) for run_id, count in rows}


#: 사라진 대상에 붙는 이름. 화면이 그대로 보여 준다.
GONE = "사라졌습니다"


def _test_runs(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Resolved]:
    rows: list[TestRun] = (
        list(db.scalars(select(TestRun).where(TestRun.id.in_(ids)))) if ids else []
    )
    live = [row for row in rows if row.deleted_at is None]
    # **한 번에 센다.** 담긴 것이 스무 건이면 스무 번 부르는 것이 N+1 이다.
    curves = _count_by_run(db, MasterCurve.test_run_id, MasterCurve, live)
    fits = _prony_by_run(db, live)
    return {
        row.id: Resolved(
            label=row.record_name,
            # **상태가 곧 다음 할 일이다** — 읽기 실패인지, 채택까지 끝났는지.
            detail="채택됨" if row.adopted_result_id else row.status,
            # **판정의 재료는 서버가 준다.** 화면이 도메인 API 를 따로 부르면
            # 워크벤치가 남의 도메인을 알게 되고, 그 방향은 되돌리기 어렵다.
            facts={
                "master_curves": curves.get(row.id, 0),
                "prony_fits": fits.get(row.id, 0),
                "adopted": 1 if row.adopted_result_id else 0,
                # 1이면 겹칠 것이 없다(변형률 스윕). 0 은 「안 세어 봤다」 가 아니라
                # 여기서는 「모른다」 를 뜻하므로 `-1` 로 구분한다.
                "temperature_steps": (
                    row.temperature_step_count
                    if row.temperature_step_count is not None
                    else -1
                ),
            },
        )
        for row in live
    }


def _materials(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Resolved]:
    rows: list[Material] = (
        list(db.scalars(select(Material).where(Material.id.in_(ids)))) if ids else []
    )
    return {
        row.id: Resolved(label=row.record_name, detail=row.category or "")
        for row in rows
        if row.deleted_at is None
    }


def _cards(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Resolved]:
    rows: list[PropertyCard] = (
        list(db.scalars(select(PropertyCard).where(PropertyCard.id.in_(ids)))) if ids else []
    )
    # **재료도 한 번에 읽는다.** 카드마다 부르면 담긴 수만큼 왕복한다.
    materials = {
        one.id: one
        for one in db.scalars(
            select(Material).where(Material.id.in_({row.material_id for row in rows}))
        )
    }
    # **카드는 소프트 삭제가 없다** — 지우면 행이 사라진다(내리는 것은
    # `deprecated` 상태다). 그래서 여기서 거를 것도 없고, 지워진 카드는 조회에서
    # 안 나와 자연히 「사라졌습니다」 가 된다.
    found: dict[uuid.UUID, Resolved] = {}
    for row in rows:
        material = materials.get(row.material_id)
        name = material.record_name if material else "?"
        found[row.id] = Resolved(
            label=row.label,
            detail=f"{name} · {row.status}",
            # 확정 여부는 「내보내도 되나」 를 가르는 사실이라 숫자로도 준다.
            facts={"published": 1 if row.status == "published" else 0},
        )
    return found


#: 종류마다 어떻게 푸나. 새 종류가 생기면 여기 한 줄이다.
RESOLVERS = {
    "test_run": _test_runs,
    "material": _materials,
    "card": _cards,
}


def resolve(db: Session, items: Sequence[WorkbenchItem]) -> list[ItemOut]:
    """담긴 것들에 이름을 붙인다. **사라진 것도 줄을 지킨다.**"""
    by_kind: dict[str, set[uuid.UUID]] = {}
    for item in items:
        by_kind.setdefault(item.kind, set()).add(item.target_id)

    found: dict[str, dict[uuid.UUID, Resolved]] = {
        kind: RESOLVERS[kind](db, ids) if kind in RESOLVERS else {}
        for kind, ids in by_kind.items()
    }

    out: list[ItemOut] = []
    for item in items:
        hit = found.get(item.kind, {}).get(item.target_id)
        out.append(
            ItemOut(
                id=item.id,
                kind=item.kind,
                target_id=item.target_id,
                label=hit.label if hit else GONE,
                detail=hit.detail if hit else None,
                facts=dict(hit.facts) if hit else {},
                missing=hit is None,
                note=item.note,
                added_at=item.added_at,
            )
        )
    return out


def owner_name(db: Session, owner_id: uuid.UUID | None) -> str | None:
    if owner_id is None:
        return None
    found = db.get(User, owner_id)
    return found.display_name if found else None
