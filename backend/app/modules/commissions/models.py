"""측정 의뢰 — 「이 시료의 이 물성을 재 달라」 가 기록으로 흐르게.

회의(2026-08-28)의 결론은 「업체가 재 준 물성은 못 올린다 → 측정을 내부에서 한다」
였다. 그런데 플랫폼은 **잰 뒤**부터만 있었다 — 시료 → 시편 → 시험 → 카드. 「누가
무엇을 왜 재 달라고 했고 어디까지 됐나」 는 메일과 구두에 있고 기록이 없었다.

VOC 가 「게시판이고 절차다」 로 자리 잡은 것과 같은 무늬로 푼다: **한 건은 상태를
거쳐 가고, 바뀔 때마다 누가·언제·무슨 말로가 남는다.** 다른 점은 하나 — 의뢰는
**끝이 데이터**다. 항목에 시험이 붙고 결과가 채택되면 진행률이 저절로 오른다.

    draft        작성 중    낸 사람만 본다
    submitted    접수 대기  받는 부서에 알림
    accepted     접수       담당자·예정일        ← 말이 있어야: 언제쯤
    in_progress  시험 중    시험이 붙으면 저절로
    on_hold      보류       시료 미도착·장비 고장  ← 이유를 반드시
    delivered    결과 전달  항목마다 채택 결과가 있을 때 받는 쪽이 옮긴다 ← 어디서 보는지
    closed       완료       낸 사람이 확인
    rejected     반려       안 하기로 함          ← 이유를 반드시

두 부서 사이의 일이다. 시료는 낸 부서 것이고, 받는 부서가 그 시료에 시편을 만들고
시험을 등록한다 — 재료 계층의 가시 범위(전역 + 열린 부서)가 이미 그것을 허용한다.
그래서 데이터는 시료가 있는 자리에 그대로 쌓이고, 의뢰는 그 위에 「왜·누가·언제」
를 잇는다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

STATUSES = (
    "draft",
    "submitted",
    "accepted",
    "in_progress",
    "on_hold",
    "delivered",
    "closed",
    "rejected",
)

STATUS_LABELS: dict[str, str] = {
    "draft": "작성 중",
    "submitted": "접수 대기",
    "accepted": "접수",
    "in_progress": "시험 중",
    "on_hold": "보류",
    "delivered": "결과 전달",
    "closed": "완료",
    "rejected": "반려",
}

#: 받는 부서(측정하는 쪽)가 옮길 수 있는 곳. 받는 부서 멤버면 누구나 — 측정은 팀이
#: 한다. 담당자 한 사람에게 묶으면 그 사람이 자리를 비운 날 의뢰가 선다.
LAB_MOVES: dict[str, tuple[str, ...]] = {
    "submitted": ("accepted", "rejected"),
    "accepted": ("in_progress", "on_hold", "rejected"),
    "in_progress": ("delivered", "on_hold"),
    "on_hold": ("in_progress", "accepted", "rejected"),
    "delivered": ("in_progress",),
    "rejected": ("accepted",),
}

#: 낸 사람이 옮길 수 있는 곳. **결과가 됐다는 말은 받는 쪽이, 됐다는 확인은 낸 사람이.**
#: 부족하면 시험 중으로 되돌리고, 반려에 동의하지 않으면 다시 낸다 — 그때는 이유를.
AUTHOR_MOVES: dict[str, tuple[str, ...]] = {
    "draft": ("submitted",),
    "submitted": ("draft",),
    "delivered": ("closed", "in_progress"),
    "rejected": ("submitted",),
}

#: 이 상태로 옮길 때는 말이 있어야 한다. 「접수」 만 찍힌 건은 언제쯤인지 아무도 모르고,
#: 이유 없는 「보류」·「반려」 는 낸 사람이 되물어야 한다. 「결과 전달」 은 어디서 보는지.
NOTE_REQUIRED = frozenset({"accepted", "on_hold", "delivered", "rejected"})

#: 이 상태에서는 시험을 붙일 수 있다. 접수 전(작성 중·접수 대기)에 붙이면 받지도
#: 않은 일이 진행되는 셈이고, 완료·반려 뒤에 붙이면 닫힌 건이 다시 움직인다.
LINKABLE = frozenset({"accepted", "in_progress", "on_hold", "delivered"})

PRIORITIES = ("normal", "urgent")
PRIORITY_LABELS: dict[str, str] = {"normal": "보통", "urgent": "급함"}

#: 항목이 「무엇으로 받을지」 의 특별한 값 — 카드가 아니라 곡선·처리 결과 그대로.
#: 나머지 값은 카드 블록 키(`matcore.cards.list_blocks`)다.
DELIVERABLE_CURVES = "curves"


class Commission(Base):
    __tablename__ = "commissions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seq: Mapped[int] = mapped_column(Integer, Identity(), unique=True)
    """사람이 부르는 번호 — 「의뢰 12번」. UUID 는 못 부른다."""
    title: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(Text)
    """왜 필요한가 — 해석 과제·판정·비교. 자유 글이다. 과제를 특정하는 키는 적지
    않는다(컴플라이언스 결론, 2026-08-28)."""
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    priority: Mapped[str] = mapped_column(
        String(10), default="normal", server_default="normal"
    )

    requester_workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    """낸 부서 — 낸 사람의 소속 부서."""
    lab_workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    """받는 부서 — 측정하는 곳. 낸 사람이 고른다(측정 조직이 하나가 아니다)."""
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("samples.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    """무엇을 재는가 — 등록된 시료. 시료가 의뢰에 묶여 있으면 지우지 못한다(RESTRICT).

    **비어 있을 수 있다** — 아직 등록 안 된 새 재료를 재 달라는 의뢰(2026-09-14). 그때는
    `material_hint` 가 무엇인지 말하고, 받는 쪽이 재료·시료를 등록한 뒤 여기에 잇는다.
    시험을 붙이려면 시료가 있어야 한다. 둘 중 하나는 있어야 한다(`create`·`update` 가 본다)."""
    material_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    """새 재료의 이름·등급·업체·두께 — 시료가 아직 없을 때 「무엇을」 의 답. 시료가
    이어진 뒤에도 남긴다(무엇을 달라고 했는지의 기록)."""
    sample_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    """시료 전달 — 몇 개, 어떻게, 언제. 자유 글."""
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    """희망 기한."""

    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    """받는 부서의 담당자. 접수 때 정한다. 없어도 받는 부서 멤버는 다 옮길 수 있다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    """지금 상태가 된 때. 목록의 「최근 처리」 — 이벤트를 건마다 세면 N+1 이다."""
    status_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CommissionItem(Base):
    """의뢰 항목 — 「이 시험 종류를 이 조건으로 n 개」.

    진행률은 저장하지 않는다. 이 항목에 붙은 시험(`TestRun.commission_item_id`) 가운데
    결과가 채택된 것의 수 / `count` 로 센다 — 저장해 두면 시험이 지워졌을 때 틀린 채
    남는다.
    """

    __tablename__ = "commission_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    commission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("commissions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    test_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("test_types.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    """시험 종류. **비어 있을 수 있다** — 「이 물성을 재 달라」 만 있고 무슨 시험으로 잴지는
    받는 쪽이 정하는 의뢰(2026-09-14). 그때는 `property_hint` 가 무엇을 재는지 말하고,
    받는 쪽이 종류를 정한 뒤 시험을 붙인다. 둘 중 하나는 있어야 한다."""
    property_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    """무엇을 재는가 — 시험 종류가 미정일 때. 「고온 탄성계수」 같은 물성 이름."""
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """시험 종류의 조건 칸(`TestConditionField`)으로 적은 조건 — **SI 로 저장**, 시험
    등록과 같은 규칙(`shared.conditions.normalize_conditions`)."""
    input_units: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """무엇으로 입력했는지 — 화면이 그 단위로 되돌려 보인다."""
    orientations: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """RD·TD·45 … 비어 있으면 방향 무관."""
    count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    """시편 수."""
    deliverable: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """무엇으로 받을지 — 카드 블록 키(hardening·rheology…) 또는 `curves`. 비면 미정."""
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CommissionEvent(Base):
    """한 건에 일어난 일 하나 — 등록·상태 변경·댓글·시험 연결.

    `from_status == to_status` 면 상태는 그대로고 말만 보탠 것이다. 등록은
    `from_status` 가 비어 있다. 지우지 않는다 — 절차의 기록이 이것이다.
    """

    __tablename__ = "commission_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    commission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("commissions.id", ondelete="CASCADE"), index=True
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
