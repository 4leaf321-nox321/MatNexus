"""알림 작업 핸들러.

모듈이 자기 핸들러를 갖는다 — 작업 종류가 늘 때 워커나 공용 파일을 고치지 않고
그 모듈 안에서 끝난다. 다른 모듈은 `app.jobs.kinds` 의 이름만 알면 된다.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.notifications import services

logger = logging.getLogger(__name__)


@handler(kinds.NOTIFY_DELIVER)
def deliver_notifications(db: Session, payload: dict[str, Any]) -> None:
    created = services.deliver(db, payload)
    logger.info("알림 %s건 생성 (%s)", created, payload.get("event_kind"))


@handler(kinds.NOTIFY_ENSURE_RULES)
def ensure_rules(db: Session, payload: dict[str, Any]) -> None:
    services.ensure_rules_for_id(db, uuid.UUID(str(payload["user_id"])))
