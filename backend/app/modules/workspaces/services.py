"""부서 로직 — 생성·보관, 멤버와 역할.

**부서를 지우지 않는다.** `is_active=false` 로 보관만 한다. 부서에는 시험 데이터가
매달리게 되고(Phase 2), 무엇이 그 부서를 참조하는지 답할 수 있게 된 뒤에야
삭제를 논할 수 있다(의존성 레지스트리, 1-2). 그 전까지 삭제 버튼을 만들면
"지웠더니 데이터가 사라졌다"가 된다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.modules.workspaces.schemas import MemberOut, WorkspaceOption, WorkspaceOut
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.permissions import membership_of, workspace_by_slug

ROLES = ("member", "manager")


def _member_count(db: Session, workspace_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
        or 0
    )


def workspace_out(db: Session, workspace: Workspace, viewer: User) -> WorkspaceOut:
    membership = membership_of(db, workspace_id=workspace.id, user_id=viewer.id)
    return WorkspaceOut(
        id=workspace.id,
        slug=workspace.slug,
        name=workspace.name,
        kind=workspace.kind,
        is_active=workspace.is_active,
        created_at=workspace.created_at,
        member_count=_member_count(db, workspace.id),
        my_role=membership.role if membership else None,
    )


def options(db: Session) -> list[WorkspaceOption]:
    """가입 신청용 부서 목록. 인증 없이 나가므로 이름만 담는다."""
    rows = db.scalars(
        select(Workspace)
        .where(Workspace.is_active.is_(True), Workspace.kind == "org")
        .order_by(Workspace.name)
    )
    return [WorkspaceOption(slug=w.slug, name=w.name) for w in rows]


def list_for(db: Session, viewer: User, *, all_workspaces: bool) -> list[WorkspaceOut]:
    """`all_workspaces` 는 시스템 관리자만 쓸 수 있다(라우터가 판정)."""
    query = select(Workspace).order_by(Workspace.name)
    if not all_workspaces:
        query = query.join(
            WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id
        ).where(WorkspaceMember.user_id == viewer.id)
    return [workspace_out(db, w, viewer) for w in db.scalars(query)]


def create(db: Session, *, slug: str, name: str, creator: User) -> Workspace:
    if db.scalar(select(Workspace).where(Workspace.slug == slug)) is not None:
        raise Conflict("MNX-WORKSPACES-0004", "이미 사용 중인 부서 주소입니다.")

    workspace = Workspace(slug=slug, name=name.strip(), kind="org")
    db.add(workspace)
    db.flush()
    # 만든 사람을 관리자로 넣는다. manager 가 0명인 부서는 아무도 멤버를 넣을 수
    # 없어 태어나자마자 잠긴다.
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=creator.id, role="manager"))
    db.commit()
    return workspace


def update(db: Session, *, slug: str, name: str | None, is_active: bool | None) -> Workspace:
    workspace = workspace_by_slug(db, slug)
    if name is not None:
        workspace.name = name.strip()
    if is_active is not None:
        workspace.is_active = is_active
    db.commit()
    return workspace


# --- 멤버 --------------------------------------------------------------------


def members(db: Session, *, workspace: Workspace) -> list[MemberOut]:
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace.id)
        .order_by(User.display_name)
    ).all()
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            role=member.role,
            joined_at=member.created_at,
        )
        for member, user in rows
    ]


def add_member(db: Session, *, workspace: Workspace, email: str, role: str) -> MemberOut:
    _check_role(role)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise NotFound("MNX-WORKSPACES-0005", "계정을 찾을 수 없습니다.")
    if user.status == "pending":
        # 승인 절차를 우회해 부서에 넣는 길을 막는다.
        raise Conflict(
            "MNX-WORKSPACES-0006", "승인 대기 중인 계정입니다. 계정 관리에서 먼저 승인하세요."
        )

    existing = membership_of(db, workspace_id=workspace.id, user_id=user.id)
    if existing is not None:
        raise Conflict("MNX-WORKSPACES-0007", "이미 이 부서의 멤버입니다.")

    member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role)
    db.add(member)
    if user.home_workspace_id is None:
        user.home_workspace_id = workspace.id
    db.commit()
    db.refresh(member)
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        role=member.role,
        joined_at=member.created_at,
    )


def set_role(db: Session, *, workspace: Workspace, user_id: uuid.UUID, role: str) -> MemberOut:
    _check_role(role)
    member = membership_of(db, workspace_id=workspace.id, user_id=user_id)
    if member is None:
        raise NotFound("MNX-WORKSPACES-0008", "이 부서의 멤버가 아닙니다.")

    if member.role == "manager" and role != "manager":
        _ensure_another_manager(db, workspace=workspace, excluding=user_id)

    member.role = role
    db.commit()
    user = db.get(User, user_id)
    assert user is not None
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        role=member.role,
        joined_at=member.created_at,
    )


def remove_member(db: Session, *, workspace: Workspace, user_id: uuid.UUID) -> None:
    member = membership_of(db, workspace_id=workspace.id, user_id=user_id)
    if member is None:
        raise NotFound("MNX-WORKSPACES-0008", "이 부서의 멤버가 아닙니다.")
    if member.role == "manager":
        _ensure_another_manager(db, workspace=workspace, excluding=user_id)

    user = db.get(User, user_id)
    if user is not None and user.home_workspace_id == workspace.id:
        # 소속을 남은 부서 중 하나로 옮긴다. 비워 두면 로그인 후 갈 곳이 없다.
        remaining = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id != workspace.id,
            )
        )
        user.home_workspace_id = remaining.workspace_id if remaining else None

    db.delete(member)
    db.commit()


def _ensure_another_manager(
    db: Session, *, workspace: Workspace, excluding: uuid.UUID
) -> None:
    """마지막 관리자를 잃지 않게 한다.

    manager 가 0명이 되면 그 부서는 멤버를 넣을 수도 뺄 수도 없어, 시스템 관리자가
    개입해야만 풀린다. 그런 상태를 만들 수 있는 버튼은 두지 않는다.
    """
    other = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.role == "manager",
            WorkspaceMember.user_id != excluding,
        )
    )
    if other is None:
        raise Conflict(
            "MNX-WORKSPACES-0009",
            "부서에 관리자가 최소 한 명 있어야 합니다. 다른 사람을 먼저 관리자로 지정하세요.",
        )


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise AppError("MNX-WORKSPACES-0010", "허용되지 않는 역할입니다.", status=400)
