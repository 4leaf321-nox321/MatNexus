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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.modules.tests.models import TestRun
from app.modules.workbench.models import WorkbenchItem
from app.modules.workbench.schemas import ItemOut

#: 사라진 대상에 붙는 이름. 화면이 그대로 보여 준다.
GONE = "사라졌습니다"


def _test_runs(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    rows: list[TestRun] = (
        list(db.scalars(select(TestRun).where(TestRun.id.in_(ids)))) if ids else []
    )
    return {
        row.id: (
            row.record_name,
            # **상태가 곧 다음 할 일이다** — 읽기 실패인지, 채택까지 끝났는지.
            "채택됨" if row.adopted_result_id else row.status,
        )
        for row in rows
        if row.deleted_at is None
    }


def _materials(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    rows: list[Material] = (
        list(db.scalars(select(Material).where(Material.id.in_(ids)))) if ids else []
    )
    return {
        row.id: (row.record_name, row.category or "") for row in rows if row.deleted_at is None
    }


def _cards(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
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
    found: dict[uuid.UUID, tuple[str, str]] = {}
    for row in rows:
        material = materials.get(row.material_id)
        name = material.record_name if material else "?"
        found[row.id] = (row.label, f"{name} · {row.status}")
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

    found: dict[str, dict[uuid.UUID, tuple[str, str]]] = {
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
                label=hit[0] if hit else GONE,
                detail=hit[1] if hit else None,
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
