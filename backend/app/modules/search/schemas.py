"""전체 검색 응답 모양."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchHitOut(BaseModel):
    kind: str
    id: str
    name: str
    score: float
    matched: str = Field(description="왜 걸렸나 — exact · prefix · contains · similar")
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
