"""시험 작업 핸들러 — 파싱과 오펀 정리.

모듈이 자기 핸들러를 갖는다. 다른 모듈은 `app.jobs.kinds` 의 이름만 알면 된다.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.tests import services

logger = logging.getLogger(__name__)


@handler(kinds.TESTS_PARSE_UPLOAD)
def parse_upload(db: Session, payload: dict[str, Any]) -> None:
    services.parse_run(db, uuid.UUID(str(payload["test_run_id"])))


@handler(kinds.TESTS_CLEANUP_STORAGE)
def cleanup_storage(db: Session, payload: dict[str, Any]) -> None:
    """기본은 `dry_run`. 지우려면 payload 에 명시적으로 false 를 넣어야 한다.

    실수로 큐에 들어간 작업이 파일을 지우는 일이 없도록, 위험한 쪽을 기본값으로
    두지 않는다.
    """
    retention = payload.get("retention_days")
    result = services.cleanup_storage(
        db,
        dry_run=bool(payload.get("dry_run", True)),
        retention_days=int(retention) if retention is not None else None,
    )
    if result["dry_run"] and result["reclaimable_bytes"]:
        logger.warning(
            "정리할 것이 %.2fMB 있습니다 (오펀 %d · 미완성 %d · 보존만료 %d) — "
            "지우려면 dry_run=false 로 다시 넣으세요",
            result["reclaimable_bytes"] / (1024 * 1024),
            len(result["orphans"]),
            len(result["incomplete"]),
            len(result["expired"]),
        )
