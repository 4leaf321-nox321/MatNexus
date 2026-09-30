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

## 번호로 친 것은 번호로 찾는다(ADR 0043)

재료 `M-` · 시료 `S-` · 시편 `P-` · 시험 `T-` 번호 꼴(`T-203` · `t203`)이면 그 종류에서
**번호가 정확히 같은 것**을 맨 위에 둔다 — 번호를 아는 사람은 그것 하나를 원한다. 결과마다
번호를 함께 싣는다(말로 전할 때 이름보다 짧다).

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
from app.shared import codes, graph, relations, semantic

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

#: RRF 상수. 순위 하나가 점수를 독점하지 않게 누르는 값으로, 60 이 통용된다.
RRF_K = 60


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

    via: str | None = None
    """**이름이 아닌 칸으로 걸렸으면** 그 칸과 값 — 「별칭 도어 이너 강판」(2026-09-29).
    이름에 없는 말로 떴는데 이유가 없으면 엉뚱한 결과로 읽힌다."""

    code: str | None = None
    """고유 번호 — 재료 · 시료 · 시편 · 시험만 있다(ADR 0043)."""


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
    # **이름 곁의 칸도 본다**(`EntityKind.also_columns`) — 별칭·로트·규격·원본 파일명.
    # 이름에 걸린 것이 곁의 칸에만 걸린 것보다 위다(곁의 칸 점수는 0.9 배).
    also = [
        (label, cast(func.coalesce(table.c[column], ""), String))
        for column, label in kind.also_columns
    ]
    by_also = [
        condition
        for _, column in also
        if (condition := _condition(column, needle, mode)) is not None
    ]
    # **번호 꼴이면 번호로**(ADR 0043) — 정확 일치라 유니크 색인을 탄다. 이름보다 위다.
    numbered = kind.slug in codes.PREFIXES
    wanted = codes.of_kind(needle, kind.slug) if numbered else None
    by_code = table.c["code"] == wanted if wanted is not None else None
    score: ColumnElement[float] = func.greatest(
        _scored(name, needle),
        *(_scored(column, needle) * 0.9 for _, column in also),
        *([case((by_code, 1.0), else_=0.0)] if by_code is not None else []),
    )

    query: Select[Any] = select(
        table.c[kind.id_column],
        name.label("name"),
        score.label("score"),
        where.label("by_name"),
        *(column.label(f"also_{at}") for at, (_, column) in enumerate(also)),
        *([table.c["code"].label("code")] if numbered else []),
        *([by_code.label("by_code")] if by_code is not None else []),
    ).where(or_(where, *by_also, *([by_code] if by_code is not None else [])))
    if kind.soft_delete:
        query = query.where(table.c["deleted_at"].is_(None))
    guard = graph.visible_ids(db, user, kind)
    if guard is not None:
        query = query.where(table.c[kind.id_column].in_(guard))

    # **하나 더 받아 「잘렸다」 를 안다.** 조용히 자르면 사람은 그것이 전부인 줄 안다.
    rows = db.execute(query.order_by(score.desc(), func.length(name)).limit(limit + 1)).all()

    found = [
        _hit(kind.slug, row, needle, [label for label, _ in also]) for row in rows[:limit]
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
                via=one.via,
                code=one.code,
            )
            for one in found
        ]
    return found, len(rows) > limit


def _hit(slug: str, row: Any, needle: str, also: list[str]) -> Hit:
    """한 줄 → 결과. 이름으로 안 걸렸으면 **어느 칸으로 걸렸는지**(`via`)를 단다."""
    name = row[1] or ""
    fields = row._mapping
    code = fields.get("code")
    if fields.get("by_code"):
        return Hit(
            kind=slug,
            id=str(row[0]),
            name=name,
            score=float(row[2] or 0.0),
            matched="exact",
            via=f"번호 {code}",
            code=code,
        )
    if row[3] or not also:
        return Hit(
            kind=slug,
            id=str(row[0]),
            name=name,
            score=float(row[2] or 0.0),
            matched=_matched(name, needle),
            code=code,
        )
    # 곁의 칸 가운데 **값이 가장 잘 맞는 것**을 이유로 단다 — 일치 · 앞 · 포함 · 비슷
    # 순서로 가장 가까운 것.
    order = {"exact": 0, "prefix": 1, "contains": 2, "similar": 3}
    candidates = [
        (label, str(row[4 + at] or "")) for at, label in enumerate(also) if row[4 + at]
    ]
    if not candidates:
        return Hit(
            kind=slug,
            id=str(row[0]),
            name=name,
            score=float(row[2] or 0.0),
            matched=_matched(name, needle),
            code=code,
        )
    label, value = min(candidates, key=lambda one: order[_matched(one[1], needle)])
    return Hit(
        kind=slug,
        id=str(row[0]),
        name=name,
        score=float(row[2] or 0.0),
        matched=_matched(value, needle),
        via=f"{label} {value}",
        code=code,
    )


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
    if mode == "similar":
        made = _fuse_meaning(db, user, needle, made, wanted)

    made.sort(key=lambda one: -max(hit.score for hit in one.hits))
    return made


