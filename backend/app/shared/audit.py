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
ACCOUNT_DATA_MANAGER_CHANGED = "account.data_manager_changed"
ACCOUNT_DELETED = "account.deleted"
GROUP_RESULT_DELETED = "group_result.deleted"
#: 처리 결과를 **실제로 지운** 일. 결과는 되살릴 수 없고(휴지통이 없다) 그 값이
#: 이미 보고서에 실렸을 수 있다 — 「그 값이 어디 갔나」 에 답할 자리가 여기다.
PROCESSING_RESULT_DELETED = "processing_result.deleted"
#: 장비를 **실제로 지운** 일. 폐기(`status`)는 여기 안 남긴다 — 그건 되돌릴 수
#: 있고 행도 살아 있다. 실삭제는 되돌릴 수 없으므로 누가 언제 왜 지웠는지가
#: 반년 뒤에 물어질 수 있는 유일한 자리다.
EQUIPMENT_DELETED = "equipment.deleted"
#: **물성 데이터를 통째로 내보낸 일.** 되돌릴 수 없다 — 나간 파일은 회수가 안 되고,
#: 부서 가시성도 그 파일 안에서는 뜻이 없다. 「누가 언제 무엇을(어느 부서·곡선·문헌)
#: 뽑았나」 는 반년 뒤에 실제로 물어질 수 있는 질문이다.
DATA_EXPORTED = "data.exported"
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
#: 아래 넷은 **그 예외의 나머지 절반이다.** 값 수정만 막아 두고 카드·처리 실행·
#: 레시피·형식은 열어 뒀더니, 「AI 가 뭘 했나」 를 이 표로는 못 셌다 — 한 군데라도
#: 새면 센 숫자가 틀린 것이지 모자란 것이 아니다.
#:
#: 실측(2026-09-18): MCP 도구 61개 중 쓰는 것이 열 몇 개인데 감사에 남는 길은
#: 값 수정 하나뿐이었다. AI 가 만든 물성 카드는 사람이 만든 것과 화면에서
#: 구별되지 않았고, 그 카드가 곧 해석에 들어가는 덱이 된다.
#:
#: **화면에서 한 것은 여기 안 남는다**(`record_by_client` 가 문지기다). 사람이
#: 카드를 만드는 것은 원래 감사 대상이 아니고, 그 규칙은 그대로다.
CARD_CREATED_BY_CLIENT = "card.created_by_client"
PROCESSING_RUN_BY_CLIENT = "processing.run_by_client"
RECIPE_SAVED_BY_CLIENT = "recipe.saved_by_client"
FORMAT_SAVED_BY_CLIENT = "format.saved_by_client"
#: **그러고도 샜던 자리**(2026-09-25). MCP 쓰기 도구를 경로마다 감사와 맞대 보니 재료·
#: 시료·시편 등록, 문헌 카탈로그 쓰기, 측정 의뢰 작성이 아무 흔적도 안 남겼다 — AI 가
#: 문헌 값을 지어 넣어도 사람이 넣은 값과 구별할 길이 없었다(등록자 칸은 토큰 주인이다).
#: 새 쓰기 도구가 다시 새지 않게 `tests/architecture/test_mcp_writes_audited.py` 가 본다.
MATERIAL_CREATED_BY_CLIENT = "material.created_by_client"
SAMPLE_CREATED_BY_CLIENT = "sample.created_by_client"
SPECIMEN_CREATED_BY_CLIENT = "specimen.created_by_client"
CATALOG_PROPERTY_CREATED_BY_CLIENT = "catalog_property.created_by_client"
CATALOG_PROPERTY_DEPRECATED_BY_CLIENT = "catalog_property.deprecated_by_client"
CATALOG_MATERIAL_CREATED_BY_CLIENT = "catalog_material.created_by_client"
CATALOG_VALUE_ADDED_BY_CLIENT = "catalog_value.added_by_client"
COMMISSION_CREATED_BY_CLIENT = "commission.created_by_client"
#: 문헌 값을 **실제로 지운** 일과 폐기된 키의 값을 **옮긴** 일. 둘 다 되돌릴 수 없어
#: 위의 규칙대로 사람이 해도 남긴다(누가 했든 `client` 가 길을 말한다) — 지운 값은 이미
#: 덱에 실렸을 수 있고, 옮긴 값은 원래 어느 키에 있었는지가 이 기록에만 남는다.
CATALOG_VALUE_DELETED = "catalog_value.deleted"
CATALOG_PROPERTY_MIGRATED = "catalog_property.migrated"
LOGIN_THROTTLED = "auth.login_throttled"
"""같은 계정의 실패가 문턱을 넘어 응답을 늦추기 시작했다. 실패마다 남기면 넘치므로
문턱을 넘는 순간 한 번만."""
#: 휴지통에서 되살리거나 영영 지운 일. **삭제와 짝이다** — 지운 기록만 남고
#: 되살린 기록이 없으면, 지금 살아 있는 행이 왜 살아 있는지 설명이 안 된다.
TRASH_RESTORED = "trash.restored"
TRASH_PURGED = "trash.purged"
VOCABULARY_RENAMED = "vocabulary.renamed"
TEST_TYPE_CHANGED = "test_type.changed"
#: 마이그레이션이 남기는 둘(ADR 0035). 코드는 이 값을 쓰지 않는다 — 감사 화면에서
#: 무엇을 찾아야 하는지 여기 적어 둔다. 앞의 것은 겹친 정의 key 를 바꾼 일(주소가
#: 바뀐다), 뒤의 것은 부서 열람 제한이 켜져 있던 부서(지우면 어느 부서였는지 사라진다).
DEFINITION_KEY_RENAMED = "definition.key_renamed"
WORKSPACE_RESTRICTION_REMOVED = "workspace.restriction_removed"
#: 등록자·편집 부서를 넘긴 일(ADR 0035). **권한이 실린 변경이다** — 넘긴 뒤에는
#: 「등록자」 칸이 새 사람을 가리키므로, 처음 올린 사람은 이 기록에만 남는다.
OWNERSHIP_CHANGED = "ownership.changed"


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


def record_by_client(
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
) -> AuditEntry | None:
    """**사람이 아닌 길로 들어온 쓰기만** 남긴다. 화면에서 한 것이면 아무것도 안 남는다.

    묻는 자리를 하나로 둔다. 라우트마다 `if get_client():` 를 손으로 적으면, 새
    쓰기가 생겼을 때 그 한 줄을 빠뜨린 자리만 조용히 안 남는다 — 감사에서 조용한
    구멍은 없는 것보다 나쁘다. 「AI 는 아무것도 안 했다」 로 읽히기 때문이다.
    """
    if not get_client():
        return None
    return record(
        db,
        action=action,
        actor=actor,
        target_table=target_table,
        target_id=target_id,
        target_label=target_label,
        workspace_id=workspace_id,
        changes=changes,
        reason=reason,
    )
