"""온톨로지 응답 모양. **AI 가 그대로 읽는다.**"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OntologyKindOut(BaseModel):
    slug: str
    label: str
    module: str = Field(description="어느 모듈의 것인가 — 화면을 찾을 때 쓴다")
    id_kind: str = Field(
        default="uuid",
        description="식별자 생김새 — `uuid` 이거나 `key`(문자열). `property` 만 `key` 다",
    )


class OntologyRelationOut(BaseModel):
    slug: str
    label: str
    inverse_label: str
    src: str
    dst: str
    directed: bool
    transitive: bool
    source: str = Field(description="관계가 실린 자리 — `fk:…` · `table:…` · `edge`")
    note: str = ""


class DeckRequirementsOut(BaseModel):
    """**코드에 있던 관계 셋**을 지도에 싣는다(2026-09-16, [계획] 온톨로지 고도화 §2-A).

    표가 아니라 레지스트리에 사는 사실이라 `relations` 의 마디·관계로는 못 걷는다 —
    대신 여기 정적으로 적어 AI 가 「이 형식엔 무엇이 필요하고, 그 블록은 어느 시험이
    내고, 어느 문헌 물성이 채우나」 를 한 번에 읽는다. 재료 하나에 대어 본 답은
    `GET /fitting/materials/{id}/deck-readiness`."""

    format_needs: dict[str, list[str]]
    """형식 key → 반드시 있어야 하는 블록."""
    block_from_tests: dict[str, list[str]]
    """블록 → 그 블록을 내는 시험 종류 키."""
    block_fills: dict[str, list[str]]
    """블록 → 그 블록의 값을 채우는 문헌 물성 키(`catalog_definitions.key`)."""


class OntologyOut(BaseModel):
    """지도 전체. **AI 는 이걸 읽고 다음 질문을 만든다.**"""

    kinds: list[OntologyKindOut]
    relations: list[OntologyRelationOut]
    deck_requirements: DeckRequirementsOut


class GraphNodeOut(BaseModel):
    kind: str
    id: str
    name: str


class GraphEdgeOut(BaseModel):
    relation: str
    label: str = Field(description="이 방향으로 읽는 말")
    src_kind: str
    src_id: str
    dst_kind: str
    dst_id: str


class RelatedOut(BaseModel):
    node: GraphNodeOut
    nodes: list[GraphNodeOut] = []
    edges: list[GraphEdgeOut] = []
    counts: dict[str, int] = Field(
        default={}, description="관계별 이웃 수 — 0인 관계는 안 싣는다"
    )
    truncated: bool = False


class PathOut(BaseModel):
    """두 마디 사이의 길. **못 찾으면 `found=false`** — 지어내지 않는다."""

    found: bool
    steps: list[GraphEdgeOut] = []
    nodes: list[GraphNodeOut] = []
    note: str | None = None
