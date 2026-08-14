"""권한 판정 — 부서 스코프.

**가시성·수정 권한을 각 쿼리에 흩뿌리지 않고 여기서만 판정한다.** 65가 RLS로
DB에 강제를 걸어 얻은 이점이 "앱에 버그가 있어도 데이터가 새지 않는다"였는데,
우리는 아직 앱 레벨이므로 최소한 판정 지점이라도 하나여야 한다. 나중에 RLS를
도입할 때도 이 함수들이 정책의 대응물이 된다(개발계획 §10).

시스템 역할과 부서 역할은 다른 축이다(D12).
  - `is_system_admin` : 전사. 계정·부서 자체를 만들고 지운다
  - 부서 `manager`    : 그 부서 안에서만. 멤버와 역할을 관리한다
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared.errors import Forbidden, NotFound


def workspace_by_slug(db: Session, slug: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise NotFound("MNX-WORKSPACES-0001", f"부서를 찾을 수 없습니다: {slug}")
    return workspace


def membership_of(
    db: Session, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember | None:
    return db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )


def require_member(db: Session, *, workspace: Workspace, user: User) -> None:
    """그 부서를 볼 수 있는가. 시스템 관리자는 모든 부서를 본다."""
    if user.is_system_admin:
        return
    if membership_of(db, workspace_id=workspace.id, user_id=user.id) is None:
        raise Forbidden("MNX-WORKSPACES-0002", "이 부서에 접근할 권한이 없습니다.")


def require_manager(db: Session, *, workspace: Workspace, user: User) -> None:
    """그 부서의 멤버·역할을 바꿀 수 있는가."""
    if user.is_system_admin:
        return
    membership = membership_of(db, workspace_id=workspace.id, user_id=user.id)
    if membership is None or membership.role != "manager":
        raise Forbidden("MNX-WORKSPACES-0003", "부서 관리자만 할 수 있습니다.")
