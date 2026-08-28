"""알림 — 규칙 / 발화 상태 / 발송을 세 테이블로 나눈다.

**합쳐 만든 뒤 나누는 비용이 크다**(개발계획 구조결정 6). RA 의 경보 모델이
AlertRule / AlertRuleState / AlertDigestRun 3분할인 이유가 그것이고, 비교표는
"규칙과 상태를 섞을 때 생기는 중복 발송·상태 꼬임을 구조로 차단" 이라고 적었다.

역할이 다르다.
  Rule          누가 어떤 사건에 알림을 받는가          (설정, 자주 바뀜)
  RuleState     그 규칙이 마지막으로 언제 무엇에 발화했나 (중복 발송 방지)
  Notification  실제로 사람에게 도달한 것                (읽음 처리, 이력)

SMTP 가 없으므로 지금 채널은 인앱뿐이다. `channel` 컬럼을 두어 메일이 열릴 때
자리만 잡아 둔다 — 나중에 붙일 때 테이블을 바꾸지 않아도 되게.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 알림을 만드는 사건.
#:   account.signup   가입 신청이 들어왔다        → 시스템 관리자에게
#:   account.decided  내 신청이 승인/거절됐다      → 신청자에게
#:   pipelines.needs_specimen  장비에서 온 파일에 시편을 못 붙였다 → 부서 관리자에게
EVENT_KINDS = ("account.signup", "account.decided", "pipelines.needs_specimen")

CHANNELS = ("inapp",)  # 'email' 은 SMTP 가 열리면 추가한다


class NotificationRule(Base):
    """누가 어떤 사건에 알림을 받는가."""

    __tablename__ = "notification_rules"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "event_kind", "channel", name="uq_notification_rules_target"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    event_kind: Mapped[str] = mapped_column(String(50), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="inapp")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotificationRuleState(Base):
    """규칙이 마지막으로 발화한 지점.

    `last_key` 는 사건을 식별하는 문자열이다(예: 신청 계정 id). 같은 키로 다시
    들어오면 보내지 않는다 — 워커 재시도나 중복 이벤트로 알림이 두 번 가는 것을
    막는 것이 이 테이블의 존재 이유다.
    """

    __tablename__ = "notification_rule_states"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("notification_rules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fire_count: Mapped[int] = mapped_column(default=0)


class Notification(Base):
    """사람에게 도달한 알림 하나."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("notification_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_kind: Mapped[str] = mapped_column(String(50), index=True)

    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    """클릭했을 때 갈 화면. 알림만 보고 무엇을 해야 할지 모르면 소용이 없다."""

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
