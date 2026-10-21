"""SP 코어 받기 작업 — 하루 한 번 저절로, 자료 관리자가 부르면 그때(ADR 0063)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.sp_core import sync

logger = logging.getLogger(__name__)


def _uuid_or_none(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


@handler(kinds.SP_CORE_PULL)
def pull(db: Session, payload: dict[str, Any]) -> None:
    """설정이 없으면 **조용히 건너뛴다** — SP 를 안 쓰는 설치도 같은 워커를 돈다."""
    if not sync.configured():
        logger.info("SP 코어 받기: SP_CORE_URL · SP_CORE_TOKEN 이 없어 건너뜁니다.")
        return
    with sync.open_client() as client:
        run = sync.pull(
            db,
            client,
            trigger=str(payload.get("trigger") or "schedule"),
            full=bool(payload.get("full")),
            requested_by_id=_uuid_or_none(payload.get("requested_by_id")),
        )
    logger.info(
        "SP 코어 받기 %s: %s",
        "끝" if run.ok else "실패",
        {slug: one.get("rows", 0) for slug, one in (run.counts or {}).items()},
    )
