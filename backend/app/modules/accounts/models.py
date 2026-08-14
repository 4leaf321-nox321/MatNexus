"""계정.

소유권 승계(구조결정 4)를 위해 사용자는 **지우지 않고 정지**하는 것을 기본으로
둔다. `deleted_at` 이 있는 행은 로그인할 수 없지만 그 사람이 등록한 시험 데이터의
소유자 참조는 살아 있다. 실제 승계 절차는 의존성 레지스트리와 함께 붙인다(1-3).

계정 상태를 불리언이 아니라 `status` 로 두는 이유: 셀프 가입 + 관리자 승인
방식에서는 "승인 대기"가 활성/비활성과 별개의 상태다. `is_active` 하나로 두면
승인 대기와 정지를 구분할 수 없어, 관리자 화면이 "왜 로그인이 안 되는지"를
설명하지 못한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 계정 상태.
#:   pending    가입 신청. 로그인 불가. 관리자 승인 대기
#:   active     정상
#:   suspended  관리자가 정지. 자료는 남기고 접근만 막는다
USER_STATUSES = ("pending", "active", "suspended")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    is_system_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    requested_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    """가입 신청 시 고른 희망 부서. 승인하면 멤버십이 생기고 이 값은 기록으로 남는다."""

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    """거절 사유. SMTP 가 없어 통보를 앱 안에서 해야 하므로 사유를 남겨 둔다."""
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

    @property
    def can_sign_in(self) -> bool:
        """로그인 가능 여부는 여기 한 곳에서만 판정한다.

        인증(로그인)·재발급(refresh)·요청 인가(current_user)·PAT 세 군데가 같은
        조건을 각자 쓰고 있으면, 상태가 하나 늘 때 한 군데를 빠뜨린다.
        """
        return self.status == "active" and self.deleted_at is None
