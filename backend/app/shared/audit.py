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
from app.shared.request_context import get_client, get_request_id

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
GROUP_RESULT_DELETED = "group_result.deleted"
#: 처리 결과를 **실제로 지운** 일. 결과는 되살릴 수 없고(휴지통이 없다) 그 값이
#: 이미 보고서에 실렸을 수 있다 — 「그 값이 어디 갔나」 에 답할 자리가 여기다.
PROCESSING_RESULT_DELETED = "processing_result.deleted"
#: 장비를 **실제로 지운** 일. 폐기(`status`)는 여기 안 남긴다 — 그건 되돌릴 수
#: 있고 행도 살아 있다. 실삭제는 되돌릴 수 없으므로 누가 언제 왜 지웠는지가
#: 반년 뒤에 물어질 수 있는 유일한 자리다.
EQUIPMENT_DELETED = "equipment.deleted"
#: **사람이 아닌 것이 값을 고친 일.** 값 수정은 원래 감사 대상이 아니다(위의
#: 규칙: 되돌릴 수 없거나 권한이 실린 것만) — 화면에서 사람이 고친 것은 지금도
#: 안 남긴다. 그런데 MCP 가 생기고 나서 「이 값을 사람이 넣었나 AI 가 넣었나」
#: 라는 질문이 새로 생겼고, 그것이 이 규칙에서 유일하게 예외가 될 만한 질문이다.
#:
#: 실측(2026-09-10): 진짜 AI 세션에 「문헌값을 사내 재료에 담아 달라」 고 했더니
#: 9건을 담았는데, 남은 흔적은 `updated_at` 하나뿐이었다. 값 자체에는 출처가
#: 붙지만(`source: literature`) **누가 담았는지는 어디에도 없었다.** 반년 뒤에
#: 물어질 질문은 「이 값 어디서 났나」 가 아니라 「이거 사람이 확인한 거 맞나」 다.
VALUES_CHANGED_BY_CLIENT = "values.changed_by_client"
LOGIN_THROTTLED = "auth.login_throttled"
"""같은 계정의 실패가 문턱을 넘어 응답을 늦추기 시작했다. 실패마다 남기면 넘치므로
문턱을 넘는 순간 한 번만."""
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
        # **어느 길로 들어왔나.** 화면이면 빈 값, AI 면 `mcp`.
        client=get_client(),
    )
    db.add(entry)
    return entry
