"""VOC 라우터.

접수는 누구나(로그인한 사람), 목록·답변은 시스템 관리자. 자기가 낸 것은
본인도 볼 수 있어야 "접수됐나?"를 확인할 수 있다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.voc.models import VOC_STATUSES, VocItem
from app.modules.voc.schemas import (
    VocCreateRequest,
    VocOut,
    VocReplyRequest,
    VocUpdateRequest,
)
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, Forbidden, NotFound

router = APIRouter(prefix="/voc", tags=["voc"])


def _out(db: Session, item: VocItem, *, viewer: User) -> VocOut:
    author = db.get(User, item.created_by_id) if item.created_by_id else None
    return VocOut(
        id=item.id,
        title=item.title,
        body=item.body,
        status=item.status,
        page_path=item.page_path,
        created_at=item.created_at,
        created_by=author.display_name if author else None,
        is_mine=item.created_by_id == viewer.id,
        reply=item.reply,
        replied_at=item.replied_at,
    )


@router.post("", response_model=VocOut, status_code=201)
def create_item(
    payload: VocCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocOut:
    item = VocItem(
        title=payload.title,
        body=payload.body,
        page_path=payload.page_path,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    return _out(db, item, viewer=user)


@router.get("", response_model=list[VocOut])
def list_items(
    status: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[VocOut]:
    query = select(VocItem).order_by(VocItem.created_at.desc())
    if not user.is_system_admin:
        # 남이 낸 제보를 아무나 보지 않게 한다.
        query = query.where(VocItem.created_by_id == user.id)
    if status:
        query = query.where(VocItem.status == status)
    return [_out(db, item, viewer=user) for item in db.scalars(query)]


def _mine(db: Session, item_id: uuid.UUID, user: User) -> VocItem:
    """고치거나 지울 수 있는 것만 돌려준다.

    **낸 사람은 답변 전까지, 관리자는 언제나.** 답변이 달린 뒤에 본문이 바뀌면
    답변이 딴 소리가 된다 — 읽는 사람은 관리자가 엉뚱한 답을 한 것으로 본다.
    그때는 고치는 대신 하나 더 내는 것이 맞다.

    남이 낸 것은 목록에서도 안 보인다(`list_items`). 여기서만 막으면 주소를
    아는 사람이 고칠 수 있으므로 같은 규칙을 둔다.
    """
    item = db.get(VocItem, item_id)
    if item is None:
        raise NotFound("MNX-VOC-0001", "접수 내역을 찾을 수 없습니다.")
    if user.is_system_admin:
        return item
    if item.created_by_id != user.id:
        raise Forbidden("MNX-VOC-0003", "자기가 낸 것만 고치거나 지울 수 있습니다.")
    if item.reply is not None:
        raise Forbidden(
            "MNX-VOC-0004",
            "답변이 달린 뒤에는 고칠 수 없습니다. 덧붙일 말이 있으면 새로 남겨 주세요.",
        )
    return item


@router.patch("/{item_id}", response_model=VocOut)
def update_item(
    item_id: uuid.UUID,
    payload: VocUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocOut:
    item = _mine(db, item_id, user)
    # **안 보낸 것과 비운 것을 가른다.** 안 가르면 제목만 고치는 요청이 본문을
    # 지운다(AGENTS.md).
    if payload.title is not None:
        item.title = payload.title
    if payload.body is not None:
        item.body = payload.body
    db.commit()
    return _out(db, item, viewer=user)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """**행을 없앤다.** 딸린 것이 없어 남길 것도 없다 — 화면이 먼저 묻는다."""
    db.delete(_mine(db, item_id, user))
    db.commit()


@router.post("/{item_id}/reply", response_model=VocOut)
def reply(
    item_id: uuid.UUID,
    payload: VocReplyRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> VocOut:
    if payload.status not in VOC_STATUSES:
        raise AppError("MNX-VOC-0002", "허용되지 않는 상태입니다.", status=400)

    item = db.get(VocItem, item_id)
    if item is None:
        raise NotFound("MNX-VOC-0001", "접수 내역을 찾을 수 없습니다.")

    item.reply = payload.reply
    item.replied_by_id = admin.id
    item.replied_at = datetime.now(UTC)
    item.status = payload.status
    db.commit()
    return _out(db, item, viewer=admin)
