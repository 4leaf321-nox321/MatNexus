"""알림 라우터 — 자기 것만 본다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.notifications import services
from app.modules.notifications.schemas import NotificationOut, UnreadCountOut
from app.shared.auth import current_user
from app.shared.errors import NotFound

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    return [
        NotificationOut.model_validate(item)
        for item in services.list_for(db, user, limit=limit, offset=offset)
    ]


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> UnreadCountOut:
    return UnreadCountOut(unread=services.unread_count(db, user))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> NotificationOut:
    item = services.mark_read(db, user, notification_id)
    if item is None:
        # 남의 알림인지 없는 알림인지 구분해 알려 주지 않는다.
        raise NotFound("MNX-NOTIFICATIONS-0001", "알림을 찾을 수 없습니다.")
    return NotificationOut.model_validate(item)


@router.post("/read-all", response_model=UnreadCountOut)
def mark_all_read(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> UnreadCountOut:
    services.mark_all_read(db, user)
    return UnreadCountOut(unread=0)
