"""휴지통 — 지운 것을 보고, 되살리고, 영영 지운다.

## 시스템 관리자만

되살리기는 **남의 부서 데이터까지 건드리는 일**이다. 재료는 전역일 수 있고, 그
아래에는 여러 부서의 시료가 매달린다 — 부서 관리자에게 열면 소관 밖을 되살리게
된다. 감사 화면이 「부서 관리자는 자기 부서 것만」 인 것과 다른 판단인데, 그쪽은
읽기이고 이쪽은 쓰기다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.trash import services
from app.modules.trash.schemas import (
    TrashDoneOut,
    TrashItemOut,
    TrashPurgedManyOut,
    TrashPurgeManyIn,
)
from app.shared.auth import require_system_admin
from app.shared.errors import AppError
from app.shared.pagination import clamp_limit

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get("", response_model=list[TrashItemOut])
def list_trash(
    kind: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[TrashItemOut]:
    """지운 것. **최근에 지운 것부터.**

    줄마다 「되살리면 무엇이 함께 오는가」 와 「왜 못 되살리는가」 를 함께 낸다 —
    화면이 그것을 스스로 세게 하면 사람이 본 숫자와 실제가 어긋난다.
    """
    return [
        TrashItemOut(
            kind=item.kind,
            kind_label=item.kind_label,
            id=item.id,
            name=item.name,
            deleted_at=item.deleted_at,
            workspace_id=item.workspace_id,
            below=item.below,
            blocked=item.blocked,
        )
        for item in services.listing(db, kind=kind, limit=clamp_limit(limit))
    ]


@router.post("/{kind}/{item_id}/restore", response_model=TrashDoneOut)
def restore(
    kind: str,
    item_id: uuid.UUID,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TrashDoneOut:
    """되살린다 — 이 행과 그 아래 **함께 지워진** 것 전부."""
    done = services.restore(db, kind, item_id, actor=user)
    db.commit()
    return TrashDoneOut(name=done.name, counts=done.counts, said=done.said)


@router.delete("/{kind}/{item_id}", response_model=TrashDoneOut)
def purge(
    kind: str,
    item_id: uuid.UUID,
    confirm: bool = Query(default=False),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TrashDoneOut:
    """영영 지운다. **되돌릴 수 없다.**

    `confirm=true` 를 받아야 지운다. 창에서 한 번 물었더라도 서버가 다시 받는
    이유는, 이 길이 API 로도 열려 있기 때문이다 — 스크립트가 실수로 부르면 그
    데이터는 돌아오지 않는다.
    """
    if not confirm:
        raise AppError(
            "MNX-TRASH-0005",
            "영구 삭제는 되돌릴 수 없습니다. confirm=true 를 함께 보내세요.",
            status=422,
        )
    done = services.purge(db, kind, item_id, actor=user)
    db.commit()
    return TrashDoneOut(name=done.name, counts=done.counts, said=done.said)


@router.post("/purge", response_model=TrashPurgedManyOut)
def purge_many(
    payload: TrashPurgeManyIn,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TrashPurgedManyOut:
    """고른 줄을 한꺼번에 영영 지운다. **되돌릴 수 없다.**

    화면이 하나씩 부르지 않는 이유는 **겹쳐 고르는 것** 때문이다 — 재료와 그
    아래 시료를 함께 고르면 두 번째 요청이 「없는 행」 으로 터지는데, 그때
    앞엣것은 이미 지워져 있다. 서버가 계층 위부터 지우고 딸려 사라진 것은
    건너뛴다.
    """
    if not payload.confirm:
        raise AppError(
            "MNX-TRASH-0005",
            "영구 삭제는 되돌릴 수 없습니다. confirm=true 를 함께 보내세요.",
            status=422,
        )
    done = services.purge_many(db, [(one.kind, one.id) for one in payload.items], actor=user)
    db.commit()
    return TrashPurgedManyOut(
        requested=done.requested,
        purged=done.purged,
        skipped=done.skipped,
        counts=done.counts,
        said=done.said,
    )
