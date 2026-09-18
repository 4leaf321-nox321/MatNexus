"""그래프 엔진 — 정의(`shared/relations` + `model.py`)를 읽어 **이웃 · 유도 선 · 차수 · 이름 ·
찾기 · 훑기**를 낸다. TestScope 의 엔진과 같은 계약이다.

큰 데이터를 통째로 안 준다(StandardPlatform 과 같은 규칙): 이웃은 한 단계씩, 노드마다 fanout
개까지, 전체 node_limit 개까지. 잘리면 잘렸다고 말한다 — 노드의 `degree`(보이는 관계 수)가
화면에 실린 수보다 크면 화면이 「+N」 을 붙인다.

노드 id 는 `"<종류>:<식별자>"`. 선 하나는 (관계 slug, src id, dst id) — **같은 두 마디를 잇는
값 행이 수십 개여도 선은 하나다**(`catalog_values` 는 (재료, 출처) 한 쌍에 행이 수십 개).

## 보이는 것만

재료를 따라가는 가시 범위(`shared/graph.visible_ids`)를 선의 양 끝과 차수에 똑같이 건다 —
검색·MCP 와 같은 한 규칙이다. 지운 것(deleted_at)은 이름 찾기에서 빠지고, 이름 없는 끝을
가진 선은 버린다 — 지운 재료로 가는 선이 그림에 남지 않게.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, Table, and_, func, or_, select
from sqlalchemy.orm import Session

from app.database import Base
from app.modules.accounts.models import User
from app.modules.graph.model import (
    EDGE_KINDS,
    NODE_META,
    NODE_META_BY_SLUG,
    NodeMeta,
    node_id,
)
from app.modules.vocabulary.models import Vocabulary
from app.modules.workspaces.models import Workspace
from app.shared import entity_search, graph, relations


@dataclass(frozen=True)
class Edge:
    id: str
    """`<관계 slug>:<src 식별자>:<dst 식별자>` — 같은 쌍이 두 응답에 실려도 하나."""

    kind: str
    src: str
    dst: str


@dataclass
class NodeInfo:
    id: str
    type_slug: str
    label: str
    key: str | None
    status: str
    sublabel: str | None = None
    workspace_slug: str | None = None


# ------------------------------------------------------------------ 표·식별자


def _table(slug: str) -> Table:
    return Base.metadata.tables[relations.KINDS[slug].table]


def _coerce(slug: str, value: Any) -> Any:
    """식별자를 그 열의 타입으로. **`property` 만 문자열이다**(`key`)."""
    kind = relations.KINDS[slug]
    if isinstance(value, uuid.UUID) or kind.id_column != "id":
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return value


def _coerce_all(slug: str, ids: set[str] | list[str]) -> list[Any]:
    out = []
    for one in ids:
        coerced = _coerce(slug, one)
        # uuid 종류에 uuid 가 아닌 것이 섞이면 그 값은 어차피 없는 것이다 — 조용히 뺀다.
        if relations.KINDS[slug].id_column == "id" and not isinstance(coerced, uuid.UUID):
            continue
        out.append(coerced)
    return out


def _guard(db: Session, user: User, slug: str) -> Select[Any] | None:
    return graph.visible_ids(db, user, relations.KINDS[slug])


def _name_expr(table: Table, kind: relations.EntityKind) -> Any:
    name: Any = table.c[kind.name_columns[0]]
    for column in kind.name_columns[1:]:
        name = name + " " + table.c[column]
    return name


def _status_text(value: Any) -> str:
    if value is None:
        return "active"
    if isinstance(value, bool):
        return "active" if value else "inactive"
    return str(value)


# ------------------------------------------------------------------ 이름


def lookup(db: Session, user: User, wanted: dict[str, set[str]]) -> dict[str, NodeInfo]:
    """종류별 식별자 집합 → 노드 정보. 지운 것·안 보이는 것은 **빠진다**(없는 것과 같은 답)."""
    out: dict[str, NodeInfo] = {}
    workspaces = {w.id: w for w in db.scalars(select(Workspace))}
    axis_labels = {v.id: v.label for v in db.scalars(select(Vocabulary))}
    for type_slug, ids in wanted.items():
        meta = NODE_META_BY_SLUG.get(type_slug)
        if meta is None or not ids:
            continue
        kind = meta.kind
        table = _table(type_slug)
        id_col = table.c[kind.id_column]
        columns: list[Any] = [id_col, _name_expr(table, kind)]
        columns.append(table.c[meta.key_column] if meta.key_column else id_col)
        for name in meta.sublabel_columns:
            columns.append(table.c[name])
        columns.append(table.c[meta.status_column] if meta.status_column else id_col)
        columns.append(table.c[meta.workspace_column] if meta.workspace_column else id_col)
        if type_slug == "term":
            columns.append(table.c["vocabulary_id"])
        query = select(*columns).where(id_col.in_(_coerce_all(type_slug, ids)))
        if kind.soft_delete:
            query = query.where(table.c["deleted_at"].is_(None))
        guard = _guard(db, user, type_slug)
        if guard is not None:
            query = query.where(id_col.in_(guard))
        for row in db.execute(query).all():
            values = list(row)
            ident = values[0]
            label = values[1] or ""
            key = str(values[2]) if meta.key_column and values[2] is not None else None
            at = 3
            parts = [str(one) for one in values[at : at + len(meta.sublabel_columns)] if one]
            at += len(meta.sublabel_columns)
            status = _status_text(values[at]) if meta.status_column else "active"
            at += 1
            workspace = None
            if meta.workspace_column and values[at] is not None:
                found = workspaces.get(values[at])
                workspace = found.slug if found else None
            at += 1
            if type_slug == "term":
                axis = axis_labels.get(values[at])
                if axis:
                    parts.insert(0, axis)
            out[node_id(type_slug, ident)] = NodeInfo(
                node_id(type_slug, ident),
                type_slug,
                str(label),
                key,
                status,
                " · ".join(parts) or None,
                workspace,
            )
    return out


# ------------------------------------------------------------------ 선


def _pairs_query(
    db: Session,
    user: User,
    relation: relations.RelationType,
    *,
    src_ids: set[str] | None,
    dst_ids: set[str] | None,
    any_side: bool,
) -> Select[Any]:
    """(src 식별자, dst 식별자) 두 열을 내는 select. FK 든 연결 표든 부르는 쪽은 모른다.

    `any_side` 면 한쪽만 걸려도(이웃), 아니면 양쪽 다(유도 선). 양 끝에 가시 범위를 건다.
    """
    source = relation.source
    table = Base.metadata.tables[source.table]
    if source.kind == "fk":
        near = table.c[relations.KINDS[relation.src].id_column]
        far = table.c[source.src_column]
    else:
        near = table.c[source.src_column]
        far = table.c[source.dst_column]
    query = select(near.label("src"), far.label("dst")).where(far.is_not(None))
    if source.kind != "fk":
        query = query.distinct()
    if "deleted_at" in table.c:
        query = query.where(table.c["deleted_at"].is_(None))
    conditions = []
    if src_ids:
        conditions.append(near.in_(_coerce_all(relation.src, src_ids)))
    if dst_ids:
        conditions.append(far.in_(_coerce_all(relation.dst, dst_ids)))
    if conditions:
        query = query.where(or_(*conditions) if any_side else and_(*conditions))
    for slug, column in ((relation.src, near), (relation.dst, far)):
        guard = _guard(db, user, slug)
        if guard is not None:
            query = query.where(column.in_(guard))
    return query


def _edges(relation: relations.RelationType, rows: Sequence[Any]) -> list[Edge]:
    seen: set[str] = set()
    out: list[Edge] = []
    for src, dst in rows:
        edge_id = f"{relation.slug}:{src}:{dst}"
        if edge_id in seen:
            continue
        seen.add(edge_id)
        out.append(
            Edge(
                edge_id, relation.slug, node_id(relation.src, src), node_id(relation.dst, dst)
            )
        )
    return out


def _ids_of(frontier: dict[str, set[str]]) -> set[str]:
    return {node_id(t, i) for t, ids in frontier.items() for i in ids}


def neighbor_edges(
    db: Session,
    user: User,
    frontier: dict[str, set[str]],
    *,
    fanout: int,
    relations_wanted: set[str] | None,
    types: set[str] | None,
) -> list[Edge]:
    """frontier(종류별 식별자)에 닿는 선. 노드 하나가 데려오는 이웃은 fanout 개까지."""
    out: list[Edge] = []
    present = _ids_of(frontier)
    per_node: dict[str, int] = defaultdict(int)
    for relation in EDGE_KINDS:
        if relations_wanted and relation.slug not in relations_wanted:
            continue
        src_ids = frontier.get(relation.src, set())
        dst_ids = frontier.get(relation.dst, set())
        if not src_ids and not dst_ids:
            continue
        # 반대쪽 종류를 걸렀으면 — 이웃 종류가 아니면 묻지도 않는다.
        if types:
            if src_ids and relation.dst not in types and not dst_ids:
                continue
            if dst_ids and relation.src not in types and not src_ids:
                continue
        query = _pairs_query(
            db, user, relation, src_ids=src_ids, dst_ids=dst_ids, any_side=True
        ).limit(fanout * max(len(src_ids | dst_ids), 1) * 2)
        for edge in _edges(relation, db.execute(query).all()):
            anchor, other = (
                (edge.src, edge.dst) if edge.src in present else (edge.dst, edge.src)
            )
            if types and other not in present and other.split(":", 1)[0] not in types:
                continue
            if per_node[anchor] >= fanout:
                continue
            per_node[anchor] += 1
            out.append(edge)
    return out


def induced_edges(
    db: Session,
    user: User,
    ids: dict[str, set[str]],
    *,
    relations_wanted: set[str] | None,
    limit: int,
) -> list[Edge]:
    """양 끝이 모두 `ids` 안에 있는 선 — fanout 에 밀린 관계도 양 끝이 화면에 있으면 긋는다."""
    out: list[Edge] = []
    present = _ids_of(ids)
    for relation in EDGE_KINDS:
        if relations_wanted and relation.slug not in relations_wanted:
            continue
        src_ids = ids.get(relation.src, set())
        dst_ids = ids.get(relation.dst, set())
        if not src_ids or not dst_ids:
            continue
        query = _pairs_query(
            db, user, relation, src_ids=src_ids, dst_ids=dst_ids, any_side=False
        ).limit(limit)
        out.extend(
            e
            for e in _edges(relation, db.execute(query).all())
            if e.src in present and e.dst in present
        )
        if len(out) >= limit:
            return out[:limit]
    return out


def degrees(db: Session, user: User, ids: dict[str, set[str]]) -> dict[str, int]:
    """노드마다 **보이는** 관계의 수 — 「+N」 의 근거. 관계마다 양 끝에서 한 번씩 센다."""
    out: dict[str, int] = defaultdict(int)
    for relation in EDGE_KINDS:
        for side, slug in (("src", relation.src), ("dst", relation.dst)):
            wanted = ids.get(slug, set())
            if not wanted:
                continue
            pairs = _pairs_query(
                db,
                user,
                relation,
                src_ids=wanted if side == "src" else None,
                dst_ids=wanted if side == "dst" else None,
                any_side=True,
            ).subquery()
            column = pairs.c.src if side == "src" else pairs.c.dst
            for ident, count in db.execute(
                select(column, func.count()).group_by(column)
            ).all():
                out[node_id(slug, ident)] += int(count)
    return dict(out)


# ------------------------------------------------------------------ 구조·찾기·훑기


def _base_query(db: Session, user: User, meta: NodeMeta) -> Select[Any]:
    """한 종류의 **보이는** 식별자 — 소프트 삭제·가시 범위를 건 select."""
    kind = meta.kind
    table = _table(meta.slug)
    id_col = table.c[kind.id_column]
    query = select(id_col)
    if kind.soft_delete:
        query = query.where(table.c["deleted_at"].is_(None))
    guard = _guard(db, user, meta.slug)
    if guard is not None:
        query = query.where(id_col.in_(guard))
    return query


def type_counts(db: Session, user: User) -> dict[str, int]:
    out: dict[str, int] = {}
    for meta in NODE_META:
        query = _base_query(db, user, meta)
        out[meta.slug] = int(
            db.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
    return out


def edge_counts(db: Session, user: User) -> dict[str, int]:
    """선 종류마다 실제로 걸린 (보이는) 쌍의 수."""
    out: dict[str, int] = {}
    for relation in EDGE_KINDS:
        query = _pairs_query(db, user, relation, src_ids=None, dst_ids=None, any_side=True)
        out[relation.slug] = int(
            db.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
    return out


def search(db: Session, user: User, q: str, limit: int) -> list[NodeInfo]:
    """종류를 가리지 않고 시작점을 찾는다 — 전체 검색과 **같은 함수**(`entity_search`)로.

    규칙이 둘이 되면 「검색에는 뜨는데 그래프에는 없다」 가 생긴다.
    """
    groups = entity_search.search(db, user, needle=q)
    wanted: dict[str, set[str]] = defaultdict(set)
    ranked: list[tuple[float, str]] = []
    for group in groups:
        if group.kind not in NODE_META_BY_SLUG:
            continue
        for hit in group.hits:
            wanted[group.kind].add(hit.id)
            ranked.append((-hit.score, node_id(group.kind, hit.id)))
    infos = lookup(db, user, wanted)
    ranked.sort()
    out: list[NodeInfo] = []
    for _, one in ranked:
        info = infos.get(one)
        if info is not None:
            out.append(info)
        if len(out) >= limit:
            break
    return out


def browse(
    db: Session, user: User, type_slug: str, *, q: str | None, limit: int, offset: int
) -> tuple[list[NodeInfo], int]:
    """한 종류의 노드를 이름순으로 쪽 단위로 — 「무엇이 있는지 모를 때 훑는 길」."""
    meta = NODE_META_BY_SLUG[type_slug]
    table = _table(type_slug)
    name = _name_expr(table, meta.kind)
    query = _base_query(db, user, meta)
    if q and q.strip():
        query = query.where(name.ilike(f"%{q.strip()}%"))
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    ids = [str(one) for one in db.scalars(query.order_by(name).offset(offset).limit(limit))]
    infos = lookup(db, user, {type_slug: set(ids)})
    ordered = [
        infos[node_id(type_slug, one)] for one in ids if node_id(type_slug, one) in infos
    ]
    return ordered, total


def all_edges_of(
    db: Session, user: User, type_slug: str, ident: str, limit: int
) -> list[Edge]:
    """노드 하나에 걸린 선 전부(상한 안에서) — 고른 노드의 관계 목록."""
    return neighbor_edges(
        db, user, {type_slug: {ident}}, fanout=limit, relations_wanted=None, types=None
    )[:limit]
