"""누가 고치나 — 보고, 넘긴다(ADR 0035 D4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.ownership import services
from app.modules.ownership.schemas import (
    OwnedKind,
    OwnershipChangeOut,
    OwnershipChangeRequest,
    OwnershipChildrenOut,
    OwnershipOut,
    PersonOut,
)
from app.modules.workspaces.models import Workspace
from app.shared import permissions
from app.shared.access import AccessBook, access_of
from app.shared.auth import current_user
from app.shared.errors import AppError

router = APIRouter(prefix="/ownership", tags=["ownership"])

#: 사람 찾기 한 번에 주는 수. 서버가 상한을 둔다(AGENTS.md).
PEOPLE_LIMIT = 20


@router.get("/people", response_model=list[PersonOut])
def people(
    q: str = Query(default="", max_length=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PersonOut]:
    """넘겨받을 사람을 **이름으로** 찾는다 — 지금 로그인할 수 있는 사람만.

    계정 목록은 시스템 관리자 것이라, 등록자가 넘길 사람을 고를 길이 없었다. 여기는
    그 한 가지 일만 한다: 이름과 대표 소속.
    """
    return services.people(db, q, limit=PEOPLE_LIMIT)


@router.get("/stewards", response_model=list[PersonOut])
def stewards(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PersonOut]:
    """**자료 관리자는 누구인가** — 새 기준정보 값·카드 확정·핸드북 승인을 부탁할 사람.

    자료 관리자가 없으면 시스템 관리자를 댄다. 막힌 사람이 「관리자에게 문의하세요」 만
    받으면 그게 누구인지 또 물어야 한다(ADR 0035) — 403 은 그 이름을 `details` 로 주지만,
    **막히기 전에** 물을 자리가 없었다(AI 가 새 등급을 미리보기로 막고도 이름을 못 댔다).
    """
    del user
    return services.stewards(db)


@router.get("/{kind}/{row_id}", response_model=OwnershipOut)
def get_ownership(
    kind: OwnedKind,
    row_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OwnershipOut:
    """지금 누가 고치나, 그리고 **아래에 무엇이 몇 건 딸렸나** — 넘기기 전에 본다."""
    row = services.load(db, user, kind, row_id)
    book = AccessBook(db, user)
    return OwnershipOut(
        kind=kind,
        id=row.id,
        name=services.name_of(row),
        access=book.of(row),
        children=[
            OwnershipChildrenOut(
                kind=child,
                label=services.LABELS[child],
                total=len(rows),
                changeable=sum(1 for one in rows if book.editor.can_hand_over(one)),
            )
            for child, rows in services.children(db, row)
            if rows
        ],
    )


@router.put("/{kind}/{row_id}", response_model=OwnershipChangeOut)
def change_ownership(
    kind: OwnedKind,
    row_id: uuid.UUID,
    payload: OwnershipChangeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OwnershipChangeOut:
    """등록자·편집 부서를 넘긴다. **등록자와 관리자만.**

    **안 보낸 칸은 그대로다.** `edit_workspace_slug` 를 `null` 로 **보내면** 부여를
    걷는다 — 안 보낸 것과 비운 것을 가르지 않으면, 등록자만 넘기려다 부서 부여가
    함께 사라진다(선언 물성·일괄 수정이 같은 자리에서 걸렸다, AGENTS.md).
    """
    row = services.load(db, user, kind, row_id)
    permissions.require_hand_over(db, user, row, code="MNX-OWNERSHIP-0004")

    given = payload.model_fields_set
    set_registrant = "registrant_id" in given
    set_workspace = "edit_workspace_slug" in given
    if not set_registrant and not set_workspace:
        raise AppError(
            "MNX-OWNERSHIP-0005",
            "바꿀 것이 없습니다 — 등록자나 편집 부서를 보내세요.",
            status=422,
        )
    if set_registrant and payload.registrant_id is None:
        raise AppError(
            "MNX-OWNERSHIP-0006",
            "등록자는 비울 수 없습니다 — 다른 사람에게 넘기기만 합니다.",
            status=422,
        )
    registrant = (
        services.active_user(db, payload.registrant_id)
        if set_registrant and payload.registrant_id is not None
        else None
    )
    workspace: Workspace | None = (
        services.active_workspace(db, payload.edit_workspace_slug)
        if set_workspace and payload.edit_workspace_slug
        else None
    )

    changed, skipped = services.change(
        db,
        user,
        row,
        registrant=registrant,
        set_registrant=set_registrant,
        workspace=workspace,
        set_workspace=set_workspace,
        include_children=payload.include_children,
    )
    db.commit()
    db.refresh(row)
    return OwnershipChangeOut(
        changed=changed, skipped=skipped, access=access_of(db, user, row)
    )
