"""감사 로그 읽기 — **쓰는 길은 여기 없다.**

`POST`·`PATCH`·`DELETE` 가 하나도 없다. 감사 기록을 API 로 만들 수 있으면 그것은
감사가 아니다 — 기록은 **변경이 일어난 그 트랜잭션 안에서만** 생긴다
(`app/shared/audit.py`).

## 누가 보나

시스템 관리자는 전부, 부서 관리자는 자기 부서 것을. **일반 사용자는 못 본다** —
"누가 무엇을 했나" 는 그 자체로 사람에 대한 정보다.

**다만 제 자료에 일어난 일은 누구나 본다**(`/audit/mine`, 2026-09-25). 고칠 권한이 등록자
밖으로 넓어진 뒤(ADR 0035) 「내 자료에 무슨 일이 있었나」 는 등록자의 물음이다 — 제 자료의
기록만 열고, 남의 것은 여전히 못 본다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.audit.schemas import AuditEntryOut
from app.modules.workspaces.models import WorkspaceMember
from app.shared.auth import current_user
from app.shared.errors import Forbidden
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/audit", tags=["audit"])


def _managed(db: Session, user: User) -> list[uuid.UUID]:
    """이 사람이 관리자인 부서."""
    rows = db.scalars(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user.id, WorkspaceMember.role == "manager"
        )
    )
    return list(rows)


@router.get("/mine", response_model=Page[AuditEntryOut])
def my_data_entries(
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[AuditEntryOut]:
    """**내 자료에 일어난 일** — 등록자가 묻는 자리(ADR 0035 남은 것). 최근 것부터.

    기록마다 「누구의 자료였나」(`subject_id`)가 적혀 있고, 그것이 나인 것만 준다. 남이 고친 것
    (「남의 자료 고침」 — 근거와 함께) · 지운 것 · 확정하거나 내린 것 · 넘긴 것이 여기 선다.

    **내가 손으로 한 일은 뺀다** — 내가 한 일은 내가 안다. 다만 **내 토큰으로 AI 가 한 일은
    남긴다**(`client`) — 그것은 내가 손으로 한 일이 아니다.
    """
    query = select(AuditEntry).where(
        AuditEntry.subject_id == user.id,
        or_(
            AuditEntry.actor_id.is_(None),
            AuditEntry.actor_id != user.id,
            AuditEntry.client != "",
        ),
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    rows = db.scalars(query.order_by(AuditEntry.created_at.desc()).limit(size).offset(offset))
    return Page(
        items=[AuditEntryOut.model_validate(row, from_attributes=True) for row in rows],
        total=int(total),
        limit=size,
        offset=offset,
    )


@router.get("", response_model=list[AuditEntryOut])
def list_entries(
    action: str | None = Query(default=None),
    client: str | None = Query(
        default=None,
        description="`mcp` 처럼 들어온 길로 거른다. `web` 이면 화면에서 한 것만.",
    ),
    target_id: uuid.UUID | None = Query(default=None),
    workspace_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AuditEntryOut]:
    """감사 기록. **최근 것부터.**

    부서 관리자는 자기 부서 것만 본다. 부서가 없는 기록(계정처럼 전사에 걸린
    일)은 **시스템 관리자만** 본다 — 어느 부서 소관인지 정할 수 없는 일이라
    부서 관리자에게 보이면 소관 밖을 보는 것이 된다.
    """
    query = select(AuditEntry).order_by(AuditEntry.created_at.desc())

    if not user.is_system_admin:
        managed = _managed(db, user)
        if not managed:
            raise Forbidden(
                "MNX-AUDIT-0001",
                "변경 이력은 시스템 관리자나 부서 관리자만 볼 수 있습니다.",
            )
        query = query.where(AuditEntry.workspace_id.in_(managed))

    if action:
        query = query.where(AuditEntry.action == action)
    if client:
        # **「화면에서 한 것」 을 고르는 길도 준다.** 빈 문자열은 질의 인자로 넘기기
        # 나빠서 `web` 이라는 말로 받는다.
        query = query.where(
            AuditEntry.client == ("" if client == "web" else client.strip().lower())
        )
    if target_id:
        query = query.where(AuditEntry.target_id == target_id)
    if workspace_id:
        query = query.where(AuditEntry.workspace_id == workspace_id)

    # **서버가 상한을 강제한다.** 목록 엔드포인트의 규칙이다.
    rows = db.scalars(query.limit(clamp_limit(limit)))
    return [AuditEntryOut.model_validate(row, from_attributes=True) for row in rows]
