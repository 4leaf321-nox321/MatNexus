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

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

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
