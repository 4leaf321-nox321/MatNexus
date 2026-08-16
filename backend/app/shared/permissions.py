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

from sqlalchemy import ColumnElement, Select, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
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


# --- 부서 소유 자산 ---------------------------------------------------------
#
# 재료·형식 프로파일·시험 종류가 **같은 소유 모델**을 쓴다(ADR 0004·0006):
# `owner_workspace_id IS NULL` 이면 전역, 아니면 그 부서 것. 판정을 각 모듈이
# 따로 적으면 "프로파일은 되는데 종류는 안 되는" 식으로 어긋나고, 실제로 그
# 어긋남이 부서 관리자를 막다른 길로 보냈다.


def visible_owner_clause(
    db: Session, user: User, column: InstrumentedAttribute[uuid.UUID | None]
) -> ColumnElement[bool]:
    """`전역 + 내 부서` 필터. 목록·조회·자동 추정이 **같은 것**을 봐야 한다.

    각자 판단하면 "화면에는 보이는데 파싱은 그 프로파일을 안 쓴다" 같은 어긋남이
    생긴다. 실제로 그 종류의 버그를 여러 번 만들었다.
    """
    if user.is_system_admin:
        return true()
    mine = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    return or_(column.is_(None), column.in_(mine))


def resolve_owner_workspace(
    db: Session, user: User, slug: str | None, *, what: str, code: str
) -> uuid.UUID | None:
    """만들 때 누구 것으로 할지. `None` 이면 전역 — 시스템 관리자만."""
    if slug is None:
        if not user.is_system_admin:
            raise Forbidden(
                code, f"전역 {what}은 시스템 관리자만 만들 수 있습니다. 부서를 고르세요."
            )
        return None
    workspace = workspace_by_slug(db, slug)
    require_manager(db, workspace=workspace, user=user)
    return workspace.id


def require_owner_edit(
    db: Session, user: User, owner_workspace_id: uuid.UUID | None, *, what: str, code: str
) -> None:
    """고칠 수 있는가.

    전역은 **여러 부서가 함께 쓴다.** 한 부서가 고치면 다른 부서의 데이터가
    다르게 읽히거나 다르게 해석된다 — 그래서 전역은 시스템 관리자만 손댄다.
    """
    if user.is_system_admin:
        return
    if owner_workspace_id is None:
        raise Forbidden(
            code,
            f"전역 {what}은 시스템 관리자만 고칠 수 있습니다. "
            f"여러 부서가 함께 쓰기 때문입니다.",
        )
    workspace = db.get(Workspace, owner_workspace_id)
    if workspace is None:
        raise NotFound(code, f"{what}의 소속 부서를 찾을 수 없습니다.")
    require_manager(db, workspace=workspace, user=user)


def is_any_manager(db: Session, user: User) -> bool:
    """어느 부서든 관리자인가. 화면이 만들기 버튼을 보일지 판단하는 근거다."""
    if user.is_system_admin:
        return True
    return (
        db.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.user_id == user.id, WorkspaceMember.role == "manager"
            )
        )
        is not None
    )


# --- 재료 계층의 가시 범위 --------------------------------------------------
#
# **여기 있는 이유가 있다.** 재료·시료·시편·시험이 전부 같은 규칙을 따라야 하는데,
# 각 모듈이 자기 버전을 갖고 있으면 "재료는 보이는데 그 시험은 안 보인다" 같은
# 어긋남이 생긴다. 모듈끼리 직접 부르는 것은 경계 규칙이 막으므로(CLAUDE.md),
# 공유해야 하는 판정은 shared 에 둔다.


def my_workspace_ids(db: Session, user: User) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        )
    )


def visible_materials(db: Session, user: User) -> Select[tuple[Material]]:
    """내 부서 재료 + 전역 재료(`owner_workspace_id IS NULL`).

    전역을 처음부터 함께 보게 짜는 것이 ADR 0004 가 지금 요구하는 둘 중 하나다.
    나중에 붙이면 모든 목록·상세·검색 쿼리를 다시 손봐야 한다.
    """
    query = select(Material).where(Material.deleted_at.is_(None))
    if user.is_system_admin:
        return query
    mine = my_workspace_ids(db, user)
    return query.where(
        or_(Material.owner_workspace_id.is_(None), Material.owner_workspace_id.in_(mine))
    )


def visible_material_ids(db: Session, user: User) -> Select[tuple[uuid.UUID]]:
    """하위 계층 쿼리에 끼워 넣을 서브쿼리."""
    query = select(Material.id).where(Material.deleted_at.is_(None))
    if user.is_system_admin:
        return query
    mine = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    return query.where(
        or_(Material.owner_workspace_id.is_(None), Material.owner_workspace_id.in_(mine))
    )


def visible_specimen(db: Session, user: User, specimen_id: uuid.UUID) -> Specimen:
    """볼 수 있는 시편 하나. 재료의 가시 범위를 그대로 따라간다."""
    specimen = db.scalar(
        select(Specimen)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(
            Specimen.id == specimen_id,
            Specimen.deleted_at.is_(None),
            Sample.deleted_at.is_(None),
            Sample.material_id.in_(visible_material_ids(db, user)),
        )
    )
    if specimen is None:
        raise NotFound("MNX-MATERIALS-0003", "시편을 찾을 수 없습니다.")
    return specimen
