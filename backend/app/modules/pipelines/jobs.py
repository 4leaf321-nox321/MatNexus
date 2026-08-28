"""장비 커넥터 작업 핸들러 — 수집함 항목 읽기."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.pipelines import services


@handler(kinds.PIPELINES_PARSE_INBOX)
def parse_inbox(db: Session, payload: dict[str, Any]) -> None:
    services.process(db, uuid.UUID(str(payload["item_id"])))