def _fuse_meaning(
    db: Session,
    user: User,
    needle: str,
    groups: list[Group],
    wanted: list[str],
) -> list[Group]:
    """**뜻이 가까운 것**을 「비슷」 에 얹는다(3단계).

    새 모드를 만들지 않는다 — 사람에게 「비슷」 은 이미 하나의 뜻이고, 모드가 넷이
    되면 무엇을 고를지가 새 문제가 된다.

    ## RRF 로 합친다

    두 순위(글자·뜻)는 점수의 단위가 다르다. 트라이그램 0.42 와 코사인 0.71 을
    직접 견주면 어느 쪽이 나은지 말할 근거가 없다. **순위만 본다** —
    `1/(60+등수)` 를 더하면 한쪽에만 걸린 것도 위로 올라온다.

    ## 못 쓰면 조용히 넘어간다

    엔진이 죽었다고 검색 화면이 오류를 띄우면 사람은 **검색이 고장 났다**고 읽는다.
    """
    matches = semantic.search(db, needle)
    if not matches:
        return groups

    by_kind: dict[str, Group] = {one.kind: one for one in groups}
    for rank, match in enumerate(matches):
        if match.kind not in relations.KINDS or match.kind not in wanted:
            continue
        kind = relations.KINDS[match.kind]
        # **권한을 다시 건다.** 조각 표에는 부서가 없다 — 여기서 안 걸면 색인이
        # 곧 유출 통로가 된다.
        if not graph.fetch(db, user, match.kind, [match.entity_id]):
            continue

        group = by_kind.get(match.kind)
        if group is None:
            group = Group(kind=kind.slug, label=kind.label, module=kind.module)
            by_kind[match.kind] = group
            groups.append(group)

        bonus = 1.0 / (RRF_K + rank)
        for at, hit in enumerate(group.hits):
            if hit.id == match.entity_id:
                # 양쪽에 걸린 것 — 두 순위를 더해 위로 올린다.
                group.hits[at] = Hit(
                    kind=hit.kind,
                    id=hit.id,
                    name=hit.name,
                    score=hit.score + bonus,
                    matched="both",
                    parent_kind=hit.parent_kind,
                    parent_id=hit.parent_id,
                    via=hit.via,
                    code=hit.code,
                )
                break
        else:
            group.hits.append(
                Hit(
                    kind=match.kind,
                    id=match.entity_id,
                    name=match.title or match.snippet[:60],
                    # 글자로는 안 걸린 것이다. 트라이그램 상위와 나란히 서되
                    # 위로 서지는 않게 둔다 — 왜 떴는지 사람이 못 읽기 때문이다.
                    score=0.35 + bonus,
                    matched="meaning",
                )
            )
    for group in groups:
        group.hits.sort(key=lambda one: -one.score)
        del group.hits[PER_KIND_FOCUSED:]
        _fill_codes(db, group)
    return groups


def _fill_codes(db: Session, group: Group) -> None:
    """뜻으로만 걸린 것에도 번호를 단다 — 글자로 찾은 것만 번호가 있으면 들쭉날쭉하다."""
    if group.kind not in codes.PREFIXES:
        return
    missing = [_coerce(hit.id) for hit in group.hits if hit.code is None]
    if not missing:
        return
    table = Base.metadata.tables[relations.KINDS[group.kind].table]
    found = {
        str(row[0]): row[1]
        for row in db.execute(
            select(table.c["id"], table.c["code"]).where(table.c["id"].in_(missing))
        )
    }
    group.hits[:] = [
        hit
        if hit.code is not None
        else Hit(
            kind=hit.kind,
            id=hit.id,
            name=hit.name,
            score=hit.score,
            matched=hit.matched,
            parent_kind=hit.parent_kind,
            parent_id=hit.parent_id,
            via=hit.via,
            code=found.get(hit.id),
        )
        for hit in group.hits
    ]
