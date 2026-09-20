"""「이 시편, 어느 의뢰의 것인가」 — 커넥터 수집함이 묻고 의뢰가 답한다.

## 왜

장비 커넥터가 파일을 올리면 수집함이 시편 후보를 좁혀 준다. 그런데 **그 시험이
누가 재 달라고 한 것인지**는 말해 주지 않았다. 받는 부서 사람은 파일을 시편에
붙이고 나서, 의뢰 화면으로 건너가 어느 건인지 스스로 떠올려 시험을 이어야 했다 —
그 왕복을 안 하면 의뢰는 「시험 중」 인 채로 서 있고, 진행률은 0 으로 남는다.

## 무엇을 하지 않나

**자동으로 잇지 않는다.** 여기가 하는 일은 「아마 이 건일 겁니다」 를 화면에
적는 것까지다. 잘못 이으면 의뢰가 **재지도 않은 것을 잰 것으로** 적고, 그 숫자는
낸 부서의 보고서로 간다. 커넥터의 `auto_register` 를 기본으로 안 켜 둔 것과 같은
판단이다.

잇는 것은 의뢰 화면의 「시험 연결」 이다 — 거기가 이력(`CommissionEvent`)을 남기는
유일한 자리이기도 하다.

## 모듈 경계

`pipelines` 가 `commissions` 를 부르면 안 되므로(AGENTS.md) 둘 다 여기를 본다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.commissions.models import (
    LINKABLE,
    STATUS_LABELS,
    Commission,
    CommissionItem,
)
from app.modules.materials.models import Specimen


@dataclass(frozen=True)
class Hint:
    """「이 시편은 아마 이 의뢰의 것」 한 줄."""

    commission_id: uuid.UUID
    seq: int
    title: str
    status_label: str
    item_id: uuid.UUID | None
    """시험 종류까지 맞은 항목. **비어 있을 수 있다** — 의뢰는 이 시료의 것인데
    항목의 시험 종류가 다르거나 아직 미정일 때다. 그때도 말해 주는 편이 낫다:
    사람이 항목의 종류를 정하면 바로 이어진다."""
    item_position: int | None


def for_specimens(
    db: Session,
    specimen_ids: list[uuid.UUID],
    *,
    test_type_id: uuid.UUID | None = None,
    preferred_seq: int | None = None,
) -> dict[uuid.UUID, Hint]:
    """시편 → 그 시편으로 답할 수 있는 의뢰 하나. **한 번에 읽는다**(N+1 을 안 만든다).

    고르는 규칙: 시료가 같고, 시험을 붙일 수 있는 상태이고(`LINKABLE`), 번호가
    작은 것 — 먼저 낸 것이 먼저다. 여럿이면 하나만 말한다. 화면이 「아마」 를
    말하는 자리이므로 목록을 늘어놓으면 고르는 일이 도로 사람에게 온다.
    """
    if not specimen_ids:
        return {}
    rows = db.execute(
        select(Specimen.id, Specimen.sample_id).where(Specimen.id.in_(specimen_ids))
    ).all()
    samples = {sample_id for _, sample_id in rows}
    if not samples:
        return {}

    # 종류가 맞는 항목 **또는 아직 종류를 안 정한 항목**. 뒤엣것을 빼면 「이 물성을
    # 재 달라」 만 적힌 의뢰(종류는 받는 쪽이 정한다)가 영영 안 맞는다.
    same_type: ColumnElement[bool] = CommissionItem.test_type_id.is_(None)
    if test_type_id is not None:
        same_type = or_(CommissionItem.test_type_id == test_type_id, same_type)
    found = db.execute(
        select(Commission, CommissionItem)
        .outerjoin(
            CommissionItem,
            (CommissionItem.commission_id == Commission.id) & same_type,
        )
        .where(
            Commission.sample_id.in_(samples),
            Commission.status.in_(tuple(LINKABLE)),
        )
        # 같은 의뢰 안에서는 **종류가 맞은 항목이 먼저**다 — 아직 종류를 안 정한
        # 항목이 앞에 서면, 바로 이을 수 있는 줄을 두고 못 잇는 줄을 가리킨다.
        # 커넥터가 의뢰 번호를 힌트로 줬으면(`\\의뢰-12\\`) 그 번호가 맨 앞이다 — 잇지는
        # 않는다, 먼저 보일 뿐이다.
        .order_by(
            (Commission.seq != preferred_seq) if preferred_seq is not None else Commission.seq,
            Commission.seq,
            CommissionItem.test_type_id.is_(None),
            CommissionItem.position,
        )
    ).all()
    if not found:
        return {}

    # 시료마다 하나 — 항목까지 맞은 것을 먼저 고른다. 번호 순으로 훑으므로 먼저
    # 낸 건이 이긴다.
    best: dict[uuid.UUID, Hint] = {}
    for commission, item in found:
        current = best.get(commission.sample_id)
        if current is not None and (current.item_id is not None or item is None):
            continue
        best[commission.sample_id] = Hint(
            commission_id=commission.id,
            seq=commission.seq,
            title=commission.title,
            status_label=STATUS_LABELS.get(commission.status, commission.status),
            item_id=item.id if item is not None else None,
            item_position=item.position if item is not None else None,
        )
    return {
        specimen_id: best[sample_id] for specimen_id, sample_id in rows if sample_id in best
    }
