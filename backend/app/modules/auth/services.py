"""인증 로직.

오류는 전부 `AppError` 로 던진다 — 응답을 만드는 경로가 곧 로그를 남기는
경로여야 65의 "원인이 로그에 안 남는" 실패가 재발하지 않는다(ADR 0001).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.auth.models import PersonalAccessToken, RefreshToken
from app.modules.auth.schemas import PatOut, UserOut, WorkspaceMembershipOut
from app.modules.workspaces import services as workspaces
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit
from app.shared.errors import AppError, Forbidden, NotFound

_INVALID_LOGIN = "이메일 또는 비밀번호가 올바르지 않습니다."


def _now() -> datetime:
    return datetime.now(UTC)


def ensure_can_sign_in(user: User) -> None:
    """로그인을 막아야 하면 사유에 맞는 오류를 던진다.

    "왜 안 되는지"를 구분해 주는 것이 중요하다. 승인 대기 중인 사람에게
    '비활성 계정' 이라고만 하면 관리자에게 무엇을 요청해야 할지 알 수 없다.
    """
    if user.deleted_at is not None:
        raise Forbidden("MNX-AUTH-0002", "삭제된 계정입니다. 관리자에게 문의하세요.")
    if user.status == "pending":
        raise Forbidden(
            "MNX-AUTH-0008", "가입 승인 대기 중입니다. 관리자가 승인하면 로그인할 수 있습니다."
        )
    if user.status != "active":
        raise Forbidden("MNX-AUTH-0002", "정지된 계정입니다. 관리자에게 문의하세요.")


# --- 로그인 -----------------------------------------------------------------


#: 시험이 갈아 끼운다 — 실제로 자면 시험이 30초씩 선다.
_sleep = time.sleep


def login_delay_seconds(failures: int) -> float:
    """이번 실패가 몇 번째인가 → 몇 초 늦출까. 문턱 전은 0.

    5회부터 2초씩 늘어 최대 30초(기본값). **잠금은 없다** — 관리자 복구가 서버 콘솔
    뿐인 시스템에서 잠금은 자해라고 계획 문서가 적었다. 늦추기만 해도 무차별 시도는
    시간당 몇 번으로 줄고, 비밀번호를 아는 사람은 한 번 기다리면 된다.
    """
    settings = get_settings()
    over = failures - settings.login_delay_after + 1
    if over <= 0:
        return 0.0
    return float(
        min(settings.login_delay_step_seconds * over, settings.login_delay_max_seconds)
    )


def _note_failure(db: Session, user: User) -> float:
    """실패를 세고 이번에 늦출 초를 돌려준다. 창이 지났으면 처음부터."""
    settings = get_settings()
    now = _now()
    window = timedelta(minutes=settings.login_failure_window_minutes)
    if user.last_failed_login_at is None or now - user.last_failed_login_at > window:
        user.failed_logins = 0
    user.failed_logins += 1
    user.last_failed_login_at = now
    delay = login_delay_seconds(user.failed_logins)
    if user.failed_logins == settings.login_delay_after:
        # 문턱을 넘는 순간 한 번만 — 실패마다 남기면 감사 기록이 넘친다.
        audit.record(
            db,
            action=audit.LOGIN_THROTTLED,
            actor=None,
            target_table="users",
            target_id=user.id,
            target_label=user.email,
            changes={"failed_logins": user.failed_logins},
        )
    db.commit()
    return delay


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))

    # 계정이 없을 때도 해시 비교를 한 번 수행해 응답 시간으로 계정 존재 여부가
    # 새지 않게 한다.
    if user is None:
        security.verify_password(password, security.hash_password("dummy"))
        raise AppError("MNX-AUTH-0001", _INVALID_LOGIN, status=401)

    if not security.verify_password(password, user.password_hash):
        # **늦추고 나서 거절한다.** 거절부터 하면 다음 시도가 바로 온다.
        delay = _note_failure(db, user)
        if delay > 0:
            _sleep(delay)
        raise AppError("MNX-AUTH-0001", _INVALID_LOGIN, status=401)

    ensure_can_sign_in(user)
    if user.failed_logins:
        user.failed_logins = 0
        user.last_failed_login_at = None
        db.commit()
    return user


def issue_session(db: Session, user: User, user_agent: str | None) -> tuple[str, int, str]:
    """(access JWT, 만료 초, refresh 평문)."""
    settings = get_settings()
    raw = security.new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            expires_at=_now() + timedelta(days=settings.refresh_token_days),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    db.commit()
    access, expires_in = security.create_access_token(user.id)
    return access, expires_in, raw


#: 회전한 옛 토큰을 **동시 갱신**으로 봐 주는 시간. 이보다 지나서 오면 재사용(탈취)이다.
#: 같은 페이지 로드의 두 요청은 밀리초 차이고, 탭 둘이 번갈아 갱신해도 초 단위다.
REFRESH_GRACE = timedelta(seconds=30)


def rotate_refresh(
    db: Session, raw: str, user_agent: str | None
) -> tuple[User, str, int, str]:
    """refresh 를 한 번 쓰면 폐기하고 새로 발급한다(회전).

    회전을 하지 않으면 탈취된 토큰이 만료까지 30일간 유효하다. 회전하면 원래
    주인이 다음 갱신을 시도하는 순간 폐기된 토큰이 쓰인 것이 드러난다.
    """
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw))
    )
    if token is None:
        raise AppError(
            "MNX-AUTH-0003", "세션이 만료되었습니다. 다시 로그인해 주세요.", status=401
        )

    if token.revoked_at is not None:
        # ── 회전 직후의 옛 값인가 — 같은 브라우저의 **동시 갱신**이다 ──────────
        #
        # 실측(2026-09-05): 한 페이지 로드에서 refresh 가 둘 나갔다(React StrictMode
        # 가 effect 를 두 번 돌린다). 서버가 둘을 순서대로 처리하면 첫째가 회전하고
        # 둘째는 **방금 회전된 값**을 들고 온다 — 그것을 탈취로 보고 admin 의 세션
        # 1,200개를 한꺼번에 끊었다. 탭이 둘이어도 같은 일이 난다.
        #
        # 탈취와 동시 갱신은 겉이 같다. 가르는 것은 **시간과 사슬**이다: 회전한 지
        # 몇 초 안이고 그 후속 토큰이 살아 있으면 같은 사람의 두 요청이다. 그때는
        # 후속 토큰을 회전시켜 사슬을 하나로 유지한다 — 옛 값을 되살리지 않는다.
        replacement = (
            db.get(RefreshToken, token.replaced_by_id) if token.replaced_by_id else None
        )
        just_rotated = _now() - token.revoked_at <= REFRESH_GRACE
        if replacement is not None and just_rotated and replacement.revoked_at is None:
            token = replacement
        else:
            # 폐기된 토큰의 재사용 — 탈취 가능성. 해당 사용자의 세션을 전부 끊는다.
            revoke_all_for_user(db, token.user_id)
            raise AppError(
                "MNX-AUTH-0005",
                "세션이 무효화되었습니다. 다시 로그인해 주세요.",
                status=401,
                details={"reason": "reuse_of_revoked_token"},
            )

    if token.expires_at <= _now():
        raise AppError(
            "MNX-AUTH-0003", "세션이 만료되었습니다. 다시 로그인해 주세요.", status=401
        )

    user = db.get(User, token.user_id)
    if user is None:
        raise Forbidden("MNX-AUTH-0002", "삭제된 계정입니다. 관리자에게 문의하세요.")
    ensure_can_sign_in(user)

    settings = get_settings()
    new_raw = security.new_opaque_token()
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=security.hash_token(new_raw),
        expires_at=_now() + timedelta(days=settings.refresh_token_days),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(new_token)
    db.flush()

    token.revoked_at = _now()
    token.replaced_by_id = new_token.id
    db.commit()

    access, expires_in = security.create_access_token(user.id)
    return user, access, expires_in, new_raw


def revoke_refresh(db: Session, raw: str) -> None:
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw))
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = _now()
        db.commit()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    for token in tokens:
        token.revoked_at = _now()
    db.commit()


# --- 비밀번호 ----------------------------------------------------------------


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not security.verify_password(current, user.password_hash):
        raise AppError("MNX-AUTH-0004", "현재 비밀번호가 올바르지 않습니다.", status=400)
    if current == new:
        raise AppError("MNX-AUTH-0006", "이전과 다른 비밀번호를 사용하세요.", status=400)

    user.password_hash = security.hash_password(new)
    user.must_change_password = False
    db.commit()

    # 비밀번호를 바꾼 이유가 유출일 수 있으므로 기존 세션을 전부 끊는다.
    revoke_all_for_user(db, user.id)


# --- 조회 --------------------------------------------------------------------


def user_out(db: Session, user: User) -> UserOut:
    rows = db.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user.id)
    ).all()

    # 순서와 경로는 **조직도가 정한다.** 이름순으로 두면 부서 선택기의 순서가
    # 부서 관리 화면과 달라진다 — 같은 목록이 화면마다 다르게 보인다.
    tree = {node.id: (depth, path) for node, depth, path in workspaces.ordered_tree(db)}
    order = {node_id: index for index, node_id in enumerate(tree)}
    rows = sorted(rows, key=lambda pair: order.get(pair[1].id, 10**6))

    home_slug: str | None = None
    if user.home_workspace_id is not None:
        home = db.get(Workspace, user.home_workspace_id)
        home_slug = home.slug if home else None

    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        is_system_admin=user.is_system_admin,
        must_change_password=user.must_change_password,
        home_workspace_slug=home_slug,
        memberships=[
            WorkspaceMembershipOut(
                workspace_id=workspace.id,
                slug=workspace.slug,
                name=workspace.name,
                path=tree.get(workspace.id, (0, workspace.name))[1],
                depth=tree.get(workspace.id, (0, workspace.name))[0],
                role=member.role,
            )
            for member, workspace in rows
        ],
    )


# --- PAT ---------------------------------------------------------------------


def create_pat(
    db: Session, user: User, name: str, expires_in_days: int | None
) -> tuple[str, PatOut]:
    raw, prefix, token_hash = security.new_pat()
    pat = PersonalAccessToken(
        user_id=user.id,
        name=name,
        prefix=prefix,
        token_hash=token_hash,
        expires_at=_now() + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    db.add(pat)
    db.commit()
    db.refresh(pat)
    return raw, PatOut.model_validate(pat)


def list_pats(db: Session, user: User) -> list[PatOut]:
    rows = db.scalars(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .order_by(PersonalAccessToken.created_at.desc())
    ).all()
    return [PatOut.model_validate(row) for row in rows]


def revoke_pat(db: Session, user: User, pat_id: uuid.UUID) -> None:
    pat = db.get(PersonalAccessToken, pat_id)
    if pat is None or pat.user_id != user.id:
        raise NotFound("MNX-AUTH-0007", "토큰을 찾을 수 없습니다.")
    if pat.revoked_at is None:
        pat.revoked_at = _now()
        db.commit()


def resolve_pat(db: Session, raw: str) -> User | None:
    """PAT 평문으로 사용자를 찾는다. 유효하지 않으면 None."""
    pat = db.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.token_hash == security.hash_token(raw)
        )
    )
    if pat is None or pat.revoked_at is not None:
        return None
    if pat.expires_at is not None and pat.expires_at <= _now():
        return None

    user = db.get(User, pat.user_id)
    if user is None or not user.can_sign_in:
        return None

    pat.last_used_at = _now()
    db.commit()
    return user
