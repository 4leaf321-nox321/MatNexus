"""부서(workspace)와 멤버십.

**조직 식별자를 내부 키로 감싼다**(개발계획 구조결정 1). URL과 화면에 보이는
것은 `slug`/`name` 이지만, 다른 테이블은 전부 불변인 `id` 를 가리킨다. 부서
이름이 바뀌거나 조직이 개편돼도 데이터가 묶이지 않게 하려는 것이다 — 65는
organization/project 를 OIDC claim 에 직결해서 개편 시 대응 수단이 없다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 부서 역할 (D12). 시스템 역할은 User.is_system_admin 이 갖는다.
WORKSPACE_ROLES = ("member", "manager")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    """URL에 쓰는 이름. 바뀔 수 있으므로 참조 키로 쓰지 않는다."""
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="org")
    """org(부서) | personal(개인 공간). 개인 공간은 Phase 1에서 자동 생성한다."""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
