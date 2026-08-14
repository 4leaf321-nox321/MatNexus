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
from app.modules.voc.schemas import VocCreateRequest, VocOut, VocReplyRequest
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, NotFound

router = APIRouter(prefix="/voc", tags=["voc"])


def _out(db: Session, item: VocItem) -> VocOut:
    author = db.get(User, item.created_by_id) if item.created_by_id else None
    return VocOut(
        id=item.id,
        title=item.title,
        body=item.body,
        status=item.status,
        page_path=item.page_path,
        created_at=item.created_at,
        created_by=author.display_name if author else None,
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
    return _out(db, item)


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
    return [_out(db, item) for item in db.scalars(query)]


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
    return _out(db, item)
