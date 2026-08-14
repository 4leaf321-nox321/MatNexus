"""계정.

소유권 승계(구조결정 4)를 위해 사용자는 **지우지 않고 비활성화**하는 것을
기본으로 둔다. `deleted_at` 이 있는 행은 로그인할 수 없지만 그 사람이 등록한
시험 데이터의 소유자 참조는 살아 있다. 실제 승계 절차는 의존성 레지스트리와
함께 Phase 1에서 붙인다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_system_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    """초기 관리자와 관리자 발급 계정의 시드 비밀번호가 그대로 남는 사고를 막는다."""

    home_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    """소속 부서. 멤버십(옛 부서 포함)과 달리 '지금 어디 소속인가'를 나타낸다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
