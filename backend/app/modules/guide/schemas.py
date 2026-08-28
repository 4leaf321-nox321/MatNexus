"""물성 핸드북 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.guide.models import KINDS

KEY_PATTERN = r"^[a-z0-9][a-z0-9-]{0,78}$"


def _doc_body(value: Any) -> dict[str, Any]:
    """편집기 문서인가. **정본이 되는 값이라 모양을 여기서 막는다** — 아무 JSON 이나
    들어가면 화면이 그리다가 죽고, 그 절은 그때부터 아무도 못 연다."""
    if not isinstance(value, dict) or value.get("type") != "doc":
        raise ValueError(
            "편집기 문서가 아닙니다 — `{type: 'doc', content: [...]}` 여야 합니다."
        )
    content = value.get("content", [])
    if not isinstance(content, list):
        raise ValueError("문서의 content 는 목록이어야 합니다.")
    return value


class DocumentCreate(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    kind: str
    topic: str | None = Field(default=None, max_length=50)
    summary: str | None = Field(default=None, max_length=500)
    position: int = 0

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        if value not in KINDS:
            raise ValueError(f"종류는 {', '.join(KINDS)} 중 하나입니다.")
        return value


class DocumentUpdate(BaseModel):
    """「안 보낸 것」 과 「비운 것」 을 구별한다."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = None
    topic: str | None = Field(default=None, max_length=50)
    summary: str | None = Field(default=None, max_length=500)
    position: int | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str | None) -> str | None:
        if value is not None and value not in KINDS:
            raise ValueError(f"종류는 {', '.join(KINDS)} 중 하나입니다.")
        return value


class SectionCreate(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    position: int = 0
    body: dict[str, Any] | None = None
    """만들면서 본문까지 주면 **승인된 본문**으로 들어간다 — 구조를 만드는 사람은
    검토자다."""

    @field_validator("body")
    @classmethod
    def _body(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else _doc_body(value)


class SectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = None


class RevisionCreate(BaseModel):
    body: dict[str, Any]
    note: str | None = Field(default=None, max_length=500)
    publish: bool = False
    """검토자가 직접 고칠 때 — 초안을 만들고 바로 승인한다. 검토자가 아니면 거절."""

    @field_validator("body")
    @classmethod
    def _body(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _doc_body(value)


class ReviewIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class Person(BaseModel):
    id: uuid.UUID
    name: str


class SectionBrief(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    position: int
    revision_no: int
    pending_count: int = 0
    """검토를 기다리는 초안 수. 목차에서 보여야 검토자가 어디로 갈지 안다."""
    updated_at: datetime


class SectionOut(SectionBrief):
    document_id: uuid.UUID
    document_key: str
    document_title: str
    body: dict[str, Any]
    updated_by: Person | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    kind: str
    topic: str | None
    summary: str | None
    position: int
    source_filename: str | None
    updated_at: datetime
    sections: list[SectionBrief]


class RevisionOut(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    section_key: str
    section_title: str
    document_key: str
    document_title: str
    status: str
    body: dict[str, Any]
    note: str | None
    author: Person | None
    created_at: datetime
    reviewed_by: Person | None
    reviewed_at: datetime | None
    review_note: str | None


class SearchHit(BaseModel):
    section_id: uuid.UUID
    document_key: str
    document_title: str
    kind: str
    topic: str | None
    section_key: str
    section_title: str
    snippet: str
    """맞은 자리 앞뒤 한 줄. **어디가 맞았는지** 보여야 제목만 보고 열었다 닫지 않는다."""


class AssetOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size: int
    url: str
    """본문에 넣는 주소. 상대경로 — 서버를 옮겨도 그대로다."""


__all__ = [
    "AssetOut",
    "DocumentCreate",
    "DocumentOut",
    "DocumentUpdate",
    "Person",
    "ReviewIn",
    "RevisionCreate",
    "RevisionOut",
    "SearchHit",
    "SectionBrief",
    "SectionCreate",
    "SectionOut",
    "SectionUpdate",
]
