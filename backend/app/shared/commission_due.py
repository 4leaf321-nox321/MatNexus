"""측정 의뢰의 **기한 임박** — 누가 봐야 하나 (2026-10-03 에 `commissions/services` 에서 옮김).

알림(`commissions.services.notify_due_soon`, 하루 한 번)과 홈의 「기한 임박 n」 이 **같은 줄을
센다.** 둘이 따로 세면 알림은 왔는데 홈에는 0 이거나 그 반대가 된다 — 통계 모듈은 의뢰
모듈을 직접 부르지 않으므로(모듈 경계) 규칙을 여기 둔다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.commissions.models import Commission
from app.modules.workspaces.models import WorkspaceMember

#: 기한을 며칠 앞두고 말하는가. 하루면 이미 늦고(시료를 받아 시험을 거는 데 하루로는
#: 모자란다), 일주일이면 매일 오는 잔소리가 되어 사람이 알림 자체를 끈다.
DUE_SOON_DAYS = 3

#: 기한이 뜻을 잃은 상태. 아직 안 낸 것(`draft`)·끝난 것·반려된 것에 기한을 말하면
#: **알림이 틀린 말을 하는 것**이고, 한 번 그러면 다음 알림도 안 읽힌다.
DUE_QUIET_STATUSES = frozenset({"draft", "delivered", "closed", "rejected"})


def today() -> date:
    """기한을 견줄 「오늘」 — 이 서버의 **현지** 날짜.

    `due_on` 은 사람이 현지 달력에서 고른 날이다. 전에는 UTC 날짜로 견줘, 한국에서는 아침
    9시 전까지 어제였다 — 그 사이 「오늘까지」 가 「내일까지」 로, 지난 기한이 안 지난
    것으로 보였다(2026-10-04).
    """
    return datetime.now().astimezone().date()


def due_soon(db: Session, *, today: date) -> dict[uuid.UUID, list[Commission]]:
    """기한이 다가왔거나 지난 의뢰 → **말할 사람별로.**

    받을 사람은 **받는 쪽**이다. 담당자가 정해졌으면 그 사람, 아직이면 받는 부서
    관리자 전원 — 담당자가 없다는 것은 아무도 안 맡았다는 뜻이고, 그때야말로 기한이
    조용히 지나간다.

    낸 사람에게는 안 보낸다. 낸 사람이 할 수 있는 일이 없기 때문이다 — 재촉은
    알림이 아니라 말로 하는 것이고, 그 화면에는 이미 기한이 보인다.
    """
    rows = list(
        db.scalars(
            select(Commission).where(
                Commission.due_on.is_not(None),
                Commission.due_on <= today + timedelta(days=DUE_SOON_DAYS),
                Commission.status.not_in(tuple(DUE_QUIET_STATUSES)),
            )
        )
    )
    if not rows:
        return {}

    # 담당자 없는 건의 받는 부서 관리자 — **한 번에 읽는다**(건마다 물으면 N+1).
    unassigned = {one.lab_workspace_id for one in rows if one.assignee_id is None}
    managers: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if unassigned:
        found = db.execute(
            select(WorkspaceMember.workspace_id, WorkspaceMember.user_id).where(
                WorkspaceMember.workspace_id.in_(unassigned),
                WorkspaceMember.role == "manager",
            )
        ).all()
        for workspace_id, user_id in found:
            managers[workspace_id].append(user_id)

    made: dict[uuid.UUID, list[Commission]] = defaultdict(list)
    for one in rows:
        targets = (
            [one.assignee_id]
            if one.assignee_id is not None
            else managers.get(one.lab_workspace_id, [])
        )
        for user_id in targets:
            made[user_id].append(one)
    return {user_id: sorted(items, key=_due_key) for user_id, items in made.items()}


def _due_key(item: Commission) -> tuple[date, int]:
    """급한 것부터 — 같은 날이면 번호 순."""
    assert item.due_on is not None
    return (item.due_on, item.seq)
