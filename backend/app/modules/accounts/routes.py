"""계정 라우터.

`/signup` 만 인증 없이 열려 있고 나머지는 시스템 관리자 전용이다. 부서 단위
멤버 관리는 workspaces 모듈이 담당한다 — 여기는 "계정 자체의 생애"만 다룬다
(생성·승인·정지·비밀번호). 두 책임을 섞으면 화면도 섞인다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts import services
from app.modules.accounts.models import User
from app.modules.accounts.schemas import (
    AccountOut,
    ApproveRequest,
    CreateAccountRequest,
    DeleteAccountRequest,
    DeleteAccountResponse,
    HomeWorkspaceRequest,
    ReferenceOut,
    RejectRequest,
    SignupRequest,
    TemporaryPasswordResponse,
)
from app.shared.auth import require_system_admin

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("/signup", response_model=AccountOut, status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> AccountOut:
    """가입 신청. 승인 전까지는 로그인할 수 없다(status=pending)."""
    user = services.signup(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        workspace_slug=payload.workspace_slug,
    )
    return services.account_out(db, user)


@router.get("", response_model=list[AccountOut])
def list_accounts(
    status: str | None = Query(default=None, pattern="^(pending|active|suspended)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[AccountOut]:
    users = services.list_accounts(db, status=status, limit=limit, offset=offset)
    return [services.account_out(db, user) for user in users]


@router.post("", response_model=TemporaryPasswordResponse, status_code=201)
def create_account(
    payload: CreateAccountRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TemporaryPasswordResponse:
    user, temporary = services.create_account(
        db,
        email=payload.email,
        display_name=payload.display_name,
        workspace_slug=payload.workspace_slug,
        role=payload.role,
        is_system_admin=payload.is_system_admin,
        created_by=admin,
    )
    return TemporaryPasswordResponse(
        account=services.account_out(db, user), temporary_password=temporary
    )


@router.post("/{account_id}/approve", response_model=AccountOut)
def approve(
    account_id: uuid.UUID,
    payload: ApproveRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    user = services.approve(
        db,
        user_id=account_id,
        decided_by=admin,
        workspace_slug=payload.workspace_slug,
        role=payload.role,
    )
    return services.account_out(db, user)


@router.post("/{account_id}/reject", response_model=AccountOut)
def reject(
    account_id: uuid.UUID,
    payload: RejectRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    user = services.reject(db, user_id=account_id, decided_by=admin, note=payload.note)
    return services.account_out(db, user)


@router.post("/{account_id}/suspend", response_model=AccountOut)
def suspend(
    account_id: uuid.UUID,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    user = services.set_status(db, user_id=account_id, status="suspended", actor=admin)
    return services.account_out(db, user)


@router.post("/{account_id}/activate", response_model=AccountOut)
def activate(
    account_id: uuid.UUID,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    user = services.set_status(db, user_id=account_id, status="active", actor=admin)
    return services.account_out(db, user)


@router.post("/{account_id}/home-workspace", response_model=AccountOut)
def set_home_workspace(
    account_id: uuid.UUID,
    payload: HomeWorkspaceRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    """대표 소속 — 이 사람이 로그인해서 처음 서는 부서."""
    user = services.set_home_workspace(
        db, user_id=account_id, workspace_slug=payload.workspace_slug, actor=admin
    )
    return services.account_out(db, user)


@router.get("/{account_id}/dependents", response_model=list[ReferenceOut])
def dependents(
    account_id: uuid.UUID,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[ReferenceOut]:
    """삭제 전 미리보기. 무엇이 딸려 있는지 보고 나서 결정하게 한다."""
    return [
        ReferenceOut(
            table=ref.table,
            label=ref.label,
            column=ref.column,
            count=ref.count,
            on_delete=ref.on_delete,
            blocks_delete=ref.blocks_delete,
        )
        for ref in services.dependents_of(db, user_id=account_id)
    ]


@router.delete("/{account_id}", response_model=DeleteAccountResponse)
def delete_account(
    account_id: uuid.UUID,
    payload: DeleteAccountRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> DeleteAccountResponse:
    """계정을 지운다. 행은 남고 접근만 끊긴다 — 자료의 소유자 참조를 잃지 않기 위해서다."""
    moved = services.delete_account(
        db, user_id=account_id, actor=admin, transfer_to_id=payload.transfer_to_id
    )
    return DeleteAccountResponse(
        transferred=[
            ReferenceOut(
                table=ref.table,
                label=ref.label,
                column=ref.column,
                count=ref.count,
                on_delete=ref.on_delete,
                blocks_delete=ref.blocks_delete,
            )
            for ref in moved
        ]
    )


@router.post("/{account_id}/reset-password", response_model=TemporaryPasswordResponse)
def reset_password(
    account_id: uuid.UUID,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TemporaryPasswordResponse:
    """관리자 중개 재설정. SMTP 가 없으므로 화면에 1회 표시하고 구두로 전달한다."""
    user, temporary = services.reset_password(db, user_id=account_id)
    return TemporaryPasswordResponse(
        account=services.account_out(db, user), temporary_password=temporary
    )
