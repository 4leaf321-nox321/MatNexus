"""외부 연동 설정 — **바깥 시스템 하나에 한 줄.**

TestScope 가 장비 자산(보유 장비 · 교정 · 기종 사양)의 정본이 됐다(2026-10-23). MatNexus 가
그것을 읽으려면 주소와 읽기 토큰이 있어야 하는데, `.env` 에 두면 시스템 관리자가 서버 파일을
고치고 서비스를 다시 띄워야 바뀐다. 그래서 **화면에서 넣고 DB 에 둔다**(사용자 요청).

토큰은 봉인해 둔다(`app.shared.secretbox`). 화면 · API 는 「설정됨」 만 말한다 — 토큰을 다시
보여 주면 그 화면을 본 사람 누구나 TestScope 를 그 토큰 주인의 눈으로 읽는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 붙일 수 있는 바깥 시스템과 화면 이름. 늘리려면 여기에 한 줄 — 연결 확인은 `services` 에.
SYSTEMS = {"testscope": "TestScope"}


class IntegrationConnection(Base):
    """바깥 시스템 하나의 연결 — 주소 · 봉인한 토큰 · 마지막 연결 확인."""

    __tablename__ = "integration_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    system: Mapped[str] = mapped_column(String(40), unique=True)
    """`testscope` — 바깥 시스템의 이름. 한 시스템에 한 줄이다."""
    base_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    """**이 서버가** 부르는 API 주소(`http://127.0.0.1:8020/api`). 같은 서버면 localhost."""
    web_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    """**사람이** 여는 화면 주소(`http://testscope-서버:8020`) — 링크에 쓴다. 비우면 API
    주소에서 `/api` 를 뗀 것. 서버끼리는 localhost 로 닿아도 사람의 브라우저는 그 주소로 못
    간다."""
    token_sealed: Mapped[str] = mapped_column(Text, default="", server_default="")
    token_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """마지막으로 「연결 확인」 을 누른 때."""
    check_ok: Mapped[bool | None] = mapped_column(Boolean)
    check_message: Mapped[str | None] = mapped_column(Text)
    """그때의 결과 한 줄 — 「연결됨 — TestScope 사용자 …」 · 「토큰이 거절됨」 …"""
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
