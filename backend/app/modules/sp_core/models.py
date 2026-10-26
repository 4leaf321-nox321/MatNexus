"""SP 코어 온톨로지의 **받은 원본**과 **연결** (ADR 0063, 2026-10-21).

Standard Platform(SP)의 코어 온톨로지(부서 · 기관 · 장비 · PLM 개발모델 · 물성 …)를 SP 의 코어
API(`/api/core`, 연동 지침서 §4.2)로 받아 **받은 그대로** 쌓는다. 받기와 잇기를 가른다:

    받은 원본   sp_core_types · sp_core_objects · sp_core_relations   SP 가 정본 — 여기서 안
    고친다
    받은 기록   sp_core_runs                                           언제 · 무엇을 · 몇 건 ·
    오류
    연결       sp_core_links                                          SP 객체 ↔ 기준정보 값 ·
    물성 …

## 왜 기준정보에 바로 넣지 않나

어느 SP 타입이 어느 기준정보 축인지가 아직 애매하다(기관 → 제조사 · 거래처? 부서 → 사업부?).
그것을 개발 서버에서 코드로 못 박으면 운영 데이터를 못 본 채 정하게 된다 — 개발 DB 에는 운영의
기준정보 값이 없고, 개발 서버는 운영 SP 에 닿지 못한다. 그래서 받기만 하고, 잇기는 운영에서
사람이 AI(MCP)로 후보를 보며 확인한다. 연결은 **기록**일 뿐 아직 값을 잠그거나 덮지 않는다.

## SP 키는 바뀔 수 있다

SP 는 키가 바뀌면 `renamed_from` · `previous_keys` 를 준다(지침 §4.2 규칙 4). 받은 원본은
`(타입, key)` 로 가리고, 키가 옮겨지면 그 행과 **연결의 `sp_key` 를 함께** 옮긴다 — 안 그러면
같은 것이 둘이 되고 연결이 옛 키에 남는다. 그래서 연결은 받은 원본에 외래키를 걸지 않고
`(sp_type, sp_key)` 로 든다(키를 옮기는 자리가 한 곳이다 — `sync._rename`).

## 지우지 않는다

SP 에서 지워진 것은 `deleted` 로 온다 — 받은 원본도 행을 지우지 않고 그 표시를 남긴다(규칙 4 ·
8: 되살아날 수 있다). 연결도 그대로 둔다 — 사람이 보고 끊는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: SP 의 한도와 같다 — 타입 slug · 객체 key(`objects.key` 120).
SLUG_MAX = 100
KEY_MAX = 120


class SpCoreType(Base):
    """SP 가 코어로 공개한 타입 하나 — 카탈로그(`GET /api/core`)의 한 줄."""

    __tablename__ = "sp_core_types"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(SLUG_MAX), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """칸 설명(`key · label · data_type · unit · multi · enum_options · ref_type_slug`)
    그대로."""
    relation_kinds: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """이 타입에서 출발하는 관계 종류 그대로(`slug · label · src · dst`)."""
    sp_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """SP 가 말한 건수 — 받은 수와 견줘 빠진 것을 본다."""
    published: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    """지금 카탈로그에 있나. 공개가 풀리면 거짓이 되고 행은 남는다(`APP-CORE-0001`)."""
    rows_as_of: Mapped[str | None] = mapped_column(String(40))
    """행을 **끝까지 받은 뒤** 저장한 SP 의 `as_of` — 다음 주기의 `since`. 우리 시계로 만들지
    않는다(규칙 1 · 2)."""
    relations_as_of: Mapped[str | None] = mapped_column(String(40))
    """선의 기준 시각 — 행과 **따로** 적는다(지침 §4.2 「선 가져오기」)."""
    full_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """마지막으로 처음부터 받아 **부재 대조**까지 끝낸 때(규칙 7). 오래되면 다시 전량을
    받는다."""
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SpCoreObject(Base):
    """받은 객체 하나 — 코어 API 행의 봉투와 `properties` 그대로."""

    __tablename__ = "sp_core_objects"
    __table_args__ = (
        UniqueConstraint("type_slug", "key", name="uq_sp_core_objects_type_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type_slug: Mapped[str] = mapped_column(String(SLUG_MAX), index=True)
    key: Mapped[str] = mapped_column(String(KEY_MAX))
    label: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    """`active` · `deprecated` — SP 가 준 그대로. 그만 쓰는 것이지 지운 것이 아니다."""
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """SP 에서 사라졌다(또는 이 토큰으로 더 안 보인다 — `hidden`). 행은 남긴다."""
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    merged_into: Mapped[str | None] = mapped_column(String(KEY_MAX))
    """합쳐져서 사라졌으면 이긴 쪽의 key — 연결을 그쪽으로 옮길지는 사람이 본다."""
    previous_keys: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    sp_updated_at: Mapped[str | None] = mapped_column(String(40))
    seen_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    """이 행을 마지막으로 받은 실행 — 전량을 받은 뒤 이번에 안 온 것을 가리는 자리(규칙 7)."""
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SpCoreRelation(Base):
    """받은 선 하나 — `(출발 타입, src, relation, dst, dst_type)` 으로 가린다(지침 §4.2)."""

    __tablename__ = "sp_core_relations"
    __table_args__ = (
        UniqueConstraint(
            "src_type", "src", "relation", "dst", "dst_type", name="uq_sp_core_relations_edge"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    src_type: Mapped[str] = mapped_column(String(SLUG_MAX), index=True)
    src: Mapped[str] = mapped_column(String(KEY_MAX))
    relation: Mapped[str] = mapped_column(String(SLUG_MAX))
    dst: Mapped[str] = mapped_column(String(KEY_MAX))
    dst_type: Mapped[str] = mapped_column(String(SLUG_MAX), index=True)
    evidence_note: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """끊긴 선 — 선은 있음/없음이라 받는 쪽도 끊는다. 행은 남겨 언제 끊겼는지 본다."""
    sp_updated_at: Mapped[str | None] = mapped_column(String(40))
    seen_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SpCoreRun(Base):
    """한 번 받은 기록 — **언제 · 무엇을 · 몇 건 · 왜 멈췄나.**

    받기는 워커가 밤에 돈다. 실패가 로그에만 남으면 사람은 「왜 SP 에 있는 것이 여기 없지」 를
    며칠 뒤에야 묻는다 — 여기 남겨 상태 조회(MCP)가 그대로 말한다."""

    __tablename__ = "sp_core_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")
    """`schedule` · `manual`."""
    full: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    system: Mapped[str | None] = mapped_column(String(100))
    """SP 설치 이름(카탈로그의 `system`) — 어디서 받은 것인지."""
    revision: Mapped[str | None] = mapped_column(String(100))
    """카탈로그의 판. 지난번과 다르면 SP 의 공개 구조(칸 · 관계 종류)가 바뀐 것이다."""
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """타입마다 `{rows, deleted, renamed, relations, absent, …}`."""
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    ok: Mapped[bool | None] = mapped_column(Boolean)
    """참 · 거짓 · 아직 도는 중(None)."""
    error: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpCoreLink(Base):
    """SP 객체 하나 ↔ MatNexus 의 무엇 하나 — **「같은 것」 이라는 사람의 확인.**

    대상(`target_kind`):

        term             기준정보 값(`vocabulary_terms.id`)
        property         물성(문헌 · 사내 키, `catalog_definitions.key`)
        property_group   물성군(`property_groups.key`)
        property_field   물성 분야(`property_fields.key`)

    대상에 외래키를 안 건다 — 물성 쪽은 키로 잇는 자리(`property_links` 와 같은 판단)이고, 한
    표에
    여러 종류가 서기 때문이다. 대상이 있는지는 만들 때 본다(`links.plan`).

    **연결은 지금 아무 값도 바꾸지 않는다.** 잠금 · 덮어쓰기 · 자동 생성은 연결이 쌓인 뒤 따로
    정한다(ADR 0063).
    """

    __tablename__ = "sp_core_links"
    __table_args__ = (
        UniqueConstraint(
            "sp_type", "sp_key", "target_kind", "target_ref", name="uq_sp_core_links_pair"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sp_type: Mapped[str] = mapped_column(String(SLUG_MAX), index=True)
    sp_key: Mapped[str] = mapped_column(String(KEY_MAX), index=True)
    target_kind: Mapped[str] = mapped_column(String(30))
    target_ref: Mapped[str] = mapped_column(String(200), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
