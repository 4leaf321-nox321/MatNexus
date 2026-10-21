"""적용 부품 — 재료가 쓰이는 부품 줄의 창구(ADR 0064).

    GET  /materials/{id}/parts                 줄 — 찾기 · 사업부 · 제품 거르기 · 쪽
    POST /materials/{id}/parts                 넣기 — 미리보기가 기본(붙여넣기 · 한 줄 추가)
    PATCH /materials/{id}/parts/{part_id}      고치기 — 보낸 칸만
    POST /materials/{id}/parts/remove          지우기
    POST /materials/parts/bom                  BOM 가져오기 — 재질로 재료를 찾아 재료마다
    넣는다

재료 라우트(`routes.py`)가 이미 커서 따로 둔다. 판정은 같다 — 넣기 · 고치기 · 지우기는 **그
재료를
고칠 수 있는 사람**(`permissions.require_edit`, ADR 0035).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.materials import parts, services
from app.modules.materials.models import MaterialPart
from app.modules.materials.schemas import (
    BomPartImportOut,
    BomPartImportRequest,
    BomPartMaterialOut,
    BomPartRowOut,
    MaterialPartAddRequest,
    MaterialPartOut,
    MaterialPartPage,
    MaterialPartPlanOut,
    MaterialPartRemoveOut,
    MaterialPartRemoveRequest,
    MaterialPartUpdate,
    PartFacetOut,
)
from app.shared import permissions, semantic
from app.shared.auth import current_user
from app.shared.errors import NotFound

router = APIRouter(prefix="/materials", tags=["materials"])

_CODE = "MNX-MATERIALS-0034"
#: 목록 엔드포인트의 상한(AGENTS — 서버가 강제한다).
PAGE_MAX = 200


def _out(row: MaterialPart, names: dict[uuid.UUID, str]) -> MaterialPartOut:
    return MaterialPartOut(
        id=row.id,
        part=row.part_name,
        product=row.product_name,
        part_code=row.part_code,
        division=row.division_name,
        source=row.source,
        source_ref=row.source_ref,
        note=row.note,
        position=row.position,
        created_by=names.get(row.created_by_id) if row.created_by_id else None,
        created_at=row.created_at,
    )


def _names(db: Session, rows: list[MaterialPart]) -> dict[uuid.UUID, str]:
    ids = {row.created_by_id for row in rows if row.created_by_id}
    if not ids:
        return {}
    return {
        one.id: one.display_name for one in db.scalars(select(User).where(User.id.in_(ids)))
    }


@router.post("/parts/bom", response_model=BomPartImportOut)
def import_bom(
    payload: BomPartImportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BomPartImportOut:
    """BOM 표 → 재료마다 적용 부품 줄. **기본이 미리보기다.**

    재질 글자로 재료를 찾는다(BOM 덱이 기억한 짝 → 이름 → 별칭 → Grade). 못 찾았거나 여럿에
    맞은
    재질은 그 줄을 이유와 함께 남긴다 — 사람이 고른 짝(`choices`)을 실어 다시 부른다. 고칠
    권한이
    없는 재료의 줄도 남긴다. **나머지는 넣는다** — 300줄 BOM 의 재질 하나 때문에 전부를 다시
    고르게 하지 않는다. 판정은 줄마다 `editor.allows`(재료를 고칠 수 있는 사람)."""
    rows, groups = parts.plan_bom(
        db,
        user,
        [one.model_dump() for one in payload.rows],
        division=payload.division,
        choices=payload.choices,
    )
    if not payload.dry_run:
        parts.apply_bom(db, user, groups, source_ref=payload.source_ref)
        semantic.queue_materials(db, list(groups))
        db.commit()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return BomPartImportOut(
        applied=not payload.dry_run,
        counts=counts,
        materials=[
            BomPartMaterialOut(
                id=material.id,
                name=material.record_name,
                new=sum(1 for row, _ in items if row["status"] == "new"),
            )
            for material, items in groups.values()
        ],
        rows=[BomPartRowOut.model_validate(row) for row in rows],
    )


@router.get("/{material_id}/parts", response_model=MaterialPartPage)
def list_parts(
    material_id: uuid.UUID,
    q: str | None = Query(default=None, description="파트명 · 부품코드 · 제품 · 비고의 글자"),
    division: str | None = Query(default=None),
    product: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=PAGE_MAX),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialPartPage:
    material = services.get_material(db, user, material_id)
    rows, total, facets = parts.page(
        db,
        material.id,
        q=q,
        division=division,
        product=product,
        limit=limit,
        offset=offset,
    )
    names = _names(db, rows)
    return MaterialPartPage(
        items=[_out(row, names) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        divisions=[PartFacetOut(value=v, count=c) for v, c in facets["divisions"]],
        products=[PartFacetOut(value=v, count=c) for v, c in facets["products"]],
    )


@router.post("/{material_id}/parts", response_model=MaterialPartPlanOut)
def add_parts(
    material_id: uuid.UUID,
    payload: MaterialPartAddRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialPartPlanOut:
    """넣는다 — **기본이 미리보기다.** 줄마다 `new` · `exists` · `error`, 넣는 것은 `new`
    만."""
    material = services.get_material(db, user, material_id)
    permissions.require_edit(db, user, material, code=_CODE, note=not payload.dry_run)
    planned = parts.plan(db, material, [one.model_dump() for one in payload.lines])
    if payload.dry_run:
        return MaterialPartPlanOut(**planned.out(applied=False))
    parts.apply(
        db, user, material, planned, source=payload.source, source_ref=payload.source_ref
    )
    semantic.queue_materials(db, [material.id])
    db.commit()
    return MaterialPartPlanOut(**planned.out(applied=True))


def _row(db: Session, material_id: uuid.UUID, part_id: uuid.UUID) -> MaterialPart:
    row = db.scalar(
        select(MaterialPart).where(
            MaterialPart.id == part_id, MaterialPart.material_id == material_id
        )
    )
    if row is None:
        raise NotFound("MNX-MATERIALS-0064", "그 재료에 그런 적용 부품 줄이 없습니다.")
    return row


@router.patch("/{material_id}/parts/{part_id}", response_model=MaterialPartOut)
def update_part(
    material_id: uuid.UUID,
    part_id: uuid.UUID,
    payload: MaterialPartUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialPartOut:
    material = services.get_material(db, user, material_id)
    permissions.require_edit(db, user, material, code=_CODE)
    row = _row(db, material.id, part_id)
    changes: dict[str, Any] = {key: getattr(payload, key) for key in payload.model_fields_set}
    parts.update(db, user, row, changes)
    semantic.queue_materials(db, [material.id])
    db.commit()
    db.refresh(row)
    return _out(row, _names(db, [row]))


@router.post("/{material_id}/parts/remove", response_model=MaterialPartRemoveOut)
def remove_parts(
    material_id: uuid.UUID,
    payload: MaterialPartRemoveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialPartRemoveOut:
    material = services.get_material(db, user, material_id)
    permissions.require_edit(db, user, material, code=_CODE)
    removed = parts.remove(db, material, payload.ids)
    semantic.queue_materials(db, [material.id])
    db.commit()
    return MaterialPartRemoveOut(removed=removed)
