"""어휘 모듈의 작업 처리.

**점검을 워커가 돌린다.** 사람이 누를 때만 도는 점검으로는 "한 릴리스 동안 0"
(ADR 0010 Contract 4-2 의 조건)을 답할 수 없다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.vocabulary import services

logger = logging.getLogger(__name__)


@handler(kinds.VOCABULARY_CHECK_DRIFT)
def check_drift(db: Session, payload: dict[str, Any]) -> None:
    """문자열 컬럼과 어휘가 같은 말을 하는지 재고 남긴다.

    **벌어졌으면 로그로 크게 말한다.** 관리 화면을 매일 보는 사람은 없다.
    """
    row = services.record_check(db, source="worker")
    db.commit()
    if not row.total:
        logger.info("어긋남 점검: 0건")
        return
    logger.warning(
        "어긋남 점검: %s건이 벌어졌습니다 — %s. 어휘 화면에서 고치세요.",
        row.total,
        ", ".join(f"{item['table']}.{item['field']} {item['count']}건" for item in row.detail),
    )
