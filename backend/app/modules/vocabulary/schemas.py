"""어휘 API 의 모양."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class VocabularyOut(BaseModel):
    slug: str
    label: str
    entry_policy: str
    """`open` 이면 화면이 '새로 추가' 를 보여 줘도 된다. `closed` 면 감춘다 —
    눌러 봐야 서버가 거절하는 버튼은 두지 않는다."""
    term_count: int


class TermOut(BaseModel):
    id: uuid.UUID
    value: str
    usage_count: int
    """피커가 많이 쓰는 것을 위로 올린다. 개수가 보이면 고르기 전에 안다."""


class TermCreateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)
