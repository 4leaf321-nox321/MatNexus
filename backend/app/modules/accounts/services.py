"""계정 로직 — 가입 신청, 승인·거절, 상태 변경, 임시 비밀번호.

**셀프 가입 + 관리자 승인**을 쓴다. 폐쇄망 사내망이라 가입 자체의 위험은 낮지만
아무나 만든 계정이 바로 데이터에 접근하면 안 되므로, 승인이 관문이다.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.accounts.schemas import AccountOut
from app.modules.auth import security
from app.modules.auth.models import RefreshToken
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit
from app.shared.dependents import Reference, references_to, transfer_ownership
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
    db.flush()

    # 알림 모듈을 직접 부르지 않고 큐에 던진다 — 모듈끼리 묶이지 않게, 그리고
    # 수신자가 늘어도 신청자의 응답이 느려지지 않게.
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": "account.signup",
            "key": str(user.id),
            "title": "새 가입 신청",
            "body": (
                f"{user.display_name}({user.email}) 님이"
                f" {workspace.name} 소속으로 신청했습니다."
            ),
            "link": "/admin/accounts",
            "to_user_id": None,
        },
    )
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

    _on_activated(db, user)
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": "account.decided",
            "key": f"approved:{user.id}",
            "title": "가입이 승인되었습니다",
            "body": f"{workspace.name} 소속으로 승인되었습니다. 이제 로그인할 수 있습니다.",
            "link": "/",
            "to_user_id": str(user.id),
        },
    )
    audit.record(
        db,
        action=audit.ACCOUNT_DECIDED,
        actor=decided_by,
        target_table="users",
        target_id=user.id,
        target_label=user.display_name or user.email,
        workspace_id=workspace.id,
        changes={"status": {"before": "pending", "after": "active"}, "role": {"after": role}},
    )
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

    # 거절도 알린다. 메일이 없어 앱 안이 유일한 통보 경로이고, 사유를 함께 담지
    # 않으면 신청자가 무엇을 고쳐 다시 신청해야 할지 모른다.
    _on_activated(db, user)  # 규칙이 있어야 이 알림을 받을 수 있다
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": "account.decided",
            "key": f"rejected:{user.id}",
            "title": "가입 신청이 거절되었습니다",
            "body": user.decision_note,
            "link": None,
            "to_user_id": str(user.id),
        },
    )
    audit.record(
        db,
        action=audit.ACCOUNT_DECIDED,
        actor=decided_by,
        target_table="users",
        target_id=user.id,
        target_label=user.display_name or user.email,
        changes={"status": {"before": "pending", "after": "suspended"}},
        # **거절 사유가 곧 근거다.** 사유 없이 거절만 남으면 나중에 같은 사람이
        # 다시 신청했을 때 무엇을 보고 판단했는지 알 수 없다.
        reason=user.decision_note,
    )
    db.commit()
    return user


def _on_activated(db: Session, user: User) -> None:
    """계정이 실제로 쓰이기 시작할 때 기본 알림 규칙을 보장한다.

    알림 모듈을 직접 부르지 않고 큐로 넘긴다(경계 유지).
    """
    queue.enqueue(db, kind=kinds.NOTIFY_ENSURE_RULES, payload={"user_id": str(user.id)})


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
    _on_activated(db, user)
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

    before = user.status
    user.status = status
    if status == "suspended":
        # 접근을 즉시 끊는다. 세션이 남아 있으면 정지가 무의미하다.
        for token in db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        ):
            token.revoked_at = _now()
    # 정지는 **되돌릴 수 있어도 접근을 끊는다.** 누가 언제 끊었는지 남지 않으면
    # "왜 로그인이 안 되죠" 를 설명할 근거가 없다.
    audit.record(
        db,
        action=audit.ACCOUNT_SUSPENDED,
        actor=actor,
        target_table="users",
        target_id=user.id,
        target_label=user.display_name or user.email,
        changes={"status": {"before": before, "after": status}},
    )
    db.commit()
    return user


def set_system_admin(db: Session, *, user_id: uuid.UUID, grant: bool, actor: User) -> User:
    """시스템 관리자 권한을 주거나 뺀다. **시스템 관리자만 부른다**(라우트가 막는다).

    ## 자기 것은 못 바꾼다

    빼는 쪽이 위험하다 — 마지막 관리자가 자기 권한을 빼면 **아무도 되돌릴 수 없는
    상태**가 된다. 계정을 새로 만들 수도, 남에게 권한을 줄 수도 없으니 DB 를 직접
    고치는 수밖에 없다. 주는 쪽은 무의미하므로(이미 갖고 있다) 둘 다 막는다.

    자기 것을 막아 두면 **관리자가 0명이 되는 길이 없다**. 부르는 사람이 이미
    관리자이고 대상이 자기가 아니므로, 무엇을 빼든 부른 사람은 남는다.

    ## 활성 계정에만 준다

    정지·대기·거절 상태에 권한을 주면 화면에는 관리자로 보이는데 로그인은 안 되는
    계정이 생긴다. 「관리자인데 왜 못 들어오지」 를 설명할 길이 없다. **빼는 것은
    상태를 안 본다** — 정지된 관리자의 권한을 못 뺀다면 그것이 더 이상하다.
    """
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")
    if user.id == actor.id:
        raise Conflict(
            "MNX-ACCOUNTS-0015",
            "자기 계정의 시스템 관리자 권한은 바꿀 수 없습니다. 다른 관리자에게 요청하세요.",
        )
    if grant and user.status != "active":
        raise Conflict(
            "MNX-ACCOUNTS-0016",
            "활성 계정에만 시스템 관리자 권한을 줄 수 있습니다.",
        )

    before = user.is_system_admin
    if before == grant:
        # **아무것도 안 바뀌었으면 기록도 안 남긴다.** 두 번 누른 것이 감사 로그에
        # 「변경」 으로 두 줄 남으면, 나중에 누가 무엇을 했는지 읽을 때 방해가 된다.
        return user
    user.is_system_admin = grant

    audit.record(
        db,
        action=audit.ACCOUNT_ADMIN_CHANGED,
        actor=actor,
        target_table="users",
        target_id=user.id,
        target_label=user.display_name or user.email,
        changes={"is_system_admin": {"before": before, "after": grant}},
    )
    db.commit()
    return user


def set_home_workspace(
    db: Session, *, user_id: uuid.UUID, workspace_slug: str, actor: User
) -> User:
    """대표 소속을 정한다 — **로그인해서 처음 서는 자리**다.

    이 값이 없으면 로그인이 `memberships[0]`, 즉 **이름 순 첫 부서**로 떨어진다.
    부서 하나뿐인 사람에게는 그것이 맞지만, 시스템 관리자처럼 여러 부서에 든
    사람은 매번 엉뚱한 곳에 서고 부서를 손으로 바꿔야 했다. 그 순서를 정하는
    것은 사람이지 이름 가나다순이 아니다.

    **멤버가 아닌 부서는 못 준다.** 주면 그 사람은 로그인해서 자기가 못 보는
    부서에 서고, 목록이 비어 보인다 — 데이터가 없는 것과 구별이 안 된다.
    멤버십을 만드는 것은 부서 멤버 화면의 일이고, 여기서 겸하면 "대표 소속을
    정했더니 없던 권한이 생겼다" 가 된다.

    이 규칙은 반대쪽에도 이미 있다 — 멤버에서 빼면 대표 소속이 남은 부서로
    옮겨진다(`workspaces/services.py`). 한쪽만 있으면 그 사이가 어긋난다.
    """
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")

    workspace = _workspace_by_slug(db, workspace_slug)

    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None:
        raise AppError(
            "MNX-ACCOUNTS-0014",
            f"{workspace.name} 의 멤버가 아닙니다. 부서 멤버로 먼저 넣으세요.",
            status=400,
        )

    before = db.get(Workspace, user.home_workspace_id) if user.home_workspace_id else None
    if before is not None and before.id == workspace.id:
        return user

    user.home_workspace_id = workspace.id
    # **로그인해서 서는 자리가 바뀐다.** 본인은 다음 로그인에서야 알게 되므로,
    # "왜 다른 부서에 서 있죠" 를 설명할 근거가 남아 있어야 한다.
    audit.record(
        db,
        action=audit.ACCOUNT_HOME_CHANGED,
        actor=actor,
        target_table="users",
        target_id=user.id,
        target_label=user.display_name or user.email,
        workspace_id=workspace.id,
        changes={
            "home_workspace": {
                "before": before.slug if before else None,
                "after": workspace.slug,
            }
        },
    )
    db.commit()
    return user


def delete_account(
    db: Session, *, user_id: uuid.UUID, actor: User, transfer_to_id: uuid.UUID | None
) -> list[Reference]:
    """계정을 지운다 — 행을 없애지 않고 `deleted_at` 을 찍는다.

    **자료는 남기고 접근만 끊는다**(구조결정 4). 그 사람이 등록한 시험 데이터의
    소유자 참조가 살아 있어야 "누가 만든 데이터인가"를 잃지 않는다. 소유권만
    `transfer_to_id` 로 넘긴다.

    옮긴 내역을 돌려준다 — 화면이 "무엇이 넘어갔는지" 보여 줘야 관리자가
    결과를 확인할 수 있다.
    """
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")
    if user.id == actor.id:
        raise Conflict("MNX-ACCOUNTS-0006", "자기 계정은 지울 수 없습니다.")
    if user.deleted_at is not None:
        raise Conflict("MNX-ACCOUNTS-0009", "이미 삭제된 계정입니다.")

    if user.is_system_admin:
        remaining = db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.is_system_admin.is_(True),
                User.deleted_at.is_(None),
                User.id != user.id,
            )
        )
        if not remaining:
            raise Conflict(
                "MNX-ACCOUNTS-0010",
                "마지막 시스템 관리자는 지울 수 없습니다. 다른 관리자를 먼저 지정하세요.",
            )

    moved: list[Reference] = []
    if transfer_to_id is not None:
        successor = db.get(User, transfer_to_id)
        if successor is None or successor.deleted_at is not None:
            raise NotFound("MNX-ACCOUNTS-0011", "승계받을 계정을 찾을 수 없습니다.")
        if successor.id == user.id:
            raise Conflict("MNX-ACCOUNTS-0012", "같은 계정으로는 승계할 수 없습니다.")
        moved = transfer_ownership(db, table="users", from_pk=user.id, to_pk=successor.id)

    # 부서 멤버십은 정리한다. 남겨 두면 부서 멤버 목록에 지워진 계정이 계속 뜬다.
    # 다만 그 부서의 마지막 관리자였다면 부서가 잠기므로 먼저 막는다.
    memberships = list(
        db.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
    )
    for membership in memberships:
        if membership.role != "manager":
            continue
        another = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == membership.workspace_id,
                WorkspaceMember.role == "manager",
                WorkspaceMember.user_id != user.id,
            )
        )
        if another is None:
            workspace = db.get(Workspace, membership.workspace_id)
            raise Conflict(
                "MNX-ACCOUNTS-0013",
                f"'{workspace.name if workspace else membership.workspace_id}' 부서의"
                " 마지막 관리자입니다. 다른 사람을 관리자로 지정한 뒤 지우세요.",
            )
    for membership in memberships:
        db.delete(membership)

    for token in db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ):
        token.revoked_at = _now()

    user.deleted_at = _now()
    user.status = "suspended"
    user.home_workspace_id = None
    audit.record(
        db,
        action=audit.ACCOUNT_DELETED,
        actor=actor,
        target_table="users",
        target_id=user.id,
        target_label=user.display_name or user.email,
        # 무엇이 누구에게 넘어갔는지가 이 기록의 핵심이다. 자료는 남고 소유자만
        # 바뀌므로, 넘긴 내역이 없으면 나중에 그 자료의 출처를 되짚을 수 없다.
        changes={
            "deleted_at": {"after": user.deleted_at.isoformat()},
            "transferred": {"after": [f"{ref.table} {ref.count}건" for ref in moved]},
        },
    )
    db.commit()
    return moved


def dependents_of(db: Session, *, user_id: uuid.UUID) -> list[Reference]:
    """삭제 전에 무엇이 딸려 있는지 미리 보여 준다."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("MNX-ACCOUNTS-0003", "계정을 찾을 수 없습니다.")
    return references_to(db, table="users", pk=user.id)


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
