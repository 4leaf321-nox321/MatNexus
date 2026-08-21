"""주기 작업 — **워커가 스스로 넣는다.**

지금까지 작업은 전부 요청이 넣었다(업로드하면 파싱, 가입하면 알림). 그런데
"저절로 돌아야 하는 것" 이 생겼다 — 어긋남 점검이다. 사람이 누를 때만 도는
점검으로는 "한 릴리스 동안 0" 을 답할 수 없다.

**메모리에 시각을 들고 있지 않는다.** 워커는 콘솔 앱이라 자주 껐다 켜진다(D9).
메모리에 두면 재기동마다 처음부터 돌고, 하루에 열 번 켜면 열 번 돈다. 대신
**큐에 이미 있는지 물어본다** — 마지막으로 넣은 시각이 곧 상태다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.jobs.models import Job

#: (작업 종류, 간격 초). 여기 한 줄을 더하면 워커가 알아서 넣는다.
#:
#: 6시간인 이유: 어긋남은 며칠 단위로 보는 것이라 분 단위로 볼 이유가 없고,
#: 점검이 전 표를 훑으므로 자주 돌리면 그것대로 비용이다.
PERIODIC: tuple[tuple[str, int], ...] = ((kinds.VOCABULARY_CHECK_DRIFT, 6 * 3600),)


def enqueue_due(db: Session) -> list[str]:
    """돌 때가 된 주기 작업을 넣는다. 넣은 종류를 돌려준다.

    **커밋은 호출부가 한다** — `enqueue` 와 같은 규칙이다.
    """
    added: list[str] = []
    now = datetime.now(UTC)
    for kind, every in PERIODIC:
        last = db.scalar(select(func.max(Job.created_at)).where(Job.kind == kind))
        if last is not None and now - last < timedelta(seconds=every):
            continue
        # 재시도를 안 한다. 다음 주기에 어차피 다시 돈다 — 실패한 점검을 30초
        # 뒤에 또 하는 것보다 6시간 뒤에 하는 편이 맞다.
        queue.enqueue(db, kind=kind, max_attempts=1)
        added.append(kind)
    return added
