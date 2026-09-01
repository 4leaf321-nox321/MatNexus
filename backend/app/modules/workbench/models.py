"""워크벤치 — **가로지르는 일을 담아 두는 자리**(ADR 0024·0025).

한 대상에 매달린 일은 그 대상의 화면에 남는다. 여러 대상을 가로지르는 일만 여기
온다 — 시험 여덟 건을 한 번에 처리하고, 재료 셋의 카드를 모아 한 덱으로 내보내는 일.

## 두 표뿐이다

    WorkbenchRun    무엇을 하는 중인가 — 목적(`workflow_key`)과 진행(`steps`)
    WorkbenchItem   무엇을 들고 있는가 — 담은 대상들

## 담은 대상에 **외래키를 안 건다**

`target_id` 는 그냥 UUID 다. 외래키를 걸면 두 갈래로 나쁘다(ADR 0025) —

    CASCADE 면    시험을 지웠을 때 담긴 줄이 조용히 사라진다.
                 「내가 담았던 여덟 건이 왜 일곱이지」 에 답이 없다
    RESTRICT 면   **담겼다는 이유로 시험을 못 지운다.** 담아 두는 것은 메모지
                 소유가 아니다

없어진 대상은 「사라졌습니다」 로 그 줄만 표시하고, 작업은 계속 민다. 대신
`shared/dependents.py` 에 등록해 **지우려는 사람이 미리 본다** — 막지 않고 말해 준다.

## 진행(`steps`)은 자유 모양이다

단계가 무엇이고 무엇으로 완료를 판정하는지는 **화면이 안다**(ADR 0025). 서버가 그것을
알면 화면을 고칠 때마다 마이그레이션이 붙고, 「진행 3단계」 가 무슨 뜻인지가 배포마다
달라진다.

못 읽는 모양이 오면(정의가 바뀌었다) 화면이 **처음부터 다시 시작하라고 말한다** —
반쯤 읽어 이어서 미는 것이 더 나쁘다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base
from app.shared import dependents

#: 담을 수 있는 것. **늘어나는 목록이다** — 새 워크플로가 새 종류를 담을 수 있다.
ITEM_KINDS = ("test_run", "material", "card")

#: 작업의 상태. `버림` 도 지우지 않고 남긴다 — 무엇을 하다 말았는지가 기록이다.
RUN_STATUSES = ("running", "finished", "dropped")


class WorkbenchRun(Base):
    """작업 하나 — **목적과 진행**."""

    __tablename__ = "workbench_runs"
    __table_args__ = (
        # 목록이 「내 부서의 진행 중인 것」 을 먼저 보여 준다.
        Index("ix_workbench_runs_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True
    )
    """**부서 안에서 공유한다.** 만든 사람만 보면 「어제 하던 것을 오늘 다른
    사람이」 가 안 된다. 누가 무엇을 밀었는지는 감사 기록이 답한다."""

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    """시작한 사람. 계정을 지워도 작업은 남는다 — 그래서 nullable 이다."""

    workflow_key: Mapped[str] = mapped_column(String(50), index=True)
    """어떤 일인가(`viscoelastic_set`·`analysis_deck` …). **뜻은 화면이 안다.**"""

    title: Mapped[str] = mapped_column(String(200))
    """사람이 알아볼 이름. 「EPDM 도어씰 2026-09」 처럼."""

    status: Mapped[str] = mapped_column(
        String(20), default="running", server_default="running", index=True
    )

    steps: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """어디까지 밀었나. 모양은 화면이 정한다 — 서버는 담아만 둔다."""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkbenchItem(Base):
    """작업이 들고 있는 것 하나 — **가리키기만 한다.**"""

    __tablename__ = "workbench_items"
    __table_args__ = (
        # 같은 것을 두 번 담아도 한 번만. 두 번 담기는 실수이지 뜻이 아니다.
        Index("uq_workbench_items", "run_id", "kind", "target_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workbench_runs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    """`test_run` | `material` | `card`."""

    target_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    """**외래키가 아니다.** 위 머리말의 이유다 — 지워질 수 있고, 지워졌다는 사실이
    보여야 한다."""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    """왜 담았는지. 「TD 만 쓸 것」 같은 메모."""

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


#: 담긴 종류 ↔ 그 대상이 사는 표. 의존성 검사가 이 표를 거꾸로 읽는다.
#:
#: **모델 옆에 둔다.** 검사는 `app.all_models` 가 부를 때 등록돼야 하는데, 그것이
#: 부르는 것은 모델 모듈이다 — 서비스에 두면 그 모듈을 부른 경로에서만 등록되고,
#: 스크립트로 지울 때는 조용히 빠진다.
TABLE_KINDS = {"test_runs": "test_run", "materials": "material", "property_cards": "card"}


def basket_references(db: Session, table: str, pk: object) -> list[dependents.Reference]:
    """**바구니에 담겼다는 사실을 지우려는 사람에게 알린다.**

    담은 대상에는 외래키를 안 건다(ADR 0025) — 걸면 담겼다는 이유로 못 지우게 되거나
    (RESTRICT), 지웠을 때 담긴 줄이 조용히 사라진다(CASCADE). 그래서 FK 를 훑는 자동
    수집에 안 잡히고, 여기서 손으로 보탠다.

    **막지 않는다.** `on_delete="SET NULL"` 로 적는 것은 「지워도 되고, 그 줄은
    사라진 것으로 표시된다」 는 뜻이다 — 실제 동작과 같은 말이다.
    """
    kind = TABLE_KINDS.get(table)
    if kind is None:
        return []
    count = (
        db.scalar(
            select(func.count())
            .select_from(WorkbenchItem)
            .where(WorkbenchItem.kind == kind, WorkbenchItem.target_id == pk)
        )
        or 0
    )
    if not count:
        return []
    return [
        dependents.Reference(
            table="workbench_items", column="target_id", count=count, on_delete="SET NULL"
        )
    ]


dependents.EXTRA_CHECKS.append(basket_references)
