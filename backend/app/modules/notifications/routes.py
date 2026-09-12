"""알림 라우터 — 자기 것만 본다."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.notifications import services
from app.modules.notifications.models import EVENT_LABELS, NotificationRule
from app.modules.notifications.schemas import (
    NotificationOut,
    NotificationRuleOut,
    NotificationRuleUpdate,
    UnreadCountOut,
)
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


def _rule_out(rule: NotificationRule) -> NotificationRuleOut:
    label, description = EVENT_LABELS.get(rule.event_kind, (rule.event_kind, ""))
    return NotificationRuleOut(
        event_kind=rule.event_kind, label=label, description=description, enabled=rule.enabled
    )


@router.get("/rules", response_model=list[NotificationRuleOut])
def list_rules(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[NotificationRuleOut]:
    """내가 받을 수 있는 알림과 켜짐 여부. 역할이 정한 것만 보인다."""
    return [_rule_out(rule) for rule in services.rules_for(db, user)]


@router.patch("/rules/{event_kind}", response_model=NotificationRuleOut)
def update_rule(
    event_kind: str,
    payload: NotificationRuleUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> NotificationRuleOut:
    """알림 하나를 켜거나 끈다. 끄면 그 사건은 나에게 오지 않는다 — 다른 사람은 그대로."""
    rule = services.set_rule(db, user, event_kind, enabled=payload.enabled)
    if rule is None:
        raise NotFound("MNX-NOTIFICATIONS-0002", "받을 수 있는 알림이 아닙니다.")
    return _rule_out(rule)


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
