"""트래버설 — **레지스트리만 보고 길을 찾는다.**

4단계다. 3단계(`relations`)가 「무엇이 무엇과 어떤 사이인가」를 적었고, 여기는 그
적힌 것을 따라 실제로 걷는다.

    「이 물성을 재는 장비가 어디에 있나」
        property ─measured_by→ instrument ←unit_of─ equipment_unit ─held_by→ workspace

    「이 값이 어느 재료에서 나왔나」
        test_run ─tested→ specimen ─part_of→ sample ─derived_from→ material

**부르는 쪽은 `fk` 인지 연결 표인지 모른다.** 그것이 이 모듈을 두는 이유다 —
관계가 실린 자리가 바뀌어도(5단계에서 `entity_edges` 가 생겨도) 부르는 코드는
그대로다.

## 권한은 여기서 건다 — `property_search` 와 반대다

값 검색은 부르는 쪽이 「문헌·사내」 둘을 이름으로 지정하므로 권한도 거기서 줬다.
트래버설은 다르다 — **부르는 쪽은 걷다가 어느 표에 닿을지 모른다.** 「이 장비로
잰 시험」 을 물었을 뿐인데 남의 부서 재료 이름이 딸려 나온다. 그래서 `user` 를
선택 인자가 아니라 **필수**로 받고, 종류마다 가시 범위를 걸어 걷는다.

안 보이는 마디에서는 **길이 끊긴다.** 이름만 가리고 계속 걸으면 「A 는 B 와
이어져 있다」 는 사실 자체가 새기 때문이다.

## 재귀 CTE 를 안 쓴다

한 홉마다 **다른 표**로 건너간다(재료→시료→시편→시험). CTE 하나로는 못 적는
모양이라, 홉마다 종류별로 묶어 질의한다 — 깊이 3이면 질의 열 몇 개다. 대신
`MAX_NODES` 로 상한을 강제한다(AGENTS.md: 목록 엔드포인트에는 서버가 상한을).
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import Base
from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun
from app.shared import permissions, relations

#: 한 마디에서 한 번에 보여 줄 이웃 수.
NEIGHBOR_LIMIT = 50

#: 한 번의 걷기에서 모을 수 있는 마디 총량. **넘으면 거기서 멈춘다** — 조용히
#: 자르지 않고 `truncated` 로 말한다.
MAX_NODES = 300

#: 기본 깊이. 「이 물성 → 장비 → 보유 개체 → 조직」 이 3이다.
DEFAULT_DEPTH = 2

#: 길 찾기 최대 깊이. 재료에서 시험까지가 3, 문헌까지가 4다.
MAX_PATH_DEPTH = 6


@dataclass(frozen=True)
class Node:
    """마디 하나. **종류와 식별자가 함께여야 뜻이 있다** — 다형 참조다."""

    kind: str
    id: str
    name: str

    @property
    def ref(self) -> tuple[str, str]:
        return (self.kind, self.id)


@dataclass(frozen=True)
class Edge:
    """가장자리 하나. 방향은 **레지스트리에 적힌 그대로**(src → dst)."""

    relation: str
    label: str
    src: tuple[str, str]
    dst: tuple[str, str]


@dataclass
class Subgraph:
    nodes: dict[tuple[str, str], Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    truncated: bool = False

    def describe(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"kind": one.kind, "id": one.id, "name": one.name}
                for one in self.nodes.values()
            ],
            "edges": [
                {
                    "relation": one.relation,
                    "label": one.label,
                    "src": {"kind": one.src[0], "id": one.src[1]},
                    "dst": {"kind": one.dst[0], "id": one.dst[1]},
                }
                for one in self.edges
            ],
            "truncated": self.truncated,
        }


def _table(kind: relations.EntityKind) -> Any:
    return Base.metadata.tables[kind.table]


def _coerce(kind: relations.EntityKind, value: Any) -> Any:
    """식별자를 그 열의 타입으로. **`property` 만 문자열이다**(`key`)."""
    if isinstance(value, uuid.UUID) or kind.id_column != "id":
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return value
    return value


def visible_ids(db: Session, user: User, kind: relations.EntityKind) -> Select[Any] | None:
    """이 종류에서 볼 수 있는 식별자들. `None` 이면 가릴 것이 없다.

    **전체 검색도 이것을 쓴다**(`entity_search`). 규칙이 둘이 되면 「검색에는 뜨는데
    열면 404」 가 생기고, 그때 어느 쪽이 맞는지 알 방법이 없다.

    **재료를 따라간다** — 시료·시편·시험·처리결과·물성카드는 모두 재료의 가시
    범위를 물려받는다(`permissions.visible_runs` 와 같은 판단: 규칙이 둘이 되면
    「재료는 보이는데 그 시험은 안 보인다」 가 생긴다).

    문헌·기준정보·장비·조직은 가리지 않는다 — 사내 공용 기준정보다.
    """
    if user.is_system_admin:
        return None
    materials = permissions.visible_material_ids(db, user)
    # **가시 규칙을 베끼지 않는다** — 시험의 범위는 `permissions` 것을 그대로 쓰고
    # 열만 좁힌다. 베끼면 「재료는 보이는데 그 시험은 안 보인다」 가 언젠가 생긴다.
    runs = permissions.visible_runs(db, user).with_only_columns(TestRun.id)
    if kind.slug == "material":
        return materials
    if kind.slug == "sample":
        return select(Sample.id).where(
            Sample.deleted_at.is_(None), Sample.material_id.in_(materials)
        )
    if kind.slug == "specimen":
        return select(Specimen.id).where(
            Specimen.deleted_at.is_(None),
            Specimen.sample_id.in_(select(Sample.id).where(Sample.material_id.in_(materials))),
        )
    if kind.slug == "test_run":
        return runs
    if kind.slug == "processing_result":
        return select(ProcessingResult.id).where(ProcessingResult.test_run_id.in_(runs))
    if kind.slug == "property_card":
        return select(PropertyCard.id).where(PropertyCard.material_id.in_(materials))
    return None


def fetch(db: Session, user: User, kind_slug: str, ids: list[Any]) -> dict[str, Node]:
    """식별자들 → 마디들. **안 보이는 것은 아예 안 돌아온다.**"""
    kind = relations.KINDS.get(kind_slug)
    if kind is None or not ids:
        return {}
    table = _table(kind)
    wanted = [_coerce(kind, one) for one in ids]

    name = table.c[kind.name_columns[0]]
    for column in kind.name_columns[1:]:
        name = name + " " + table.c[column]

    query = select(table.c[kind.id_column], name).where(table.c[kind.id_column].in_(wanted))
    if kind.soft_delete:
        query = query.where(table.c["deleted_at"].is_(None))
    guard = visible_ids(db, user, kind)
    if guard is not None:
        query = query.where(table.c[kind.id_column].in_(guard))

    return {
        str(row[0]): Node(kind=kind.slug, id=str(row[0]), name=row[1] or "")
        for row in db.execute(query).all()
    }


def _relations_for(kind_slug: str, wanted: list[str] | None) -> list[relations.RelationType]:
    chosen = relations.relations_of(kind_slug)
    if wanted is not None:
        chosen = [one for one in chosen if one.slug in wanted]
    # 5단계 전까지 `edge` 관계는 실린 자리가 없다 — 걸으면 빈손이다.
    return [one for one in chosen if one.source.kind != "edge"]


def _hop(
    db: Session,
    relation: relations.RelationType,
    *,
    from_kind: str,
    ids: list[Any],
) -> list[tuple[Any, Any]]:
    """한 관계를 한 홉 건넌다 → `[(출발 식별자, 도착 식별자)]`.

    `from_kind` 가 `src` 면 정방향, `dst` 면 역방향이다. **부르는 쪽은 이 안이
    FK 인지 연결 표인지 모른다.**
    """
    source = relation.source
    table = Base.metadata.tables[source.table]
    forward = from_kind == relation.src

    if source.kind == "fk":
        src_kind = relations.KINDS[relation.src]
        dst_kind = relations.KINDS[relation.dst]
        own = table.c[src_kind.id_column]
        points = table.c[source.src_column]
        wanted = [_coerce(src_kind if forward else dst_kind, one) for one in ids]
        query = select(own, points).where(points.is_not(None))
        query = query.where(own.in_(wanted) if forward else points.in_(wanted))
        if "deleted_at" in table.c:
            query = query.where(table.c["deleted_at"].is_(None))
        rows = db.execute(query.limit(MAX_NODES * 4)).all()
        return [(row[0], row[1]) if forward else (row[1], row[0]) for row in rows]

    src_column = table.c[source.src_column]
    dst_column = table.c[source.dst_column]
    near, far = (src_column, dst_column) if forward else (dst_column, src_column)
    kind = relations.KINDS[relation.src if forward else relation.dst]
    query = select(near, far).where(near.in_([_coerce(kind, one) for one in ids]))
    return [(row[0], row[1]) for row in db.execute(query.limit(MAX_NODES * 4)).all()]


def neighbors(
    db: Session,
    user: User,
    *,
    kind: str,
    ident: Any,
    only: list[str] | None = None,
    direction: str = "both",
    limit: int = NEIGHBOR_LIMIT,
) -> list[tuple[Edge, Node]]:
    """마디 하나의 이웃. **관계 이름과 함께 준다** — 「왜 이어져 있나」 가 답의 절반이다."""
    if kind not in relations.KINDS:
        return []
    if not fetch(db, user, kind, [ident]):
        return []  # 못 보는 마디에서는 걷지 않는다

    found: list[tuple[Edge, Node]] = []
    for relation in _relations_for(kind, only):
        forward = kind == relation.src
        if direction == "out" and not forward:
            continue
        if direction == "in" and forward:
            continue
        other_kind = relation.dst if forward else relation.src
        pairs = _hop(db, relation, from_kind=kind, ids=[ident])
        others = [pair[1] for pair in pairs]
        nodes = fetch(db, user, other_kind, others)
        for _, other in pairs:
            node = nodes.get(str(other))
            if node is None:
                continue
            ref = (kind, str(ident))
            edge = Edge(
                relation=relation.slug,
                label=relation.label if forward else relation.inverse_label,
                src=ref if forward else node.ref,
                dst=node.ref if forward else ref,
            )
            found.append((edge, node))
            if len(found) >= limit:
                return found
    return found


def traverse(
    db: Session,
    user: User,
    *,
    seeds: list[tuple[str, Any]],
    only: list[str] | None = None,
    direction: str = "both",
    max_depth: int = DEFAULT_DEPTH,
) -> Subgraph:
    """씨앗에서 시작해 `max_depth` 홉까지. **본 마디는 다시 안 넓힌다.**"""
    graph = Subgraph()
    frontier: list[tuple[str, str]] = []
    for kind, ident in seeds:
        for seed in fetch(db, user, kind, [ident]).values():
            graph.nodes[seed.ref] = seed
            frontier.append(seed.ref)

    seen = set(frontier)
    for _ in range(max(0, max_depth)):
        if not frontier or graph.truncated:
            break
        # 같은 종류끼리 묶어 한 번에 묻는다 — 마디마다 물으면 홉마다 300번이다.
        by_kind: dict[str, list[str]] = {}
        for kind, ident in frontier:
            by_kind.setdefault(kind, []).append(ident)

        next_frontier: list[tuple[str, str]] = []
        for kind, ids in by_kind.items():
            for relation in _relations_for(kind, only):
                forward = kind == relation.src
                if direction == "out" and not forward:
                    continue
                if direction == "in" and forward:
                    continue
                other_kind = relation.dst if forward else relation.src
                pairs = _hop(db, relation, from_kind=kind, ids=list(ids))
                nodes = fetch(db, user, other_kind, [pair[1] for pair in pairs])
                for here, there in pairs:
                    node = nodes.get(str(there))
                    if node is None:
                        continue
                    ref = (kind, str(here))
                    graph.edges.append(
                        Edge(
                            relation=relation.slug,
                            label=relation.label if forward else relation.inverse_label,
                            src=ref if forward else node.ref,
                            dst=node.ref if forward else ref,
                        )
                    )
                    if node.ref in seen:
                        continue
                    if len(graph.nodes) >= MAX_NODES:
                        graph.truncated = True
                        break
                    graph.nodes[node.ref] = node
                    seen.add(node.ref)
                    next_frontier.append(node.ref)
        frontier = next_frontier
    return graph


def path_between(
    db: Session,
    user: User,
    *,
    start: tuple[str, Any],
    goal: tuple[str, Any],
    only: list[str] | None = None,
    max_depth: int = 4,
) -> list[Edge] | None:
    """두 마디 사이의 **가장 짧은 길** — 없으면 `None`.

    「이 값이 어느 장비로 나왔나」 처럼 사람이 사슬을 모를 때 쓴다. 너비 우선이라
    처음 닿은 길이 가장 짧다.
    """
    depth = min(max(1, max_depth), MAX_PATH_DEPTH)
    start_nodes = fetch(db, user, start[0], [start[1]])
    goal_nodes = fetch(db, user, goal[0], [goal[1]])
    if not start_nodes or not goal_nodes:
        return None

    here = (start[0], str(start[1]))
    there = (goal[0], str(goal[1]))
    if here == there:
        return []

    came: dict[tuple[str, str], tuple[tuple[str, str], Edge]] = {}
    queue: deque[tuple[tuple[str, str], int]] = deque([(here, 0)])
    seen = {here}

    while queue:
        ref, level = queue.popleft()
        if level >= depth:
            continue
        for edge, node in neighbors(
            db, user, kind=ref[0], ident=ref[1], only=only, limit=NEIGHBOR_LIMIT
        ):
            if node.ref in seen:
                continue
            seen.add(node.ref)
            came[node.ref] = (ref, edge)
            if node.ref == there:
                walked: list[Edge] = []
                cursor = node.ref
                while cursor != here:
                    previous, taken = came[cursor]
                    walked.append(taken)
                    cursor = previous
                return list(reversed(walked))
            queue.append((node.ref, level + 1))
            if len(seen) > MAX_NODES:
                return None
    return None


def counts(db: Session, user: User, *, kind: str, ident: Any) -> dict[str, int]:
    """관계별 이웃 수. **0인 관계는 안 싣는다** — AI 가 빈 길로 들어가지 않게."""
    found: dict[str, int] = {}
    for relation in _relations_for(kind, None):
        forward = kind == relation.src
        pairs = _hop(db, relation, from_kind=kind, ids=[ident])
        other_kind = relation.dst if forward else relation.src
        visible = fetch(db, user, other_kind, [pair[1] for pair in pairs])
        if visible:
            found[relation.slug] = len(visible)
    return found
