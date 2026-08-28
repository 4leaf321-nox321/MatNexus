"""묶음 — 여러 시험을 묶어 만든 것.

**만들기와 읽기만 있다.** 고치는 길이 없는 것이 실수가 아니다 — 처리 결과와
같이 불변이다. 방법을 바꿔 다시 묶으면 새 행이 생기고, 앞의 것은 그때의 방법과
구성원을 그대로 들고 남는다. 「왜 이 값이 이래」 에 답하려면 그 스냅샷이 있어야
한다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.grouping import services
from app.modules.grouping.models import GroupResult
from app.modules.grouping.schemas import (
    GroupCreateRequest,
    GroupingParamOut,
    GroupingProducedOut,
    GroupingSpecOut,
    GroupResultOut,
)
from app.modules.materials.models import Material
from app.shared import permissions
from app.shared.auth import current_user
from app.shared.errors import NotFound
from matcore import groups

router = APIRouter(prefix="/groups", tags=["grouping"])


def _out(row: GroupResult) -> GroupResultOut:
    return GroupResultOut(
        id=row.id,
        material_id=row.material_id,
        plugin_id=row.plugin_id,
        plugin_version=row.plugin_version,
        options=row.options,
        members=row.members,
        used=row.used,
        values=row.values,
        detail=row.detail,
        warnings=row.warnings,
        note=row.note,
        created_at=row.created_at,
    )


@router.get("/kinds", response_model=list[GroupingSpecOut])
def list_kinds(
    applies_to: str | None = None,
    user: User = Depends(current_user),
) -> list[GroupingSpecOut]:
    """고를 수 있는 묶음. **레지스트리가 정한다.**

    화면이 목록을 적어 두면 새 물성을 붙일 때 화면도 고쳐야 한다 — 그게 확장이
    아닌 상태다(D7).
    """
    return [
        GroupingSpecOut(
            id=plugin.id,
            label=plugin.label,
            applies_to=list(plugin.applies_to),
            params=[
                GroupingParamOut(
                    name=item.name,
                    label=item.label,
                    type=item.type,
                    default=item.default,
                    choices=list(item.choices),
                    help=item.help,
                )
                for item in plugin.params
            ],
            makes_values=[
                GroupingProducedOut(key=item.key, label=item.label, si_unit=item.si_unit)
                for item in plugin.makes_values
            ],
        )
        for plugin in groups.groupings(applies_to)
    ]


@router.post("", response_model=GroupResultOut, status_code=201)
def create_group(
    payload: GroupCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GroupResultOut:
    """묶어서 행으로 남긴다."""
    row = services.create(
        db,
        user,
        plugin_id=payload.plugin_id,
        run_ids=payload.run_ids,
        options=payload.options,
        note=payload.note,
    )
    db.commit()
    return _out(row)


@router.get("/materials/{material_id}", response_model=list[GroupResultOut])
def list_for_material(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[GroupResultOut]:
    """그 재료의 묶음. 최근 것부터."""
    # 재료를 볼 수 있는 사람만 그 묶음을 본다. **판정은 `shared` 하나뿐이다** —
    # 모듈마다 제 버전을 두면 「재료는 보이는데 그 묶음은 안 보인다」 가 난다.
    visible = db.scalar(
        permissions.visible_materials(db, user).where(Material.id == material_id)
    )
    if visible is None:
        raise NotFound("MNX-GROUPING-0003", "재료를 찾을 수 없습니다.")
    return [_out(row) for row in services.of_material(db, material_id)]
