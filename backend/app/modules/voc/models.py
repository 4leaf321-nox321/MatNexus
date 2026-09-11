"""VOC — 사용자가 앱 안에서 문제를 제보하는 창구.

비교표: 65는 "GitHub issue 가 사실상의 창구" 인데, **폐쇄망에서는 GitHub 가
창구가 될 수 없다**. 앱 안에 접수 경로가 없으면 문제는 구두로만 오가고 기록이
남지 않는다.

## 게시판이고 절차다 (2026-09-11)

처음에는 「낸 사람과 관리자만 보는 카드 + 답변 한 줄」 이었다. 그러면 같은 문제를
여럿이 따로 내고, 무엇이 고쳐졌는지는 낸 사람만 알고, 「접수됐나 → 보고 있나 →
됐나」 가 답변 한 줄에 뭉쳐 있어 중간 상태가 없었다.

그래서 **로그인한 사람은 다 보는 게시판**이고, 한 건은 **상태를 거쳐 간다**:

    open        등록      낸 상태
    accepted    접수      관리자가 보고 할 것으로 정함
    in_progress 처리 중
    resolved    해결      관리자가 조치를 적음  ← 무엇을 했는지 반드시 적는다
    closed      종료      낸 사람이 확인(또는 관리자)
    rejected    반려      안 하기로 함        ← 이유를 반드시 적는다

상태가 바뀔 때마다 **누가·언제·무슨 말로** 바꿨는지 `voc_events` 에 남는다.
그것이 곧 절차의 기록이고, 답변 한 줄이 아니라 그 줄들이 화면에 흐른다.

`reply`·`replied_*` 는 옛 자리다. 이관 때 `voc_events` 로 옮겼고 읽는 쪽은
더 안 본다 — 한 릴리스 뒤에 지운다(ADR 0010 Expand).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

VOC_STATUSES = ("open", "accepted", "in_progress", "resolved", "closed", "rejected")

VOC_STATUS_LABELS: dict[str, str] = {
    "open": "등록",
    "accepted": "접수",
    "in_progress": "처리 중",
    "resolved": "해결",
    "closed": "종료",
    "rejected": "반려",
}

#: 관리자가 옮길 수 있는 곳. 같은 상태로 옮기는 것은 상태 변경이 아니라 댓글이다.
ADMIN_MOVES: dict[str, tuple[str, ...]] = {
    "open": ("accepted", "in_progress", "resolved", "rejected"),
    "accepted": ("in_progress", "resolved", "rejected"),
    "in_progress": ("resolved", "rejected", "accepted"),
    "resolved": ("closed", "in_progress"),
    "closed": ("in_progress",),
    "rejected": ("accepted", "in_progress"),
}

#: 낸 사람이 옮길 수 있는 곳. **해결됐다는 말은 관리자가, 됐다는 확인은 낸 사람이.**
#: 반려·해결에 동의하지 않으면 다시 연다 — 그때는 이유를 적는다.
AUTHOR_MOVES: dict[str, tuple[str, ...]] = {
    "resolved": ("closed", "open"),
    "rejected": ("open",),
    "closed": ("open",),
}

#: 이 상태로 옮길 때는 말이 있어야 한다. 「해결」 만 찍힌 건은 무엇이 바뀌었는지
#: 아무도 모르고, 이유 없는 「반려」 는 낸 사람이 다시 낼 수밖에 없다.
NOTE_REQUIRED = frozenset({"resolved", "rejected", "open"})


class VocItem(Base):
    __tablename__ = "voc_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seq: Mapped[int] = mapped_column(Integer, Identity(), unique=True)
    """게시판 번호. 사람이 「VOC 12번」 이라고 부르는 손잡이 — UUID 는 못 부른다.
    이관 때 등록 순서로 매겼고, 새 건은 시퀀스가 준다."""
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

    status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    """지금 상태가 된 때. 목록이 「최근 처리」 열을 이것으로 그린다 — 이벤트를
    건마다 세면 목록이 N+1 이 된다."""
    status_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── 옛 자리. 읽지 않는다 — 한 릴리스 뒤에 지운다. ──────────────────────────
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VocEvent(Base):
    """한 건에 일어난 일 하나 — 등록·상태 변경·댓글.

    `from_status == to_status` 면 상태는 그대로고 말만 보탠 것(댓글)이다. 등록은
    `from_status` 가 비어 있다. 지우지 않는다 — 절차의 기록이 이것이다.
    """

    __tablename__ = "voc_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("voc_items.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
