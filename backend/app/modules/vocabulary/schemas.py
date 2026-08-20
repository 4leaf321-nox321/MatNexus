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
    parent_value: str | None = None
    """상위 축의 값. 화면이 "이 강종은 Metal/Steel 아래 있습니다" 를 말하는 데 쓴다."""
    usage_count: int
    """피커가 많이 쓰는 것을 위로 올린다. 개수가 보이면 고르기 전에 안다.

    **이름을 고칠 때 몇 건이 따라오는지**이기도 하다. 외래키라 한 행을 고치면
    이 수만큼이 함께 바뀐다."""
    status: str = "active"


class TermCreateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    parent_value: str | None = Field(default=None, max_length=200)
    """상위 축의 값. 주면 새 값이 그 아래로 들어간다."""


class TermUpdateRequest(BaseModel):
    """표기 고치기와 감추기. **관리자만.**

    값을 지우는 길은 없다 — 지우면 그것을 가리키던 시료가 무엇이었는지 알 수
    없게 된다. `deprecated` 로 감추면 피커에서만 사라진다.
    """

    value: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|deprecated)$")
