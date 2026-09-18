"""그래프 응답 — **화면이 그리는 데 필요한 것만.** 나머지는 노드를 눌렀을 때 상세가 준다.

이름에 `KG` 를 붙인 이유: `OverviewOut`(홈 통계) · `RelatedOut`·`GraphNodeOut`(MCP 온톨로지)이
이미 있다. 같은 이름이 둘이면 OpenAPI 가 모듈 경로를 앞에 붙여 프론트 타입 이름이 깨진다.
"""

from __future__ import annotations

from pydantic import BaseModel

# --- 구조 그림 ------------------------------------------------------------------


class KGTypeNodeOut(BaseModel):
    slug: str
    label: str
    icon: str
    layer: str
    count: int
    """보이는 객체 수. 남의 부서 재료·시험은 안 센다."""
    detail_path: str | None
    """목록 화면 주소 서식(`{id}` 없이 쓰면 목록). None 이면 화면이 없다."""


class KGTypeEdgeOut(BaseModel):
    relation: str
    label: str
    inverse_label: str
    directed: bool
    src_type: str
    dst_type: str
    count: int
    """실제로 걸린 관계 수. 0 이면 **정의만 있고 아직 아무것도 안 이어진** 것."""


class KGOverviewOut(BaseModel):
    nodes: list[KGTypeNodeOut]
    edges: list[KGTypeEdgeOut]
    object_count: int
    edge_count: int


# --- 탐색 그림 ------------------------------------------------------------------


class KGNodeOut(BaseModel):
    id: str
    """`<종류>:<식별자>` — 물성 정의만 키(`property:<key>`), 나머지는 uuid."""
    label: str
    key: str | None
    sublabel: str | None
    type_slug: str
    type_label: str
    status: str
    owner_workspace_slug: str | None
    degree: int
    """이 노드에 걸린 **보이는** 관계의 수 — 잘렸으면 화면의 수보다 크다."""
    truncated: bool
    """화면에 실린 것보다 관계가 더 있다. 「+N 더」 의 근거."""
    detail_path: str | None


class KGEdgeOut(BaseModel):
    id: str
    relation: str
    label: str
    inverse_label: str
    directed: bool
    src: str
    dst: str


class KGNeighborhoodOut(BaseModel):
    focus: str
    nodes: list[KGNodeOut]
    edges: list[KGEdgeOut]
    depth: int
    fanout: int
    node_limit: int
    truncated: bool


class KGSubgraphOut(BaseModel):
    nodes: list[KGNodeOut]
    edges: list[KGEdgeOut]
    total: int
    limit: int
    offset: int
    truncated: bool


class KGSearchHitOut(BaseModel):
    id: str
    label: str
    key: str | None
    sublabel: str | None
    type_slug: str
    type_label: str


class KGBrowseOut(BaseModel):
    items: list[KGSearchHitOut]
    total: int
    limit: int
    offset: int


# --- 고른 노드 -------------------------------------------------------------------


class KGFactOut(BaseModel):
    label: str
    value: str


class KGRelatedOut(BaseModel):
    relation: str
    label: str
    """방향에 맞는 말 — 나가는 선이면 label, 들어오는 선이면 inverse_label."""
    outgoing: bool
    node_id: str
    node_label: str
    node_type_label: str


class KGNodeDetailOut(BaseModel):
    id: str
    label: str
    key: str | None
    type_slug: str
    type_label: str
    status: str
    detail_path: str | None
    facts: list[KGFactOut]
    related: list[KGRelatedOut]
    related_total: int
    """걸린 관계 전체 수. `related` 는 상한 안에서만."""
