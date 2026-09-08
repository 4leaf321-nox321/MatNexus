"""전체 검색 응답 모양."""

from __future__ import annotations

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
