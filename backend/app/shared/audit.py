"""감사 기록을 남기는 **한 곳.**

오류 규약이 *"오류 본문을 라우트에서 직접 만들지 않는다 — `AppError` 를 raise
한다. 응답을 만드는 경로가 곧 로그를 남기는 경로여야 한다"* 라고 정했다. 같은
이유로 감사도 한 곳을 거친다. 라우트마다 손으로 만들면 어떤 곳은 사유를 빼먹고
어떤 곳은 대상 이름을 안 박고, 나중에 그 차이를 메울 방법이 없다.

## 무엇을 남기나

**되돌릴 수 없거나 권한이 실린 것**만이다. 값 하나 고친 것까지 남기면 그 안에서
정작 찾을 것을 못 찾는다.

## 커밋은 부르는 쪽이 한다

여기서 `commit` 하지 않는다. 감사 기록은 **그 변경과 같은 트랜잭션**에 있어야
한다 — 변경은 됐는데 기록이 없거나, 기록은 있는데 변경이 롤백되는 상태를 안
만든다.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.shared.request_context import get_request_id

#: 남기는 일. **과거형으로 적는다** — 일어난 일의 기록이지 명령이 아니다.
#:
#: 새 항목을 더할 때는 "이걸 반년 뒤에 누가 찾을까" 를 먼저 묻는다. 답이 없으면
#: 안 넣는 편이 낫다.
CARD_PUBLISHED = "card.published"
CARD_DEPRECATED = "card.deprecated"
CARD_RESTORED = "card.restored"
WORKSPACE_MERGED = "workspace.merged"
CARD_DELETED = "card.deleted"
MATERIAL_DELETED = "material.deleted"
TEST_RUN_DELETED = "test_run.deleted"
TEST_RUN_UPDATED = "test_run.updated"
ACCOUNT_DECIDED = "account.decided"
ACCOUNT_SUSPENDED = "account.suspended"
ACCOUNT_HOME_CHANGED = "account.home_changed"
ACCOUNT_ADMIN_CHANGED = "account.admin_changed"
ACCOUNT_DELETED = "account.deleted"
#: 휴지통에서 되살리거나 영영 지운 일. **삭제와 짝이다** — 지운 기록만 남고
#: 되살린 기록이 없으면, 지금 살아 있는 행이 왜 살아 있는지 설명이 안 된다.
TRASH_RESTORED = "trash.restored"
TRASH_PURGED = "trash.purged"
VOCABULARY_RENAMED = "vocabulary.renamed"
TEST_TYPE_CHANGED = "test_type.changed"


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """바뀐 것만 남긴다.

    통째로 스냅샷하면 표가 커지고 **무엇이 바뀌었는지는 오히려 안 보인다.** 안
    바뀐 값 스무 개 사이에서 바뀐 하나를 찾게 된다.
    """
    return {
        key: {"before": before.get(key), "after": after[key]}
        for key in after
        if before.get(key) != after[key]
    }


def record(
    db: Session,
    *,
    action: str,
    actor: User | None,
    target_table: str,
    target_id: uuid.UUID | None,
    target_label: str,
    workspace_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditEntry:
    """감사 기록 하나. **부르는 쪽이 커밋한다.**

    `actor` 가 없을 수 있다(시스템이 한 일). 그때도 남긴다 — 안 남기면 "아무도
    안 했는데 바뀌었다" 가 되고, 그것이 가장 설명하기 어려운 상태다.
    """
    entry = AuditEntry(
        action=action,
        actor_id=actor.id if actor else None,
        # **그때의 이름을 박는다.** 계정이 지워지면 누가 했는지 모르게 되는데,
        # 그건 감사 로그가 존재하는 이유와 정면으로 어긋난다.
        actor_label=(actor.display_name or actor.email) if actor else "시스템",
        target_table=target_table,
        target_id=target_id,
        target_label=target_label[:300],
        workspace_id=workspace_id,
        changes=changes or {},
        reason=reason,
        # 접근 로그·파일 로그와 잇는 끈. 이 값으로 그 요청의 전말을 볼 수 있다.
        request_id=get_request_id(),
    )
    db.add(entry)
    return entry
