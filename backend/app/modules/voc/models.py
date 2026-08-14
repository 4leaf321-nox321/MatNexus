"""VOC — 사용자가 앱 안에서 문제를 제보하는 창구.

비교표: 65는 "GitHub issue 가 사실상의 창구" 인데, **폐쇄망에서는 GitHub 가
창구가 될 수 없다**. 앱 안에 접수 경로가 없으면 문제는 구두로만 오가고 기록이
남지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

VOC_STATUSES = ("open", "in_progress", "resolved")


class VocItem(Base):
    __tablename__ = "voc_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)

    page_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    """접수 당시 보고 있던 화면. "그 화면에서 안 돼요" 를 재현하는 실마리다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
