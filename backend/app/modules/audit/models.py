"""접근 로그 — 감사 로그와 **목적이 다르다**.

비교표 6-1: *"감사 로그와 지원 로그는 목적이 다르다. '그 화면에서 안 돼요' 를
재현하려면 누가 어느 화면을 언제 열었는지가 필요하다."*

  접근 로그(여기)  사용자 지원용. 누가 언제 어느 화면·API 를 썼는가
  감사 로그(뒤)    무결성용. 무엇이 바뀌었는가, 누가 승인했는가

둘을 한 테이블에 섞으면 보존 기간이 충돌한다 — 접근 로그는 몇 달이면 지워도
되지만 감사 로그는 남아야 한다. 처음부터 나눈다.

파일 로그(app.log)와도 역할이 다르다. 파일은 요청 단위 진단용이고 로테이션으로
사라지지만, 이것은 질의할 수 있어야 한다("지난주에 이 사람이 뭘 했나").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """로그인 전 요청도 남으므로 nullable. 계정이 지워져도 기록은 남는다."""

    action: Mapped[str] = mapped_column(String(30), index=True)
    """LOGIN / LOGOUT / API. 화면 방문은 SPA 라 서버가 모르므로 API 호출로 갈음한다."""

    path: Mapped[str] = mapped_column(String(300))
    method: Mapped[str] = mapped_column(String(10))
    status_code: Mapped[int] = mapped_column(Integer)

    request_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    """파일 로그와 잇는 끈. 이 값으로 app.log 에서 그 요청의 모든 줄을 찾는다."""

    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AuditEntry(Base):
    """감사 로그 — **무엇이 바뀌었고 누가 승인했는가.**

    위의 접근 로그와 목적이 다르다. 접근 로그는 *"그 화면에서 안 돼요"* 를 재현하는
    지원용이고, 이것은 **무결성**용이다. 보존 기간이 다르므로 처음부터 나눠 둔다.

    ## 모든 변경을 담지 않는다

    담으면 아무도 안 읽는다. **되돌릴 수 없거나 권한이 실린 것**만 남긴다 —
    카드 확정, 삭제, 계정 상태, 기준정보 이름 변경처럼 *"누가 그랬지"* 가 실제로
    문제가 되는 일이다. 값 하나 고친 것까지 남기면 그 안에서 이걸 못 찾는다.

    ## 지워져도 남는다

    `actor_id` 는 `SET NULL` 이고 **이름을 함께 박아 둔다.** 계정이 지워지면 누가
    했는지 모르게 되는데, 그건 감사 로그가 존재하는 이유와 정면으로 어긋난다.
    대상도 같다 — 카드를 지워도 *"그 카드를 누가 언제 확정했는지"* 는 남아야 한다.

    ## 고치지 않는다

    이 표에는 `updated_at` 이 없다. 감사 기록을 고칠 수 있으면 감사가 아니다 —
    쓰는 길만 있고 고치는 길은 API 에도 없다.
    """

    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    action: Mapped[str] = mapped_column(String(60), index=True)
    """`card.published` · `material.deleted` · `account.suspended` 처럼
    `<대상>.<한 일>`. **과거형으로 적는다** — 일어난 일의 기록이지 명령이 아니다."""

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_label: Mapped[str] = mapped_column(String(200))
    """그때의 사람 이름. **계정이 지워져도 남아야 한다.**"""

    target_table: Mapped[str] = mapped_column(String(60), index=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    """**외래키를 안 건다.** 지워진 대상의 기록이 그 삭제 때문에 사라지면 안 된다."""
    target_label: Mapped[str] = mapped_column(String(300))
    """그때의 대상 이름. 카드를 지워도 무엇이었는지는 남는다."""

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    """어느 부서의 일인가. 가시성 판정에 쓴다 — 여기도 FK 를 안 건다."""

    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """`{키: {"before": ..., "after": ...}}`. **바뀐 것만** 담는다.

    통째로 스냅샷하면 표가 커지고 무엇이 바뀌었는지는 오히려 안 보인다."""

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    """사람이 적은 사유. 없을 수 있다 — **없다고 안 남기지는 않는다.**"""

    request_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    """접근 로그·파일 로그와 잇는 끈. 이 값으로 그 요청의 전말을 볼 수 있다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
