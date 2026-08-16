"""부서 라우터.

`/options` 만 인증 없이 열려 있다 — 가입 신청 화면에서 희망 부서를 골라야 하는데,
그 화면은 로그인 전이다. 이름과 주소만 나가고 멤버 수나 내부 식별자는 담지 않는다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.workspaces import services
from app.modules.workspaces.schemas import (
    MemberAddRequest,
    MemberOut,
    MemberRoleRequest,
    WorkspaceCreateRequest,
    WorkspaceMoveRequest,
    WorkspaceOption,
    WorkspaceOut,
    WorkspaceReferenceOut,
    WorkspaceReorderRequest,
    WorkspaceUpdateRequest,
)
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import Forbidden
from app.shared.permissions import require_manager, require_member, workspace_by_slug

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/options", response_model=list[WorkspaceOption])
def options(db: Session = Depends(get_db)) -> list[WorkspaceOption]:
    """가입 신청 화면용. 로그인 전에 부르므로 인증이 없다."""
    return services.options(db)


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    all_workspaces: bool = Query(default=False, alias="all"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceOut]:
    if all_workspaces and not user.is_system_admin:
        raise Forbidden(
            "MNX-WORKSPACES-0011", "전체 부서 목록은 시스템 관리자만 볼 수 있습니다."
        )
    return services.list_for(db, user, all_workspaces=all_workspaces)


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    payload: WorkspaceCreateRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    workspace = services.create(
        db,
        slug=payload.slug,
        name=payload.name,
        creator=admin,
        parent_slug=payload.parent_slug,
    )
    return services.workspace_out(db, workspace, admin)


@router.patch("/{slug}", response_model=WorkspaceOut)
def update_workspace(
    slug: str,
    payload: WorkspaceUpdateRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    workspace = services.update(db, slug=slug, name=payload.name, is_active=payload.is_active)
    return services.workspace_out(db, workspace, admin)


@router.post("/{slug}/move", response_model=WorkspaceOut)
def move_workspace(
    slug: str,
    payload: WorkspaceMoveRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    """상위 부서 바꾸기 — 조직 개편.

    **자료는 하나도 안 움직인다.** 시험·재료는 부서 `id` 를 가리키고, 트리를 옮겨도
    그 id 는 그대로다. 65가 조직 식별자를 데이터에 직접 박아 개편에 대응할 수단이
    없었던 것과 반대다.
    """
    workspace = services.move(
        db,
        slug=slug,
        parent_slug=payload.parent_slug,
        before_slug=payload.before_slug,
    )
    return services.workspace_out(db, workspace, admin)


@router.get("/{slug}/references", response_model=list[WorkspaceReferenceOut])
def workspace_references(
    slug: str,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[WorkspaceReferenceOut]:
    """무엇이 이 부서를 가리키는가. 삭제 확인 화면이 부른다.

    목록을 손으로 관리하지 않는다 — FK 를 훑어 모은다. RA 의 부서 삭제 500 버그가
    "참조 테이블 목록이 하드코딩돼 새 테이블을 못 따라감" 이었다.
    """
    return services.references(db, slug=slug)


@router.delete("/{slug}", status_code=204)
def delete_workspace(
    slug: str,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    """부서를 지운다. 막는 참조가 하나라도 있으면 거절한다.

    **보관이 여전히 기본 수단이다.** 삭제는 잘못 만든 부서처럼 자료가 아예 없는
    경우를 위한 것이다 — 자료가 있는 부서는 지우는 게 아니라 보관한다.
    """
    services.delete(db, slug=slug)
    return Response(status_code=204)


@router.post("/{slug}/reorder", response_model=WorkspaceOut)
def reorder_workspace(
    slug: str,
    payload: WorkspaceReorderRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    """형제 사이 순서. 조직도 순서는 이름순도 생성순도 아니다 — 사람이 정한다."""
    workspace = services.reorder(db, slug=slug, direction=payload.direction)
    return services.workspace_out(db, workspace, admin)


# --- 멤버 --------------------------------------------------------------------


@router.get("/{slug}/members", response_model=list[MemberOut])
def list_members(
    slug: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    workspace = workspace_by_slug(db, slug)
    # 조회는 멤버면 된다 — 같은 부서 사람이 누군지는 알아야 일이 된다.
    require_member(db, workspace=workspace, user=user)
    return services.members(db, workspace=workspace)


@router.post("/{slug}/members", response_model=MemberOut, status_code=201)
def add_member(
    slug: str,
    payload: MemberAddRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MemberOut:
    workspace = workspace_by_slug(db, slug)
    require_manager(db, workspace=workspace, user=user)
    return services.add_member(db, workspace=workspace, email=payload.email, role=payload.role)


@router.patch("/{slug}/members/{user_id}", response_model=MemberOut)
def set_member_role(
    slug: str,
    user_id: uuid.UUID,
    payload: MemberRoleRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MemberOut:
    workspace = workspace_by_slug(db, slug)
    require_manager(db, workspace=workspace, user=user)
    return services.set_role(db, workspace=workspace, user_id=user_id, role=payload.role)


@router.delete("/{slug}/members/{user_id}", status_code=204)
def remove_member(
    slug: str,
    user_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    workspace = workspace_by_slug(db, slug)
    require_manager(db, workspace=workspace, user=user)
    services.remove_member(db, workspace=workspace, user_id=user_id)
