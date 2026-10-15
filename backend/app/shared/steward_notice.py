"""자료 관리자에게 알린다 — 확정 · 승인 요청, 그리고 AI 가 한 확정 · 채택(2026-10-15).

**상태만 두면 아무도 모른다.** 확정 대기 카드는 홈의 숫자로만 보였고, 승인 대기 값은 그
화면을 열어야 보였다. AI 가 확인 없이 확정해도(ADR 0061 의 남은 위험) 감사 표를 열어 보기
전에는 드러나지 않았다. 여기는 그 셋을 **사람에게 가는 말**로 바꾼다.

알림 모듈의 함수는 다른 모듈이 못 부른다(모듈끼리 직접 부르지 않는다) — 측정 의뢰처럼 큐에
직접 넣는다(`kinds.NOTIFY_DELIVER`). 받는 사람은 자료 관리자, 없으면 시스템 관리자
(`permissions.data_steward_names` 와 같은 규칙 — 빈 목록은 답이 아니다). 실제로 받으려면 그
사람에게 그 사건의 규칙이 있어야 하고, 규칙은 `notifications.services.wanted_kinds` 가 자료
관리자 · 시스템 관리자에게 만든다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.modules.accounts.models import User

REVIEW_REQUESTED = "review.requested"
AI_CONFIRMED = "ai.confirmed"

#: 들어온 길의 이름 — `request_context.KNOWN_CLIENTS` 와 같은 키.
_CLIENT_NAMES = {"mcp": "AI(MCP)", "pylon": "MatPylon", "script": "스크립트"}


def client_label(client: str) -> str:
    return _CLIENT_NAMES.get(client, client)


def steward_ids(db: Session) -> list[uuid.UUID]:
    """받을 사람 — 자료 관리자. 한 명도 없으면 시스템 관리자."""
    active = (User.deleted_at.is_(None), User.status == "active")
    found = list(db.scalars(select(User.id).where(User.is_data_manager.is_(True), *active)))
    if found:
        return found
    return list(db.scalars(select(User.id).where(User.is_system_admin.is_(True), *active)))


def notify_stewards(
    db: Session,
    *,
    event_kind: str,
    key: str,
    title: str,
    body: str | None,
    link: str | None,
    exclude: uuid.UUID | None = None,
) -> int:
    """자료 관리자마다 하나씩 큐에 넣는다. 넣은 수를 돌려준다. **커밋은 부르는 쪽이 한다.**

    `exclude` — 부탁한 사람이 자료 관리자라도 자기에게는 안 보낸다. AI 가 한 일은 토큰 주인
    에게도 보낸다(제 AI 가 무엇을 했는지 알아야 한다) — 그래서 그때는 비워 둔다.
    `key` 는 중복을 막는다(워커가 같은 키를 두 번 보내지 않는다).
    """
    sent = 0
    for user_id in steward_ids(db):
        if user_id == exclude:
            continue
        queue.enqueue(
            db,
            kind=kinds.NOTIFY_DELIVER,
            payload={
                "event_kind": event_kind,
                "key": key,
                "title": title,
                "body": body,
                "link": link,
                "to_user_id": str(user_id),
            },
        )
        sent += 1
    return sent
