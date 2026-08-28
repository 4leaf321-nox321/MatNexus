"""알림 로직.

발행(publish)은 **작업 큐를 거친다**. 가입 신청 트랜잭션 안에서 알림을 직접
만들면, 수신자가 많아질수록 신청자의 응답이 느려지고 알림 하나가 실패하면
가입까지 되돌아간다. 큐에 넣는 것은 한 줄이고, 실제 발송은 워커가 한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.notifications.models import (
    Notification,
    NotificationRule,
    NotificationRuleState,
)
from app.shared import permissions


def _now() -> datetime:
    return datetime.now(UTC)


def publish(
    db: Session,
    *,
    event_kind: str,
    key: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    to_user_id: uuid.UUID | None = None,
) -> None:
    """사건을 알린다 — 큐에 넣기만 하고 즉시 돌아온다.

    `to_user_id` 가 있으면 그 사람에게만, 없으면 그 사건 규칙을 가진 모두에게.
    `key` 는 중복 판정에 쓴다(같은 키로 두 번 들어오면 한 번만 간다).

    커밋은 호출부가 한다 — 도메인 변경과 한 트랜잭션이어야 "가입은 됐는데 알림은
    안 들어간" 상태가 없다.
    """
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": event_kind,
            "key": key,
            "title": title,
            "body": body,
            "link": link,
            "to_user_id": str(to_user_id) if to_user_id else None,
        },
    )


def deliver(db: Session, payload: dict[str, object]) -> int:
    """워커가 부른다. 규칙을 찾아 알림을 만든다. 만든 개수를 돌려준다."""
    event_kind = str(payload["event_kind"])
    key = str(payload["key"])
    to_user_id = payload.get("to_user_id")

    query = select(NotificationRule).where(
        NotificationRule.event_kind == event_kind, NotificationRule.enabled.is_(True)
    )
    if to_user_id:
        query = query.where(NotificationRule.user_id == uuid.UUID(str(to_user_id)))

    created = 0
    for rule in db.scalars(query):
        state = db.get(NotificationRuleState, rule.id)
        if state is None:
            state = NotificationRuleState(rule_id=rule.id)
            db.add(state)
            db.flush()

        # 같은 키로 이미 발화했으면 보내지 않는다 — 워커 재시도로 알림이 두 번
        # 가는 것을 막는 것이 이 상태 테이블의 존재 이유다.
        if state.last_key == key:
            continue

        db.add(
            Notification(
                user_id=rule.user_id,
                rule_id=rule.id,
                event_kind=event_kind,
                title=str(payload["title"]),
                body=payload.get("body") and str(payload["body"]),
                link=payload.get("link") and str(payload["link"]),
            )
        )
        state.last_key = key
        state.last_fired_at = _now()
        state.fire_count += 1
        created += 1

    db.commit()
    return created


# --- 규칙 --------------------------------------------------------------------


def ensure_rules_for_id(db: Session, user_id: uuid.UUID) -> None:
    user = db.get(User, user_id)
    if user is None:
        return
    ensure_rules(db, user)
    db.commit()


def ensure_rules(db: Session, user: User) -> None:
    """그 사람에게 필요한 기본 규칙을 만든다.

    규칙 관리 화면은 아직 없다. 지금은 역할에 따라 자동으로 붙이고, 사용자가
    "이 알림은 그만 받고 싶다"고 할 때 화면을 만든다 — 그 전에는 켜고 끌 것이
    무엇인지도 모른다.
    """
    wanted = ["account.decided"]
    if user.is_system_admin:
        wanted.append("account.signup")
    # 장비 커넥터가 시편을 못 정한 파일은 **부서 관리자**가 붙인다(ADR 0021).
    if user.is_system_admin or permissions.is_any_manager(db, user):
        wanted.append("pipelines.needs_specimen")

    for event_kind in wanted:
        exists = db.scalar(
            select(NotificationRule).where(
                NotificationRule.user_id == user.id,
                NotificationRule.event_kind == event_kind,
                NotificationRule.channel == "inapp",
            )
        )
        if exists is None:
            db.add(NotificationRule(user_id=user.id, event_kind=event_kind, channel="inapp"))


# --- 수신함 -------------------------------------------------------------------


def list_for(db: Session, user: User, *, limit: int, offset: int) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def unread_count(db: Session, user: User) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> Notification | None:
    item = db.get(Notification, notification_id)
    if item is None or item.user_id != user.id:
        return None
    if item.read_at is None:
        item.read_at = _now()
        db.commit()
    return item


def mark_all_read(db: Session, user: User) -> int:
    items = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        )
    )
    for item in items:
        item.read_at = _now()
    if items:
        db.commit()
    return len(items)
