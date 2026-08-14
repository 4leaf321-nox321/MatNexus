"""계정 로직 — 가입 신청, 승인·거절, 상태 변경, 임시 비밀번호.

**셀프 가입 + 관리자 승인**을 쓴다. 폐쇄망 사내망이라 가입 자체의 위험은 낮지만
아무나 만든 계정이 바로 데이터에 접근하면 안 되므로, 승인이 관문이다.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.accounts.schemas import AccountOut
from app.modules.auth import security
from app.modules.auth.models import RefreshToken
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared.errors import AppError, Conflict, NotFound


def _now() -> datetime:
    return datetime.now(UTC)


def _workspace_by_slug(db: Session, slug: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise NotFound("MNX-ACCOUNTS-0001", f"부서를 찾을 수 없습니다: {slug}")
    return workspace


def account_out(db: Session, user: User) -> AccountOut:
    rows = db.execute(
        select(Workspace.slug)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name)
    ).all()

    home = db.get(Workspace, user.home_workspace_id) if user.home_workspace_id else None
    requested = (
        db.get(Workspace, user.requested_workspace_id) if user.requested_workspace_id else None
    )

    return AccountOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        is_system_admin=user.is_system_admin,
        must_change_password=user.must_change_password,
        home_workspace_slug=home.slug if home else None,
        requested_workspace_slug=requested.slug if requested else None,
        memberships=[row[0] for row in rows],
        created_at=user.created_at,
        decided_at=user.decided_at,
        decision_note=user.decision_note,
    )


# --- 가입 ---------------------------------------------------------------------


def signup(
    db: Session, *, email: str, password: str, display_name: str, workspace_slug: str
) -> User:
    normalized = email.strip().lower()
    workspace = _workspace_by_slug(db, workspace_slug)

    if db.scalar(select(User).where(User.email == normalized)) is not None:
        # 이미 있는 아이디인지 알려 준다. 폐쇄망 사내 시스템이라 아이디 존재 여부가
        # 민감하지 않고, 모호하게 굴면 신청자가 무엇을 고쳐야 할지 알 수 없다.
        raise Conflict("MNX-ACCOUNTS-0002", "이미 사용 중인 아이디입니다.")

    user = User(
        email=normalized,
        password_hash=security.hash_password(password),
        display_name=display_name.strip(),
        status="pending",
        requested_workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    return user


def approve(
    db: Session, *, user_id: uuid.UUID, decided_by: User, workspace_slug: str | None, role: str
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")
    if user.status != "pending":
        raise Conflict("MNX-ACCOUNTS-0004", "승인 대기 상태가 아닙니다.")

    slug = workspace_slug
    if slug is None:
        requested = (
            db.get(Workspace, user.requested_workspace_id)
            if user.requested_workspace_id
            else None
        )
        if requested is None:
            raise AppError(
                "MNX-ACCOUNTS-0005",
                "배정할 부서를 지정해야 합니다 (신청 부서가 없습니다).",
                status=400,
            )
        slug = requested.slug

    workspace = _workspace_by_slug(db, slug)
    _ensure_membership(db, workspace=workspace, user=user, role=role)

    user.status = "active"
    user.home_workspace_id = workspace.id
    user.decided_at = _now()
    user.decided_by_id = decided_by.id
    user.decision_note = None
    db.commit()
    return user


def reject(db: Session, *, user_id: uuid.UUID, decided_by: User, note: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")
    if user.status != "pending":
        raise Conflict("MNX-ACCOUNTS-0004", "승인 대기 상태가 아닙니다.")

    # 지우지 않고 정지로 남긴다. 같은 사람이 다시 신청했을 때 이전 판단을 볼 수 있고,
    # 아이디를 재사용하려는 시도도 드러난다.
    user.status = "suspended"
    user.decided_at = _now()
    user.decided_by_id = decided_by.id
    user.decision_note = note.strip()
    db.commit()
    return user


# --- 관리자 직접 생성 ----------------------------------------------------------


def create_account(
    db: Session,
    *,
    email: str,
    display_name: str,
    workspace_slug: str,
    role: str,
    is_system_admin: bool,
    created_by: User,
) -> tuple[User, str]:
    """(계정, 임시 비밀번호). 임시 비밀번호는 호출부가 한 번만 노출한다."""
    normalized = email.strip().lower()
    if db.scalar(select(User).where(User.email == normalized)) is not None:
        raise Conflict("MNX-ACCOUNTS-0002", "이미 사용 중인 아이디입니다.")

    workspace = _workspace_by_slug(db, workspace_slug)
    temporary = secrets.token_urlsafe(9)

    user = User(
        email=normalized,
        password_hash=security.hash_password(temporary),
        display_name=display_name.strip(),
        status="active",
        is_system_admin=is_system_admin,
        must_change_password=True,  # 임시 비밀번호가 그대로 남지 않게
        home_workspace_id=workspace.id,
        decided_at=_now(),
        decided_by_id=created_by.id,
    )
    db.add(user)
    db.flush()
    _ensure_membership(db, workspace=workspace, user=user, role=role)
    db.commit()
    return user, temporary


def reset_password(db: Session, *, user_id: uuid.UUID) -> tuple[User, str]:
    """관리자 중개 비밀번호 재설정.

    SMTP 가 없어 셀프 링크를 보낼 수 없다. 관리자가 임시 비밀번호를 발급하고
    화면에서 읽어 전달한다 — 비교표가 폐쇄망에 권한 방식이다.
    """
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")

    temporary = secrets.token_urlsafe(9)
    user.password_hash = security.hash_password(temporary)
    user.must_change_password = True

    # 재설정 이유가 유출일 수 있으므로 기존 세션을 전부 끊는다.
    for token in db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ):
        token.revoked_at = _now()

    db.commit()
    return user, temporary


# --- 상태 --------------------------------------------------------------------


def set_status(db: Session, *, user_id: uuid.UUID, status: str, actor: User) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")
    if user.id == actor.id:
        raise Conflict("MNX-ACCOUNTS-0006", "자기 계정의 상태는 바꿀 수 없습니다.")
    if status not in ("active", "suspended"):
        raise AppError("MNX-ACCOUNTS-0007", "허용되지 않는 상태입니다.", status=400)

    user.status = status
    if status == "suspended":
        # 접근을 즉시 끊는다. 세션이 남아 있으면 정지가 무의미하다.
        for token in db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        ):
            token.revoked_at = _now()
    db.commit()
    return user


def list_accounts(db: Session, *, status: str | None, limit: int, offset: int) -> list[User]:
    query = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    if status:
        query = query.where(User.status == status)
    return list(db.scalars(query))


def _ensure_membership(db: Session, *, workspace: Workspace, user: User, role: str) -> None:
    if role not in ("member", "manager"):
        raise AppError("MNX-ACCOUNTS-0008", "허용되지 않는 역할입니다.", status=400)

    existing = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id
        )
    )
    if existing is None:
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    else:
        existing.role = role
