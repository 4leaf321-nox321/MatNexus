"""물성 분류 — **분야 ⊃ 물성군 ⊃ 물성** (ADR 0054, 2026-10-03).

문헌 물성 정의(허브 키)는 키 앞머리(`mechanical.` …)로 열두 갈래로만 나뉘어 있었다. 기계
104종이 한 줄로 늘어서 「강도 계열」 「탄성 계열」 을 고를 길이 없었고, Standard Platform(SP)
의 코어 온톨로지에는 이 데이터를 바탕으로 만든 **물성 분야 · 물성군 · 물성** 세 층이 이미
있었다. 물성의 정본은 이쪽이므로(물성 목록은 MatNexus 가 SP 로 내보낸다) 분류도 이쪽에 둔다.

## 세 층이고, 포함 관계다

    분야     property_fields          기계 · 열 · 광학 …     씨앗 열둘 — 키 = 키 앞머리
    물성군   property_groups          강도 · 탄성 · 경도 …    분야 하나에 든다
    물성     property_group_members   항복강도 · 인장강도 …   물성군 하나에(없으면 미분류)

물성 하나가 두 군에 들지 않는다 — 소속 표의 기본 키가 물성 키다. 포함 관계라서다.

## 키 앞머리는 분류가 아니다

`mechanical.yield_strength` 의 `mechanical` 은 원본(MaterialTwin)이 붙인 **식별자의 일부**다 —
바뀌지 않는다. 분류는 이 표들이 정본이다. 씨앗 분야의 키를 앞머리와 같게 둬서 대개는 같은
자리에 서지만, 밀어 넣은 분류가 원본과 다르게 묶었으면 그대로 따른다(막지 않는다).

## 지우지 않고 폐기한다 · 키는 안 바뀐다

분야와 군은 바깥(SP)이 읽어 간다. 지우면 그쪽에서 행이 말없이 사라진다 — `retired_at` 을
찍고 목록에 `is_active: false` 로 남긴다(SP 연동 지침 §3.2). 이름은 고쳐도 되고, **키는 처음
정한 그대로다**(같은 지침 §12-A — 식별자는 바뀌지 않는다).

## 이관물 옆에 따로 둔다

소속을 `catalog_definitions` 의 칸으로 두지 않는다 — 별칭 · 연결(`ontology_models`)과 같은
판단이고, `property_key` 에 외래키를 안 거는 것도 같다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PropertyField(Base):
    """물성 분야 — 분류의 맨 위 층."""

    __tablename__ = "property_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    """안 바뀌는 식별자. 씨앗은 키 앞머리(`mechanical`), 여기서 만든 것은 `pf-0001` 꼴이거나
    만든 사람이 준 것(SP 의 키를 그대로 쓰면 두 시스템의 키가 같아진다)."""
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """폐기. 비어 있으면 쓰는 중이다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PropertyGroup(Base):
    """물성군 — 분야 하나에 든다."""

    __tablename__ = "property_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    """안 바뀌는 식별자 — `pg-0001` 꼴이거나 만든 사람이 준 것. **다른 분야로 옮겨도
    그대로다**."""
    field_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        # 폐기만 하므로 분야가 지워질 일이 없다. 지우려 들면 막는 편이 맞다 — 군이 떠돌게 된다.
        ForeignKey("property_fields.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PropertyGroupMember(Base):
    """물성 하나가 어느 군에 드는가. **물성 하나에 줄 하나** — 기본 키가 물성 키다."""

    __tablename__ = "property_group_members"

    property_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    """`catalog_definitions.key`. **외래키를 안 건다** — 별칭 · 연결과 같은 까닭(이관물 옆)."""
    group_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("property_groups.id", ondelete="RESTRICT"),
        index=True,
    )

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
