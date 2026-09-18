"""측정 의뢰 모듈의 작업 처리.

**기한을 워커가 본다.** `due_on` 은 v1.230 부터 받아 뒀는데 아무도 안 읽었다 —
기한은 지나고 나서야 문제가 되는 종류의 값이라, 화면에 적어 두는 것만으로는 아무
일도 안 일어난다. 의뢰 목록을 매일 여는 사람이 없기 때문이다.

하루 한 번 훑어 **받는 쪽**(담당자, 없으면 받는 부서 관리자)에게 한 통으로 묶어
말한다. 낸 사람에게는 안 보낸다 — 낸 사람이 할 수 있는 일이 없다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.commissions import services

logger = logging.getLogger(__name__)


@handler(kinds.COMMISSIONS_DUE_SOON)
def due_soon(db: Session, payload: dict[str, Any]) -> None:
    """기한이 사흘 안으로 다가왔거나 지난 의뢰를 맡은 사람에게 알린다."""
    sent = services.notify_due_soon(db)
    db.commit()
    if sent:
        logger.info("의뢰 기한 알림: %s명에게 보냈습니다.", sent)
