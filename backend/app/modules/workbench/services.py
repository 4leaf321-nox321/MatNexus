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
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import Curve, TestRun
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
    material_id: uuid.UUID | None = None


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


def _cards_by_run(
    db: Session, runs: list[TestRun], owners: dict[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, int]:
    """이 시험에서 나온 물성 카드가 몇인가.

    **카드가 자기 근거를 들고 있어서**(`source.test_run_ids`) 셀 수 있다 — 사람이
    만든 카드를 바구니에 도로 담아 줘야 「만들었다」 를 아는 구조가 아니다. 담기는
    나중에 이어서 하려고 모아 두는 일이지, 다 한 일을 신고하는 절차가 아니다.

    재료로 좁혀 읽는다. 카드 표 전체를 훑으면 재료가 늘수록 느려지고, 담긴 시험의
    카드는 그 시험의 재료 아래에만 있다. `blocks` 는 카드 하나가 수천 점이라
    **읽지 않는다** — 근거 한 칸만 꺼낸다.
    """
    wanted = {one.id for one in runs}
    materials = {owners[one.id] for one in runs if one.id in owners}
    if not wanted or not materials:
        return {}
    counts: dict[uuid.UUID, int] = {}
    for (sources,) in db.execute(
        select(PropertyCard.source["test_run_ids"]).where(
            PropertyCard.material_id.in_(materials),
            # **사용 중지된 카드는 「있다」 가 아니다** — 쓰지 말라는 표시다.
            PropertyCard.status != "deprecated",
        )
    ):
        for raw in sources if isinstance(sources, list) else []:
            try:
                made_from = uuid.UUID(str(raw))
            except ValueError:
                continue
            if made_from in wanted:
                counts[made_from] = counts.get(made_from, 0) + 1
    return counts


def _material_by_run(db: Session, runs: list[TestRun]) -> dict[uuid.UUID, uuid.UUID]:
    """시험이 어느 재료의 것인가 — **시편 → 시료 → 재료**.

    화면이 「이 시험의 재료로 가기」 를 그릴 수 있어야 한다. 글로벌 피팅은 재료 화면에
    있는데(ADR 0020), 바구니에는 시험만 담기기 때문이다. **주소가 아니라 id 를 준다** —
    화면의 주소 체계를 서버가 알면 라우팅을 고칠 때마다 서버도 고쳐야 한다.
    """
    if not runs:
        return {}
    rows = db.execute(
        select(TestRun.id, Sample.material_id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(TestRun.id.in_([one.id for one in runs]))
    )
    return {run_id: material_id for run_id, material_id in rows}


def _channels_by_run(db: Session, runs: list[TestRun]) -> dict[uuid.UUID, int]:
    """파일에서 실제로 잡힌 채널 수. **열 매핑이 됐나** 를 이걸로 본다.

    정의에 있어도 파일에 없을 수 있어서 `Curve.channels` 는 「실제로 들어 있는 것」
    이다 — 새 장비 파일을 붙일 때 사람이 확인해야 하는 것이 정확히 그 차이다.
    측정 곡선만 센다(장비가 계산한 표는 열 매핑의 증거가 아니다).
    """
    if not runs:
        return {}
    found: dict[uuid.UUID, set[str]] = {}
    for run_id, channels in db.execute(
        select(Curve.test_run_id, Curve.channels).where(
            Curve.test_run_id.in_([one.id for one in runs]), Curve.kind == "measured"
        )
    ):
        found.setdefault(run_id, set()).update(channels or [])
    return {run_id: len(keys) for run_id, keys in found.items()}


def _results_by_run(db: Session, runs: list[TestRun]) -> dict[uuid.UUID, int]:
    """처리 결과 수. **레시피가 돌았나** 를 이걸로 본다 — 결과는 불변이라 다시
    돌리면 행이 는다(그래서 「몇 번 돌았나」 가 아니라 「돌았나」 로 읽는다)."""
    return _count_by_run(db, ProcessingResult.test_run_id, ProcessingResult, runs)


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

#: 담긴 종류마다 실어 보내는 **사실의 이름**. 화면의 단계 판정이 이 이름으로 읽는다
#: (`modules/workbench/workflows.ts`).
#:
#: **이름이 어긋나면 양쪽 시험이 다 통과하면서 화면만 조용히 틀린다** — 없는 키를
#: 읽으면 0이 되고, 0은 「아직 안 했다」 로 읽히므로 영원히 안 끝나는 단계가 된다.
#: 그래서 목록을 여기 못 박고 양쪽에서 검사한다.
FACT_KEYS = {
    "test_run": {
        "master_curves",
        "prony_fits",
        "cards",
        "adopted",
        "parsed",
        "results",
        "channels",
        "temperature_steps",
    },
    "material": {"cards", "published_cards"},
    "card": {"published", "samples", "notes"},
}


def _test_runs(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Resolved]:
    rows: list[TestRun] = (
        list(db.scalars(select(TestRun).where(TestRun.id.in_(ids)))) if ids else []
    )
    live = [row for row in rows if row.deleted_at is None]
    # **한 번에 센다.** 담긴 것이 스무 건이면 스무 번 부르는 것이 N+1 이다.
    curves = _count_by_run(db, MasterCurve.test_run_id, MasterCurve, live)
    fits = _prony_by_run(db, live)
    owners = _material_by_run(db, live)
    made = _cards_by_run(db, live, owners)
    processed = _results_by_run(db, live)
    channels = _channels_by_run(db, live)
    return {
        row.id: Resolved(
            label=row.record_name,
            # **상태가 곧 다음 할 일이다** — 읽기 실패인지, 채택까지 끝났는지.
            detail="채택됨" if row.adopted_result_id else row.status,
            material_id=owners.get(row.id),
            # **판정의 재료는 서버가 준다.** 화면이 도메인 API 를 따로 부르면
            # 워크벤치가 남의 도메인을 알게 되고, 그 방향은 되돌리기 어렵다.
            facts={
                "master_curves": curves.get(row.id, 0),
                "prony_fits": fits.get(row.id, 0),
                "cards": made.get(row.id, 0),
                "adopted": 1 if row.adopted_result_id else 0,
                # 오늘 들어온 것을 미는 데 필요한 둘 — 읽혔나, 처리됐나.
                "parsed": 1 if row.status == "parsed" else 0,
                "results": processed.get(row.id, 0),
                # 새 장비 파일을 붙일 때 보는 것 — 열이 채널로 잡혔나.
                "channels": channels.get(row.id, 0),
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


def _cards_by_material(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """재료마다 (카드 수, 확정 수). **해석에 넘기기 전에 뭐가 비었나** 를 이걸로 센다.

    사용 중지된 카드(`deprecated`)는 세지 않는다 — 쓰지 말라는 표시다. 세는 것이 목록이
    아니라 수뿐이므로 `blocks` 를 읽지 않는다(카드 하나의 표가 수천 점이다).
    """
    if not ids:
        return {}
    rows = db.execute(
        select(
            PropertyCard.material_id,
            func.count(),
            func.count().filter(PropertyCard.status == "published"),
        )
        .where(PropertyCard.material_id.in_(ids), PropertyCard.status != "deprecated")
        .group_by(PropertyCard.material_id)
    )
    return {
        material_id: (int(total), int(published)) for material_id, total, published in rows
    }


def _materials(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Resolved]:
    rows: list[Material] = (
        list(db.scalars(select(Material).where(Material.id.in_(ids)))) if ids else []
    )
    live = [row for row in rows if row.deleted_at is None]
    cards = _cards_by_material(db, {row.id for row in live})
    return {
        row.id: Resolved(
            label=row.record_name,
            detail=row.category or "",
            material_id=row.id,
            # 해석 덱을 갖출 때 묻는 것은 둘이다 — 카드가 있나, 확정됐나.
            facts={
                "cards": cards.get(row.id, (0, 0))[0],
                "published_cards": cards.get(row.id, (0, 0))[1],
            },
        )
        for row in live
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
            facts={
                "published": 1 if row.status == "published" else 0,
                # 확정 전에 보는 것 — **근거가 얼마나 두꺼운가.** 표본 하나로 만든
                # 카드는 만들 수는 있어도 그대로 확정하면 안 된다.
                "samples": int(row.source.get("sample_count") or 0),
                "notes": len(row.source.get("notes") or []),
            },
            material_id=row.material_id,
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
                material_id=hit.material_id if hit else None,
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
