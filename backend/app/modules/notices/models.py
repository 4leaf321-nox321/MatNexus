"""공지 — 배포 없이 안내를 갱신하는 유일한 수단.

비교표가 65의 공백으로 짚은 항목이다. 공지가 없으면 안내 문구 하나를 바꾸려고
새 버전을 배포해야 하고, 폐쇄망에서는 그 왕복이 며칠이 된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)

    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """초안으로 두었다가 발행한다. 쓰는 도중에 사람들에게 뜨면 곤란하다."""

    is_popup: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """켜면 읽지 않은 사람에게 한 번 뜬다. 중요한 것만 켠다 — 전부 팝업이면
    아무도 읽지 않는다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    seed_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    """**배포에 실려 온 안내**면 그 파일 이름(2026-09-12). 새 기능은 코드와 함께 도착하는데
    그것을 알리는 글은 사람이 따로 써야 했고, 그러면 언젠가 아무도 안 쓴다. 이제
    `seeds/notices/*.md` 가 배포마다 **초안**으로 들어오고(`import_notices.py`), 관리자가
    읽고 발행한다. 같은 키는 두 번 안 들어온다 — 운영에서 고친 글을 덮지 않는다. 지운 글도
    다시 안 들어온다 — 넣은 키는 `NoticeSeedKey` 가 따로 기억한다."""


class NoticeSeedKey(Base):
    """**넣은 적이 있는 씨앗 키**(2026-11-15) — 공지를 지워도 남는다.

    `import_notices.py` 는 「넣었나」 를 `notices.seed_key` 행으로만 봤다. 관리자가 초안을
    지우면 행이 사라지니 다음 배포가 그 씨앗을 또 초안으로 넣었다(씨앗 약 100개 — 지운 것이
    배포마다 되살아났다). 넣을 때 키를 여기 적고, 넣을지는 여기를 본다. 공지 행과 묶지
    않는다(FK 없음) — 공지가 사라져도 「넣었다」 는 사실은 남아야 한다.
    """

    __tablename__ = "notice_seed_keys"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NoticeRead(Base):
    """누가 어떤 공지를 읽었는가. 팝업을 한 번만 띄우기 위한 것."""

    __tablename__ = "notice_reads"
    __table_args__ = (UniqueConstraint("notice_id", "user_id", name="uq_notice_reads_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notice_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("notices.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
