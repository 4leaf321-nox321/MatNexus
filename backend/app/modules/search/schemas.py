"""전체 검색 응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SearchHitOut(BaseModel):
    kind: str
    id: str
    name: str
    score: float
    matched: str = Field(
        description="왜 걸렸나 — exact · prefix · contains · similar · meaning · both"
    )
    parent_kind: str | None = None
    parent_id: str | None = None


class SearchGroupOut(BaseModel):
    kind: str
    label: str
    module: str
    hits: list[SearchHitOut]
    truncated: bool = Field(
        default=False, description="더 있다 — 종류를 골라 다시 물으면 나온다"
    )


class SearchOut(BaseModel):
    query: str
    mode: str
    groups: list[SearchGroupOut]
    total: int
    meaning: bool = Field(
        default=False,
        description="뜻으로도 찾았나. 거짓이면 글자만 본 것이다 — 화면이 그것을 말해야 "
        "사람이 「왜 이건 안 나오지」 를 엔진 탓인지 데이터 탓인지 안다",
    )


class SemanticStatusOut(BaseModel):
    """의미 검색 현황 — **왜 꺼졌는지까지.** 관리 화면이 이 하나로 그린다."""

    ready: bool
    """엔진·표·조각이 다 있나. 거짓이면 「비슷」 은 글자만 본다."""
    engine: str
    """`ollama` · `mock` · `off`."""
    model: str
    dim: int
    """설정의 차원. 표가 다른 차원이면 색인이 표를 다시 만든다."""
    table_dim: int | None
    extension: bool
    """pgvector 가 이 DB 에 켜져 있나."""
    table: bool
    chunks: int
    kinds: dict[str, int]
    """종류별 조각 수 — 무엇이 색인됐는지."""
    models: list[str]
    """표에 실제로 든 모델들. 둘이면 색인이 반쯤 갈렸다는 뜻이다."""
    indexed_at: datetime | None
    blocked: str | None
    """꺼져 있으면 그 이유와 할 일. 켜져 있으면 None."""
    running: bool = False
    """색인 작업이 큐에 있거나 도는 중."""


class SemanticReindexOut(BaseModel):
    """색인을 예약했다. **요청 안에서 돌리지 않는다** — 조각 수천 개는 수 분이 걸린다."""

    job_id: uuid.UUID
    chunks: int
    """지금 표에 든 조각 수(색인 전). 끝나면 현황에서 다시 본다."""
