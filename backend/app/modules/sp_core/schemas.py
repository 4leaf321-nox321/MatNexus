"""SP 코어 받기 · 연결의 모양(ADR 0063)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

#: 한 번에 잇거나 끊는 줄의 상한 — 미리보기를 사람이 읽을 수 있는 크기.
LINK_BATCH_MAX = 500


class SpCoreTypeOut(BaseModel):
    slug: str
    label: str
    description: str | None = None
    published: bool
    """지금 SP 카탈로그에 있나. 거짓이면 공개가 풀렸다 — 받은 것은 남아 있다."""
    sp_count: int
    """SP 가 말한 건수."""
    received: int
    """받아 둔 것 중 살아 있는 것."""
    deleted: int
    """받아 둔 것 중 SP 에서 사라진 것."""
    relations: int
    links: int
    properties: list[dict[str, Any]]
    relation_kinds: list[dict[str, Any]]
    rows_as_of: str | None = None
    relations_as_of: str | None = None
    full_at: datetime | None = None


class SpCoreRunOut(BaseModel):
    id: uuid.UUID
    trigger: str
    full: bool
    system: str | None = None
    revision: str | None = None
    ok: bool | None = None
    """참 · 거짓 · 도는 중(null)."""
    error: str | None = None
    warnings: list[str] = []
    counts: dict[str, Any] = {}
    started_at: datetime
    finished_at: datetime | None = None


class SpCoreStatusOut(BaseModel):
    configured: bool
    """SP 주소 · 토큰이 설정돼 있나. 거짓이면 받지 않는다."""
    source: str | None = None
    """받는 곳(주소의 호스트까지만 — 토큰은 싣지 않는다)."""
    types: list[SpCoreTypeOut]
    runs: list[SpCoreRunOut]
    """최근 실행(새것부터)."""
    links: int


class SpCoreSyncRequest(BaseModel):
    full: bool = False
    """처음부터 받아 이번에 안 온 것을 사라진 것으로 둔다(부재 대조). 보통은 바뀐 것만."""


class SpCoreSyncOut(BaseModel):
    queued: bool
    job_id: uuid.UUID
    message: str


class SpCoreObjectOut(BaseModel):
    type_slug: str
    key: str
    label: str
    status: str
    deleted: bool
    hidden: bool
    merged_into: str | None = None
    previous_keys: list[str] = []
    properties: dict[str, Any] = {}
    sp_updated_at: str | None = None
    received_at: datetime


class SpCoreObjectPage(BaseModel):
    items: list[SpCoreObjectOut]
    total: int
    limit: int
    offset: int


class SpCoreRelationOut(BaseModel):
    src_type: str
    src: str
    src_label: str | None = None
    relation: str
    dst_type: str
    dst: str
    dst_label: str | None = None
    deleted: bool
    properties: dict[str, Any] = {}


class SpCoreLinkOut(BaseModel):
    id: uuid.UUID
    sp_type: str
    sp_key: str
    sp_label: str | None = None
    target: str
    target_ref: str
    target_label: str | None = None
    note: str | None = None
    created_by: str | None = None
    created_at: datetime


class SpCoreObjectDetailOut(SpCoreObjectOut):
    outgoing: list[SpCoreRelationOut]
    """이 객체에서 나가는 선(끊긴 것 포함, 최대 200)."""
    incoming: list[SpCoreRelationOut]
    """이 객체로 들어오는 선(끊긴 것 포함, 최대 200)."""
    links: list[SpCoreLinkOut]


class SpCoreMatchOut(BaseModel):
    """한 SP 타입을 한 대상과 견준 것 — **후보는 저절로 잇지 않는다.**"""

    sp_type: str
    target: str
    vocabulary: str | None = None
    sp_total: int
    target_total: int
    matched_total: int
    linked_total: int
    ambiguous_total: int
    sp_only_total: int
    target_only_total: int
    matched: list[dict[str, Any]]
    """`{sp_key, sp_label, target_ref, target_label, by: key|name|alias, link_id}`."""
    ambiguous: list[dict[str, Any]]
    """이름이 둘 이상에 맞은 것 — `{sp_key, sp_label, candidates[]}`."""
    sp_only: list[dict[str, Any]]
    """맞는 것이 없는 SP 객체 — `{sp_key, sp_label, linked}`."""


class SpCoreLinkItem(BaseModel):
    sp_type: str = Field(min_length=1, max_length=100)
    sp_key: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=30)
    """`term` · `property` · `property_group` · `property_field`."""
    target_ref: str = Field(min_length=1, max_length=200)
    """기준정보 값은 id, 물성 · 물성군 · 분야는 키."""


class SpCoreLinkRequest(BaseModel):
    items: list[SpCoreLinkItem] = Field(min_length=1, max_length=LINK_BATCH_MAX)
    note: str | None = Field(default=None, max_length=1000)
    dry_run: bool = True
    """기본이 미리보기다 — `false` 일 때만 잇고, 오류가 한 줄이라도 있으면 아무것도 안
    잇는다."""


class SpCoreLinkPlanOut(BaseModel):
    applied: bool
    new: int
    exists: int
    errors: int
    rows: list[dict[str, Any]]


class SpCoreUnlinkRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=LINK_BATCH_MAX)
    dry_run: bool = True


class SpCoreUnlinkOut(BaseModel):
    applied: bool
    rows: list[dict[str, Any]]


class SpCoreLinkPage(BaseModel):
    items: list[SpCoreLinkOut]
    total: int
    limit: int
    offset: int
