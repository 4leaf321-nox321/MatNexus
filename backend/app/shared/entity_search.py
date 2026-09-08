"""전체 검색 — **한 칸에 치면 무엇이든 찾는다.**

사람은 「SECC180」 이 재료인지 시료인지 시험 이름인지 모른 채 친다. 지금은 화면마다
검색 칸이 따로 있어서, 어디에 있는지 알아야 찾을 수 있다 — 그것을 뒤집는다.

## 대상은 온톨로지 레지스트리가 정한다

`relations.KINDS` 가 종류마다 「어느 표, 어느 열이 이름인가」 를 이미 들고 있다.
여기서 그것을 읽으므로 **종류를 더하면 검색에 저절로 들어온다** — 검색용 목록을
따로 두면 언젠가 한쪽만 늘고, 그때 「왜 이건 안 나오지」 가 생긴다.

## 세 모드 — 사람이 무엇을 원하는지가 다르다

    일치     정확히 그 이름. 번호·코드를 아는 사람이 쓴다
    포함     그 말이 들어간 것. 기본값이다
    비슷     오타·표기 흔들림까지. 「SECC 180」·「secc18O」

세 번째는 `pg_trgm` 이다. 이미 깔려 있고 재료·시료·시편·시험 이름에 GIN 색인이
있다(마이그레이션 `154c0d5508af`: 5만 건에서 118ms → 4.6ms). **앞에 와일드카드가
붙는 검색은 B-tree 를 못 타므로** 이 색인이 없으면 매 타이핑마다 표를 통째로 훑는다.

## 권한은 그래프 것을 그대로 쓴다

`graph.visible_ids` 다. 규칙이 둘이 되면 **「검색에는 뜨는데 열면 404」** 가 생기고,
그것은 사람에게 고장으로 보인다. 안 보이는 것은 검색 결과에서도 없는 것이다.

## 화면이 없는 종류는 자기를 품은 것으로 데려간다

시료·시편·처리결과는 제 화면이 없다 — 재료 상세와 시험 상세 안에 산다. 결과만
주고 갈 곳을 안 주면 「찾았는데 못 연다」 가 되므로, 그 셋은 품은 것(재료·시험)을
함께 준다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement, Select, String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.database import Base
from app.modules.accounts.models import User
from app.modules.materials.models import Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.shared import graph, relations

#: 모드 셋.
MODES = ("exact", "contains", "similar")

#: 「비슷」 에서 이 아래는 안 준다. `pg_trgm` 기본 문턱과 같다 — 더 낮추면
#: 세 글자짜리 질의에 아무 이름이나 걸린다.
SIMILARITY_FLOOR = 0.3

#: 종류마다 몇 개까지. **전부 주지 않는다** — 열세 종류가 각각 쏟아지면 화면이
#: 무엇을 찾았는지 못 보여 준다. 더 보려면 종류를 골라 다시 묻는다.
PER_KIND = 5

#: 한 종류만 물었을 때의 상한.
PER_KIND_FOCUSED = 50

#: 두 글자 이하는 트라이그램이 안 나온다(세 글자씩 쪼개므로). 「포함」 으로 떨어뜨린다.
TRIGRAM_MIN = 3


@dataclass(frozen=True)
class Hit:
    """찾은 것 하나."""

    kind: str
    id: str
    name: str
    score: float
    matched: str
    """왜 걸렸나 — `exact` · `prefix` · `contains` · `similar`."""

    parent_kind: str | None = None
    parent_id: str | None = None
    """제 화면이 없는 종류를 데려갈 곳(재료·시험)."""


@dataclass
class Group:
    """한 종류의 결과 묶음."""

    kind: str
    label: str
    module: str
    hits: list[Hit] = field(default_factory=list)
    truncated: bool = False


def _name_column(kind: relations.EntityKind) -> ColumnElement[str]:
    """보여 줄 이름. 여럿이면 이어 붙인다(장비 정의는 `vendor` + `model`)."""
    table = Base.metadata.tables[kind.table]
    columns = [table.c[one] for one in kind.name_columns]
    if len(columns) == 1:
        return cast(func.coalesce(columns[0], ""), String)
    joined: ColumnElement[str] = cast(func.coalesce(columns[0], ""), String)
    for column in columns[1:]:
        joined = joined + " " + cast(func.coalesce(column, ""), String)
    return joined


def _scored(name: ColumnElement[str], needle: str) -> ColumnElement[float]:
    """왜 걸렸나에 따라 점수. **정확 일치가 언제나 위다.**

    이름이 짧을수록 사람이 뜻한 것일 확률이 높다 — 「SECC」 를 쳤을 때
    「SECC」 가 「SECC180_MDOI_1.0_02」 보다 먼저 서야 한다. 그래서 같은 등급
    안에서는 길이로 가른다.
    """
    lowered = func.lower(name)
    wanted = needle.lower()
    return func.greatest(
        case(
            (lowered == wanted, 1.0),
            (lowered.like(f"{wanted}%"), 0.8),
            (lowered.like(f"%{wanted}%"), 0.6),
            else_=0.0,
        ),
        # 트라이그램 유사도는 0~1 이다. 반으로 눌러 **포함보다 아래**에 둔다 —
        # 「비슷한 것」이 「그 말이 든 것」보다 위에 서면 안 된다.
        func.similarity(name, needle) * 0.5,
    )


def _matched(name: str, needle: str) -> str:
    lowered, wanted = name.lower(), needle.lower()
    if lowered == wanted:
        return "exact"
    if lowered.startswith(wanted):
        return "prefix"
    if wanted in lowered:
        return "contains"
    return "similar"


def _condition(name: ColumnElement[str], needle: str, mode: str) -> ColumnElement[bool] | None:
    """모드가 무엇을 통과시키나."""
    if mode == "exact":
        return func.lower(name) == needle.lower()
    contains = name.ilike(f"%{needle}%")
    if mode == "contains":
        return contains
    if len(needle) < TRIGRAM_MIN:
        # 두 글자 이하는 트라이그램이 안 나온다 — 「포함」 과 같아진다.
        return contains
    return or_(contains, func.similarity(name, needle) >= SIMILARITY_FLOOR)


#: 제 화면이 없는 종류 → 품은 것을 찾는 짝(부모 종류, 부모 열).
#:
#: **레지스트리에서 자동으로 끌어내지 않는다.** 관계는 여럿이고(시편은 시료에도
#: 시험에도 걸린다) 「사람을 어디로 데려갈까」 는 그중 하나를 고르는 판단이라,
#: 그 판단을 여기 적어 둔다.
_PARENTS: dict[str, str] = {
    "sample": "material",
    "specimen": "material",
    "processing_result": "test_run",
}


def _parents(db: Session, kind: str, ids: list[Any]) -> dict[str, tuple[str, str]]:
    """자식 식별자 → (부모 종류, 부모 식별자)."""
    if kind not in _PARENTS or not ids:
        return {}
    parent_kind = _PARENTS[kind]
    if kind == "sample":
        rows = db.execute(
            select(Sample.id, Sample.material_id).where(Sample.id.in_(ids))
        ).all()
    elif kind == "specimen":
        # 시편은 시료를 한 번 더 거쳐야 재료에 닿는다.
        rows = db.execute(
            select(Specimen.id, Sample.material_id)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Specimen.id.in_(ids))
        ).all()
    else:
        rows = db.execute(
            select(ProcessingResult.id, ProcessingResult.test_run_id).where(
                ProcessingResult.id.in_(ids)
            )
        ).all()
    return {str(child): (parent_kind, str(parent)) for child, parent in rows if parent}


def search_kind(
    db: Session,
    user: User,
    *,
    kind_slug: str,
    needle: str,
    mode: str = "contains",
    limit: int = PER_KIND,
) -> tuple[list[Hit], bool]:
    """한 종류에서 찾는다 → (결과, 잘렸나)."""
    kind = relations.KINDS.get(kind_slug)
    if kind is None or not needle.strip():
        return [], False

    table = Base.metadata.tables[kind.table]
    name = _name_column(kind)
    where = _condition(name, needle, mode)
    if where is None:
        return [], False

    query: Select[Any] = select(
        table.c[kind.id_column], name.label("name"), _scored(name, needle).label("score")
    ).where(where)
    if kind.soft_delete:
        query = query.where(table.c["deleted_at"].is_(None))
    guard = graph.visible_ids(db, user, kind)
    if guard is not None:
        query = query.where(table.c[kind.id_column].in_(guard))

    # **하나 더 받아 「잘렸다」 를 안다.** 조용히 자르면 사람은 그것이 전부인 줄 안다.
    rows = db.execute(
        query.order_by(_scored(name, needle).desc(), func.length(name)).limit(limit + 1)
    ).all()

    found = [
        Hit(
            kind=kind.slug,
            id=str(row[0]),
            name=row[1] or "",
            score=float(row[2] or 0.0),
            matched=_matched(row[1] or "", needle),
        )
        for row in rows[:limit]
    ]
    owners = _parents(db, kind.slug, [_coerce(one.id) for one in found])
    if owners:
        found = [
            Hit(
                kind=one.kind,
                id=one.id,
                name=one.name,
                score=one.score,
                matched=one.matched,
                parent_kind=owners.get(one.id, (None, None))[0],
                parent_id=owners.get(one.id, (None, None))[1],
            )
            for one in found
        ]
    return found, len(rows) > limit


def _coerce(value: str) -> Any:
    try:
        return uuid.UUID(value)
    except ValueError:
        return value


def search(
    db: Session,
    user: User,
    *,
    needle: str,
    mode: str = "contains",
    only: list[str] | None = None,
) -> list[Group]:
    """온톨로지 종류 전부에서 찾는다. **빈 묶음은 안 싣는다.**"""
    wanted = [one for one in (only or list(relations.KINDS)) if one in relations.KINDS]
    limit = PER_KIND_FOCUSED if len(wanted) == 1 else PER_KIND

    made: list[Group] = []
    for slug in wanted:
        kind = relations.KINDS[slug]
        hits, truncated = search_kind(
            db, user, kind_slug=slug, needle=needle, mode=mode, limit=limit
        )
        if hits:
            made.append(
                Group(
                    kind=slug,
                    label=kind.label,
                    module=kind.module,
                    hits=hits,
                    truncated=truncated,
                )
            )
    # 가장 잘 맞은 것이 있는 묶음이 위로. 종류 차례를 고정하면 재료가 늘 위에
    # 서고, 장비를 찾는 사람은 매번 아래로 훑어야 한다.
    made.sort(key=lambda one: -max(hit.score for hit in one.hits))
    return made
