"""그래프 라우터 — **큰 데이터를 통째로 안 준다.** TestScope·StandardPlatform 의 지식 그래프를
옮겨 왔다.

    overview       종류와 선 종류만 — 객체가 십만 개여도 (종류 수) 노드
    search         이름으로 시작점 찾기 (종류를 가리지 않는다 — 전체 검색과 같은 함수)
    browse         한 종류를 쪽 단위로 훑기 — 무엇을 칠지 모르는 사람의 길
    neighborhood   시작점에서 depth 단계 — fanout · node_limit 상한을 서버가 강제
    subgraph       한 종류(들)의 노드 전부 — 쪽 단위, 상한 안에서. 「N개 중 M개」
    node           고른 노드의 요약과 관계 목록

「전부」 는 없다. 전부를 보려는 사람은 overview 로 모양을 보고, 궁금한 곳에서 neighborhood 로
들어간다. 그림 하나가 모든 것을 담으려 하면 아무것도 안 보인다.

MCP 의 `get_ontology`·`related`·`find_path`(`modules/ontology`)와 **같은 정의**
(`shared/relations`)를 읽는다 — AI 가 걷는 그래프와 사람이 보는 그래프가 다르면 안 된다.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.graph import engine
from app.modules.graph.model import (
    EDGE_KIND_BY_SLUG,
    EDGE_KINDS,
    NODE_META,
    NODE_META_BY_SLUG,
    split_node_id,
)
from app.modules.graph.schemas import (
    KGBrowseOut,
    KGEdgeOut,
    KGFactOut,
    KGNeighborhoodOut,
    KGNodeDetailOut,
    KGNodeOut,
    KGOverviewOut,
    KGRelatedOut,
    KGSearchHitOut,
    KGSubgraphOut,
    KGTypeEdgeOut,
    KGTypeNodeOut,
)
from app.shared.auth import current_user
from app.shared.errors import NotFound

router = APIRouter(prefix="/graph", tags=["graph"])

#: 상한 — **클라이언트가 보낸 값을 그대로 믿지 않는다.** 기본값은 낮게(처음 뜨는 그림은
#: 읽히는 크기), 상한은 넉넉히(「더」 를 누르는 사람은 자기가 무엇을 하는지 안다).
MAX_DEPTH = 6
DEFAULT_DEPTH = 1
MAX_FANOUT = 500
DEFAULT_FANOUT = 30
MAX_NODES = 20000
DEFAULT_NODES = 300
MAX_EDGES = 60000
SEARCH_LIMIT = 20
RELATED_LIMIT = 300


def _clamp(value: int | None, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    return max(1, min(value, maximum))


def _csv(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    found = {one.strip() for one in raw.split(",") if one.strip()}
    return found or None


def _detail_path(type_slug: str, ident: str) -> str | None:
    meta = NODE_META_BY_SLUG[type_slug]
    if meta.detail_path is None:
        return None
    return meta.detail_path.replace("{id}", ident)


def _node_out(info: engine.NodeInfo, degree: int, shown: int) -> KGNodeOut:
    _, ident = info.id.split(":", 1)
    return KGNodeOut(
        id=info.id,
        label=info.label,
        key=info.key,
        sublabel=info.sublabel,
        type_slug=info.type_slug,
        type_label=NODE_META_BY_SLUG[info.type_slug].label,
        status=info.status,
        owner_workspace_slug=info.workspace_slug,
        degree=degree,
        truncated=degree > shown,
        detail_path=_detail_path(info.type_slug, ident),
    )


def _edge_out(edge: engine.Edge) -> KGEdgeOut:
    kind = EDGE_KIND_BY_SLUG[edge.kind]
    return KGEdgeOut(
        id=edge.id,
        relation=edge.kind,
        label=kind.label,
        inverse_label=kind.inverse_label,
        directed=kind.directed,
        src=edge.src,
        dst=edge.dst,
    )


def _group(ids: set[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for one in ids:
        parsed = split_node_id(one)
        if parsed:
            out[parsed[0]].add(parsed[1])
    return out


def _shown_counts(edges: list[engine.Edge]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for edge in edges:
        out[edge.src] += 1
        out[edge.dst] += 1
    return out


def _hit(info: engine.NodeInfo) -> KGSearchHitOut:
    return KGSearchHitOut(
        id=info.id,
        label=info.label,
        key=info.key,
        sublabel=info.sublabel,
        type_slug=info.type_slug,
        type_label=NODE_META_BY_SLUG[info.type_slug].label,
    )


@router.get("/overview", response_model=KGOverviewOut)
def overview(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> KGOverviewOut:
    """정의 그래프 — 종류가 노드, 관계 종류가 선. 선의 굵기는 실제로 걸린 수라 정의만 있고
    비어 있는 선은 점선으로 드러난다."""
    counts = engine.type_counts(db, user)
    edge_counts = engine.edge_counts(db, user)
    nodes = [
        KGTypeNodeOut(
            slug=one.slug,
            label=one.label,
            icon=one.icon,
            layer=one.layer,
            count=counts.get(one.slug, 0),
            detail_path=one.detail_path.replace("/{id}", "") if one.detail_path else None,
        )
        for one in sorted(NODE_META, key=lambda t: t.sort_order)
    ]
    edges = [
        KGTypeEdgeOut(
            relation=kind.slug,
            label=kind.label,
            inverse_label=kind.inverse_label,
            directed=kind.directed,
            src_type=kind.src,
            dst_type=kind.dst,
            count=edge_counts.get(kind.slug, 0),
        )
        for kind in EDGE_KINDS
    ]
    return KGOverviewOut(
        nodes=nodes,
        edges=edges,
        object_count=sum(counts.values()),
        edge_count=sum(edge_counts.values()),
    )


@router.get("/search", response_model=list[KGSearchHitOut])
def search(
    q: str = Query(min_length=1, description="이름·번호·키·별칭의 일부"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[KGSearchHitOut]:
    """종류를 가리지 않고 시작점을 찾는다 — 무엇이 어느 종류인지 모르는 사람의 자리."""
    return [_hit(one) for one in engine.search(db, user, q, SEARCH_LIMIT)]


@router.get("/browse", response_model=KGBrowseOut)
def browse(
    type: str = Query(description="종류 slug"),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KGBrowseOut:
    """한 종류를 이름순으로 쪽 단위로 — 훑어서 시작점을 고르는 길."""
    if type not in NODE_META_BY_SLUG:
        raise NotFound("MNX-GRAPH-0002", f"종류를 찾을 수 없습니다: {type}")
    items, total = engine.browse(db, user, type, q=q, limit=limit, offset=offset)
    return KGBrowseOut(
        items=[_hit(one) for one in items], total=total, limit=limit, offset=offset
    )


@router.get("/neighborhood", response_model=KGNeighborhoodOut)
def neighborhood(
    focus: str = Query(description="시작 노드 id (<종류>:<식별자>)"),
    depth: int | None = Query(default=None, description=f"몇 단계까지. 최대 {MAX_DEPTH}"),
    fanout: int | None = Query(
        default=None, description=f"노드 하나가 데려오는 이웃 수. 최대 {MAX_FANOUT}"
    ),
    limit: int | None = Query(default=None, description=f"노드 상한. 최대 {MAX_NODES}"),
    relations: str | None = Query(default=None, description="선 종류 slug, 쉼표로"),
    types: str | None = Query(default=None, description="이웃 종류 slug, 쉼표로"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KGNeighborhoodOut:
    """시작점에서 depth 단계까지의 이웃. **한 단계씩, 노드마다 fanout 개까지, 전체 limit
    개까지.** 잘리면 `truncated` 와 노드의 `degree` 로 잘렸다고 말한다."""
    parsed = split_node_id(focus)
    if parsed is None:
        raise NotFound("MNX-GRAPH-0001", "노드를 찾을 수 없습니다.")
    start_type, start_id = parsed
    start = engine.lookup(db, user, {start_type: {start_id}}).get(focus)
    if start is None:
        raise NotFound("MNX-GRAPH-0001", "노드를 찾을 수 없습니다.")
    focus = start.id  # 식별자 표기를 서버 것으로(대문자 uuid 등)

    depth_n = _clamp(depth, default=DEFAULT_DEPTH, maximum=MAX_DEPTH)
    fanout_n = _clamp(fanout, default=DEFAULT_FANOUT, maximum=MAX_FANOUT)
    node_limit = _clamp(limit, default=DEFAULT_NODES, maximum=MAX_NODES)
    wanted_relations = _csv(relations)
    wanted_types = _csv(types)
    if wanted_types is not None:
        wanted_types.add(start_type)  # 시작점의 종류는 늘 든다

    seen: set[str] = {focus}
    order: list[str] = [focus]
    edges: dict[str, engine.Edge] = {}
    frontier: set[str] = {focus}
    truncated = False
    for _ in range(depth_n):
        if not frontier:
            break
        found = engine.neighbor_edges(
            db,
            user,
            _group(frontier),
            fanout=fanout_n,
            relations_wanted=wanted_relations,
            types=wanted_types,
        )
        next_frontier: set[str] = set()
        for edge in found:
            other = edge.dst if edge.src in frontier else edge.src
            if other not in seen:
                if len(seen) >= node_limit:
                    truncated = True
                    continue
                seen.add(other)
                order.append(other)
                next_frontier.add(other)
            edges[edge.id] = edge
        frontier = next_frontier

    # 이름을 찾는다 — 지운 것·안 보이는 것은 여기서 떨어지고, 그 끝을 가진 선도 버린다.
    infos = engine.lookup(db, user, _group(set(order)))
    order = [one for one in order if one in infos]
    present = set(order)
    # 이미 실린 노드끼리의 선을 마저 긋는다 — fanout 에 밀린 관계도 양 끝이 화면에 있으면
    # 그린다.
    for edge in engine.induced_edges(
        db, user, _group(present), relations_wanted=wanted_relations, limit=MAX_EDGES
    ):
        edges[edge.id] = edge
    kept = [e for e in edges.values() if e.src in present and e.dst in present]
    if len(kept) > MAX_EDGES:
        truncated = True
        kept = kept[:MAX_EDGES]
    degree_of = engine.degrees(db, user, _group(present))
    shown = _shown_counts(kept)
    nodes: list[KGNodeOut] = []
    for one in order:
        node = _node_out(infos[one], degree_of.get(one, 0), shown.get(one, 0))
        truncated = truncated or node.truncated
        nodes.append(node)
    return KGNeighborhoodOut(
        focus=focus,
        nodes=nodes,
        edges=[_edge_out(e) for e in kept],
        depth=depth_n,
        fanout=fanout_n,
        node_limit=node_limit,
        truncated=truncated,
    )


@router.get("/subgraph", response_model=KGSubgraphOut)
def subgraph(
    types: str = Query(description="종류 slug, 쉼표로"),
    relations: str | None = Query(default=None, description="선 종류 slug, 쉼표로"),
    q: str | None = Query(default=None, description="이름의 일부"),
    limit: int | None = Query(default=None, description=f"노드 상한. 최대 {MAX_NODES}"),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KGSubgraphOut:
    """한 종류(들)의 노드를 **쪽 단위로** 전부, 그 사이의 선과 함께. 「N개 중 M개」."""
    node_limit = _clamp(limit, default=DEFAULT_NODES, maximum=MAX_NODES)
    wanted = [one for one in (_csv(types) or set()) if one in NODE_META_BY_SLUG]
    if not wanted:
        raise NotFound("MNX-GRAPH-0002", f"종류를 찾을 수 없습니다: {types}")
    wanted.sort(key=lambda slug: NODE_META_BY_SLUG[slug].sort_order)
    # 쪽을 종류마다 나눠 채운다 — 한 종류가 첫 쪽을 다 차지하면 선이 없는 그림이 된다.
    share = max(1, node_limit // len(wanted))
    per_type_offset = offset // len(wanted)
    infos: list[engine.NodeInfo] = []
    total = 0
    for slug in wanted:
        items, n = engine.browse(db, user, slug, q=q, limit=share, offset=per_type_offset)
        infos.extend(items)
        total += n
    infos = infos[:node_limit]
    present = {one.id for one in infos}
    edges = engine.induced_edges(
        db, user, _group(present), relations_wanted=_csv(relations), limit=MAX_EDGES
    )
    degree_of = engine.degrees(db, user, _group(present))
    shown = _shown_counts(edges)
    nodes = [_node_out(one, degree_of.get(one.id, 0), shown.get(one.id, 0)) for one in infos]
    return KGSubgraphOut(
        nodes=nodes,
        edges=[_edge_out(e) for e in edges],
        total=total,
        limit=node_limit,
        offset=offset,
        truncated=offset + len(infos) < total or len(edges) >= MAX_EDGES,
    )


#: 부제가 무엇을 뜻하는지 — 종류마다 다르다. 없는 종류는 「설명」.
SUBLABEL_NAMES: dict[str, str] = {
    "material": "재료군 · 등급",
    "sample": "제조사",
    "specimen": "방향",
    "test_run": "시험자",
    "property_card": "방향",
    "property": "SI 단위",
    "catalog_material": "제조사",
    "source": "연도",
    "instrument": "분류",
    "parameter_set": "모델",
    "term": "축",
    "test_type": "약어",
    "formula": "갈래",
    "guide_document": "주제",
}
KEY_NAMES: dict[str, str] = {
    "material": "재료 번호",
    "sample": "로트",
    "commission": "의뢰 번호",
    "equipment_unit": "자산번호",
    "workspace": "주소",
    "source": "DOI",
    "catalog_material": "재료 코드",
}


@router.get("/node", response_model=KGNodeDetailOut)
def node(
    id: str = Query(description="노드 id (<종류>:<식별자>)"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KGNodeDetailOut:
    """고른 노드의 요약 — 그래프를 떠나지 않고 「이게 뭐지」 에 답한다. 관계는 종류별로 화면이
    묶는다."""
    parsed = split_node_id(id)
    if parsed is None:
        raise NotFound("MNX-GRAPH-0001", "노드를 찾을 수 없습니다.")
    type_slug, ident = parsed
    info = engine.lookup(db, user, {type_slug: {ident}}).get(id)
    if info is None:
        raise NotFound("MNX-GRAPH-0001", "노드를 찾을 수 없습니다.")
    edges = engine.all_edges_of(db, user, type_slug, ident, RELATED_LIMIT)
    others = {e.dst if e.src == info.id else e.src for e in edges}
    names = engine.lookup(db, user, _group(others))
    related: list[KGRelatedOut] = []
    for edge in edges:
        outgoing = edge.src == info.id
        other = edge.dst if outgoing else edge.src
        other_info = names.get(other)
        if other_info is None:
            continue
        kind = EDGE_KIND_BY_SLUG[edge.kind]
        related.append(
            KGRelatedOut(
                relation=edge.kind,
                label=kind.label if outgoing else kind.inverse_label or kind.label,
                outgoing=outgoing,
                node_id=other,
                node_label=other_info.label,
                node_type_label=NODE_META_BY_SLUG[other_info.type_slug].label,
            )
        )
    related.sort(key=lambda one: (not one.outgoing, one.label, one.node_label))
    degree_total = engine.degrees(db, user, {type_slug: {ident}}).get(info.id, 0)
    facts = [KGFactOut(label="종류", value=NODE_META_BY_SLUG[type_slug].label)]
    if info.sublabel:
        facts.append(
            KGFactOut(label=SUBLABEL_NAMES.get(type_slug, "설명"), value=info.sublabel)
        )
    if info.key:
        facts.append(KGFactOut(label=KEY_NAMES.get(type_slug, "키"), value=info.key))
    facts.append(KGFactOut(label="상태", value=info.status))
    return KGNodeDetailOut(
        id=info.id,
        label=info.label,
        key=info.key,
        type_slug=type_slug,
        type_label=NODE_META_BY_SLUG[type_slug].label,
        status=info.status,
        detail_path=_detail_path(type_slug, ident),
        facts=facts,
        related=related,
        related_total=degree_total,
    )
