"""부서 라우터.

`/options` 만 인증 없이 열려 있다 — 가입 신청 화면에서 희망 부서를 골라야 하는데,
그 화면은 로그인 전이다. 이름과 주소만 나가고 멤버 수나 내부 식별자는 담지 않는다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.workspaces import imports, services
from app.modules.workspaces.schemas import (
    ImportResultOut,
    ImportRowOut,
    MemberAddRequest,
    MemberOut,
    MemberRoleRequest,
    WorkspaceCreateRequest,
    WorkspaceMergeRequest,
    WorkspaceMoveRequest,
    WorkspaceOption,
    WorkspaceOut,
    WorkspaceReferenceOut,
    WorkspaceReorderRequest,
    WorkspaceUpdateRequest,
)
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, Conflict, Forbidden
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


@router.post("/import/preview", response_model=ImportResultOut)
def preview_import(
    file: UploadFile,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> ImportResultOut:
    """ReportArchive 부서 내보내기 CSV 로 **무엇이 만들어질지** 먼저 보여 준다.

    바로 만들지 않는 이유: 조직도는 한 번 잘못 들어가면 지우기 어렵다(부서마다
    재료·시험이 매달리기 시작한다). 계획을 보고 사람이 누른다.
    """
    rows = imports.parse(_read_limited(file))
    return _import_out(imports.plan(db, rows))


@router.post("/import", response_model=ImportResultOut)
def import_workspaces(
    file: UploadFile,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> ImportResultOut:
    """미리보기와 **같은 코드**로 판정해 만든다. 한 트랜잭션이다 — 절반만 들어간
    조직도는 없느니만 못하다."""
    rows = imports.parse(_read_limited(file))
    planned = imports.apply(db, rows, creator=admin)
    try:
        db.commit()
    except IntegrityError as exc:
        # 같은 순간에 다른 관리자가 같은 slug 를 만들었다. 미리보기 검사와 commit
        # 사이의 틈이라 미리 못 막는다 — 500 대신 다시 시도하라고 말한다.
        db.rollback()
        raise Conflict(
            "MNX-WORKSPACES-0022",
            "같은 순간에 다른 관리자가 부서를 만들고 있습니다. 다시 시도해 주세요.",
        ) from exc
    return _import_out(planned)


#: 부서 CSV 의 크기 상한. 막는 값이 아니라 **실수를 막는 값**이다 — 조직도
#: CSV 는 커야 수백 KB 인데, 엉뚱한 파일(측정 데이터 덤프)을 올리면 메모리로
#: 통째로 읽는다.
IMPORT_MAX_BYTES = 5 * 1024 * 1024


def _read_limited(file: UploadFile) -> bytes:
    raw = file.file.read(IMPORT_MAX_BYTES + 1)
    if len(raw) > IMPORT_MAX_BYTES:
        raise AppError(
            "MNX-WORKSPACES-0023",
            "파일이 5MB 를 넘습니다 — 부서 내보내기 CSV 가 아닌 것 같습니다.",
            status=422,
        )
    return raw


def _import_out(planned: list[imports.Planned]) -> ImportResultOut:
    return ImportResultOut(
        rows=[
            ImportRowOut(
                line=one.line,
                slug=one.slug,
                name=one.name,
                parent_slug=one.parent_slug,
                action=one.action,
                reason=one.reason,
            )
            for one in planned
        ],
        created=sum(1 for one in planned if one.action == "create"),
        skipped=sum(1 for one in planned if one.action.startswith("skip")),
        errors=sum(1 for one in planned if one.action == "error"),
    )


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


@router.post("/{slug}/merge", response_model=list[WorkspaceReferenceOut])
def merge_workspace(
    slug: str,
    payload: WorkspaceMergeRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[WorkspaceReferenceOut]:
    """이 부서의 데이터를 전부 다른 부서로 옮기고 원본을 보관한다.

    무엇이 옮겨질지는 `GET /{slug}/references` 가 먼저 보여 준다 — 화면이 그
    목록을 띄우고 사람이 누른다. 응답은 **실제로 옮긴 것**의 같은 목록이다.
    """
    moved = services.merge_into(
        db, source_slug=slug, target_slug=payload.target_slug, actor=admin
    )
    return [
        WorkspaceReferenceOut(
            table=one.table,
            column=one.column,
            label=one.label,
            count=one.count,
            on_delete=one.on_delete,
            blocks_delete=one.blocks_delete,
        )
        for one in moved
    ]


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
