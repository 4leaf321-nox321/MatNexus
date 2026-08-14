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

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
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
