"""덮어쓰기를 막는다 — **낙관적 잠금.**

## 무엇을 막는가

관리자 둘이 같은 시험 종류를 연다. A 가 채널 라벨을 고치고 저장하고, B 가
(A 의 변경을 못 본 화면에서) 조건 하나를 더하고 저장한다. **A 의 변경이 흔적
없이 사라진다.**

여기서 지키는 것은 `PUT /test-types/{key}` 와 `PUT /processing/recipes/{key}`
둘뿐이다. 이 둘이 **정의를 한 벌 통째로 갈아 끼우기** 때문이다 — 뒤에 저장한
쪽이 앞을 덮는 것이 아니라 **자식까지 통째로 지운다.**

`PATCH` 는 안 건다. `exclude_unset` 이라 **안 보낸 필드는 안 바뀐다** — 서로
다른 필드를 고치는 두 사람은 애초에 안 부딪히고, 같은 필드를 고치면 그건
덮어쓰기가 아니라 그냥 나중 값이다.

## 임대(`heartbeat`)가 아니라 대조인 이유

계획서에는 `heartbeat` 로 적혀 있었다. 바꾼 이유 셋.

- 지금 문제는 *"둘이 동시에 편집하면 불편하다"* 가 아니라 **"조용히 지워진다"**
  다. 대조가 그것을 정확히 막는다
- 임대는 **살아 있는 상태**를 만든다 — 만료 정리·워커·시계 어긋남. ADR 0007 이
  *"화면은 늘 최신을 본다"* 로 잡아 둔 결의 반대다
- 부서 하나에 관리자 두셋이다. 충돌이 잦지 않으므로 **막는 것보다 알아채는
  것**이 값이 크다

## `updated_at` 이 아니라 `revision` 인 이유

실측했다(2026-08-24). `onupdate=func.now()` 는 **부모 행이 더러울 때만** 걸린다.

    ① 처음               17:38:20.239452
    ② 자식(채널)만 바꿈    17:38:20.239452   ← 안 움직였다
    ③ 부모를 바꿈         17:38:20.265544

채널 라벨만 고치는 것은 흔한 편집인데, 그때 `updated_at` 은 그대로다. 그 위에
잠금을 세우면 **바뀐 것을 안 바뀐 것으로 보고 통과시킨다.**
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry
from app.shared.errors import AppError


def _who(db: Session, target_id: uuid.UUID | None) -> str:
    """누가 언제 고쳤나. **감사 기록이 이미 답을 갖고 있다**(v1.52.0).

    409 만 던지면 사람은 새로고침하고 자기 작업을 **다시** 잃는다. 무엇이
    바뀌었는지 볼 자리를 알려 줘야 그 앞에서 판단할 수 있다.
    """
    if target_id is None:
        return ""
    entry = db.scalar(
        select(AuditEntry)
        .where(AuditEntry.target_id == target_id)
        .order_by(AuditEntry.created_at.desc())
        .limit(1)
    )
    if entry is None:
        return ""
    when = entry.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
    return (
        f" {entry.actor_label} 이 {when} 에 고쳤습니다 — "
        f"감사 기록에서 무엇이 바뀌었는지 볼 수 있습니다."
    )


def guard(
    db: Session,
    item: Any,
    expected: int,
    *,
    what: str,
    code: str,
) -> None:
    """내가 본 리비전이 아직 최신인지 본다. 아니면 **저장하지 않고 거절한다.**

    거절 메시지에 **지금 저장하면 무슨 일이 나는지**를 적는다. "충돌했습니다"
    만으로는 사람이 그냥 새로고침하고 다시 저장하는데, 그러면 남의 변경을
    지우는 것이 맞다고 생각하게 된다.
    """
    current = int(getattr(item, "revision", 1))
    if current == expected:
        return
    raise AppError(
        code,
        f"이 {what}가 그사이 바뀌었습니다 (열었을 때 {expected}, 지금 {current})."
        f"{_who(db, getattr(item, 'id', None))} "
        f"새로 고쳐서 다시 여세요 — **지금 저장하면 그 변경이 지워집니다.** "
        f"이 정의는 한 벌 통째로 갈아 끼우므로 덮는 것이 아니라 지우는 것입니다.",
        status=409,
    )


def bump(item: Any) -> None:
    """저장했으니 번호를 올린다.

    **부르는 쪽이 명시적으로 올린다.** 자동으로 만들 수도 있었지만(ORM 이벤트),
    그러면 *무엇이 바뀌면 올릴 것인가* 가 코드에서 안 보인다 — 자식만 바뀐
    경우를 놓친 것이 `updated_at` 이 못 쓰게 된 이유다.
    """
    item.revision = int(getattr(item, "revision", 1)) + 1
