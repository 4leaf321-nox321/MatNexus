"""온톨로지 API — **AI 에게 주는 지도와 길잡이.**

세 자리뿐이다:

    GET /api/ontology            무엇이 있고 무엇과 이어지나 (지도)
    GET /api/ontology/related    이 마디 옆에 무엇이 있나
    GET /api/ontology/path       이 둘 사이에 길이 있나

**화면이 없다**(`BACKEND_ONLY`). 사람은 재료 상세에서 시료를 누르고 시험으로 가면
되지만, AI 에게는 링크가 없다 — 그 자리를 이 셋이 메운다. 별도 화면을 두면
「어디서 보나」 가 둘이 되고, 이 저장소가 반복해서 데인 「만들어 두고 안 쓰는
것」이 하나 더 는다.

로직은 없다. 판정은 `shared/graph.py`(걷기·권한)와 `shared/relations.py`(무엇이
이어지나)에 있고 여기는 그것을 HTTP 로 옮기기만 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.ontology.schemas import (
    GraphEdgeOut,
    GraphNodeOut,
    OntologyKindOut,
    OntologyOut,
    OntologyRelationOut,
    PathOut,
    RelatedOut,
)
from app.shared import graph, relations
from app.shared.auth import current_user
from app.shared.errors import AppError

router = APIRouter(prefix="/ontology", tags=["ontology"])


def _kind_or_raise(slug: str) -> relations.EntityKind:
    kind = relations.KINDS.get(slug)
    if kind is None:
        raise AppError(
            "MNX-ONTOLOGY-0001",
            f"'{slug}' 는 아는 종류가 아닙니다 — `GET /api/ontology` 로 목록을 보세요.",
            status=422,
        )
    return kind


def _edge(one: graph.Edge) -> GraphEdgeOut:
    return GraphEdgeOut(
        relation=one.relation,
        label=one.label,
        src_kind=one.src[0],
        src_id=one.src[1],
        dst_kind=one.dst[0],
        dst_id=one.dst[1],
    )


def _node(one: graph.Node) -> GraphNodeOut:
    return GraphNodeOut(kind=one.kind, id=one.id, name=one.name)


@router.get("", response_model=OntologyOut)
def get_ontology(user: User = Depends(current_user)) -> OntologyOut:
    """**지도 전체.** 어떤 종류가 있고 무엇이 무엇과 어떤 사이인가.

    AI 가 길을 찾으려면 스키마를 먼저 알아야 한다 — 사람은 화면에서 링크를 눌러
    다니지만 AI 에게는 이 응답이 지도의 전부다.
    """
    shape = relations.describe()
    return OntologyOut(
        kinds=[OntologyKindOut(**one) for one in shape["kinds"]],
        relations=[OntologyRelationOut(**one) for one in shape["relations"]],
    )


@router.get("/related", response_model=RelatedOut)
def get_related(
    kind: str = Query(description="마디 종류 — `material` · `property` · `instrument` …"),
    id: str = Query(description="식별자. `property` 만 문자열 키다"),
    relation: list[str] | None = Query(default=None, description="이 관계만 따라간다"),
    direction: str = Query(default="both", pattern="^(both|out|in)$"),
    depth: int = Query(default=1, ge=1, le=3, description="몇 홉까지"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RelatedOut:
    """**이 마디 옆에 무엇이 있나** — 관계 이름과 함께 준다.

    「왜 이어져 있나」 가 답의 절반이다. `counts` 로 관계별 개수를 먼저 주므로
    AI 는 **빈 길로 들어가지 않는다.**

    안 보이는 마디에서는 길이 끊긴다 — 이름만 가리고 계속 걸으면 「A 는 B 와
    이어져 있다」 는 사실 자체가 샌다.
    """
    _kind_or_raise(kind)
    found = graph.fetch(db, user, kind, [id])
    here = found.get(str(id))
    if here is None:
        raise AppError(
            "MNX-ONTOLOGY-0002",
            "그 마디를 찾을 수 없습니다 — 없거나, 볼 권한이 없습니다.",
            status=404,
        )

    walked = graph.traverse(
        db, user, seeds=[(kind, id)], only=relation, direction=direction, max_depth=depth
    )
    return RelatedOut(
        node=_node(here),
        nodes=[_node(one) for one in walked.nodes.values() if one.ref != here.ref],
        edges=[_edge(one) for one in walked.edges],
        counts=graph.counts(db, user, kind=kind, ident=id),
        truncated=walked.truncated,
    )


@router.get("/path", response_model=PathOut)
def get_path(
    from_kind: str = Query(alias="from_kind"),
    from_id: str = Query(alias="from_id"),
    to_kind: str = Query(alias="to_kind"),
    to_id: str = Query(alias="to_id"),
    max_depth: int = Query(default=4, ge=1, le=graph.MAX_PATH_DEPTH),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PathOut:
    """**이 둘 사이에 길이 있나** — 「이 값이 어느 장비로 나왔나」.

    사람이 사슬을 모를 때 쓴다. 가장 짧은 길 하나만 준다. 못 찾으면
    `found=false` 다 — **지어내지 않는다.**
    """
    _kind_or_raise(from_kind)
    _kind_or_raise(to_kind)

    walked = graph.path_between(
        db,
        user,
        start=(from_kind, from_id),
        goal=(to_kind, to_id),
        max_depth=max_depth,
    )
    if walked is None:
        return PathOut(
            found=False,
            note=f"{max_depth} 홉 안에 길이 없습니다 — 양끝이 실제로 안 이어져 있거나, "
            "가운데 마디를 볼 권한이 없습니다.",
        )

    refs = [(from_kind, str(from_id))]
    for one in walked:
        refs.extend([one.src, one.dst])
    nodes: dict[tuple[str, str], graph.Node] = {}
    for kind_slug, ident in refs:
        for node in graph.fetch(db, user, kind_slug, [ident]).values():
            nodes[node.ref] = node

    return PathOut(
        found=True,
        steps=[_edge(one) for one in walked],
        nodes=[_node(one) for one in nodes.values()],
    )
