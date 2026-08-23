"""감사 로그 읽기 — **쓰는 길은 여기 없다.**

`POST`·`PATCH`·`DELETE` 가 하나도 없다. 감사 기록을 API 로 만들 수 있으면 그것은
감사가 아니다 — 기록은 **변경이 일어난 그 트랜잭션 안에서만** 생긴다
(`app/shared/audit.py`).

## 누가 보나

시스템 관리자는 전부, 부서 관리자는 자기 부서 것을. **일반 사용자는 못 본다** —
"누가 무엇을 했나" 는 그 자체로 사람에 대한 정보다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.audit.schemas import AuditEntryOut
from app.modules.workspaces.models import WorkspaceMember
from app.shared.auth import current_user
from app.shared.errors import Forbidden
from app.shared.pagination import clamp_limit

router = APIRouter(prefix="/audit", tags=["audit"])


def _managed(db: Session, user: User) -> list[uuid.UUID]:
    """이 사람이 관리자인 부서."""
    rows = db.scalars(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user.id, WorkspaceMember.role == "manager"
        )
    )
    return list(rows)


@router.get("", response_model=list[AuditEntryOut])
def list_entries(
    action: str | None = Query(default=None),
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
                "감사 기록은 시스템 관리자나 부서 관리자만 볼 수 있습니다.",
            )
        query = query.where(AuditEntry.workspace_id.in_(managed))

    if action:
        query = query.where(AuditEntry.action == action)
    if target_id:
        query = query.where(AuditEntry.target_id == target_id)
    if workspace_id:
        query = query.where(AuditEntry.workspace_id == workspace_id)

    # **서버가 상한을 강제한다.** 목록 엔드포인트의 규칙이다.
    rows = db.scalars(query.limit(clamp_limit(limit)))
    return [AuditEntryOut.model_validate(row, from_attributes=True) for row in rows]
