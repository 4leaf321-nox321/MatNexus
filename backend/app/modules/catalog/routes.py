"""물성 카탈로그 읽기 — **쓰는 길은 API 에 없다.**

카탈로그 데이터는 이관 스크립트(`scripts/import_materialtwin.py`)로만 들어온다
(ADR 0027). 화면에서 값을 만들거나 고칠 수 있으면 「출처+등급이 붙은 채굴
데이터」 라는 성격이 무너진다 — 사내 실측은 시험→처리→카드 경로가 따로 있다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.schemas import (
    CatalogMaterialDetailOut,
    CatalogMaterialOut,
    CatalogMaterialPage,
    CatalogSourceOut,
    CatalogSummaryOut,
    CatalogValueOut,
)
from app.shared.auth import current_user
from app.shared.errors import NotFound
from app.shared.pagination import clamp_limit

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/summary", response_model=CatalogSummaryOut)
def summary(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> CatalogSummaryOut:
    """전체 규모와 패싯 분포 — 목록 화면의 필터 축이 여기서 나온다."""

    def counted(column: Any) -> dict[Any, int]:
        rows = db.execute(
            select(column, func.count()).select_from(column.class_).group_by(column)
        )
        return {key if key is not None else "": count for key, count in rows}

    domains: dict[str, int] = {
        domain: count
        for domain, count in db.execute(
            select(CatalogDefinition.domain, func.count(CatalogValue.id))
            .join(CatalogValue, CatalogValue.property_key == CatalogDefinition.key)
            .group_by(CatalogDefinition.domain)
        )
    }
    return CatalogSummaryOut(
        materials=db.scalar(select(func.count()).select_from(CatalogMaterial)) or 0,
        values=db.scalar(select(func.count()).select_from(CatalogValue)) or 0,
        sources=db.scalar(select(func.count()).select_from(CatalogSource)) or 0,
        definitions=db.scalar(select(func.count()).select_from(CatalogDefinition)) or 0,
        subsystems=counted(CatalogMaterial.subsystem),
        categories=counted(CatalogMaterial.category),
        domains=domains,
        tiers=counted(CatalogValue.quality_tier),
    )


@router.get("/materials", response_model=CatalogMaterialPage)
def list_materials(
    q: str | None = Query(default=None),
    subsystem: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CatalogMaterialPage:
    """카탈로그 재료 목록. 물성 많은 순 — 쓸 것이 많은 재료가 먼저다."""
    conditions: list[ColumnElement[bool]] = []
    if q:
        conditions.append(CatalogMaterial.name.ilike(f"%{q}%"))
    if subsystem is not None:
        # 빈 문자열은 「미분류」 를 뜻한다 — 분류 안 된 것을 찾는 것도 일이다.
        conditions.append(
            CatalogMaterial.subsystem.is_(None)
            if subsystem == ""
            else CatalogMaterial.subsystem == subsystem
        )
    if category:
        conditions.append(CatalogMaterial.category == category)

    value_count = (
        select(func.count())
        .select_from(CatalogValue)
        .where(CatalogValue.material_id == CatalogMaterial.id)
        .scalar_subquery()
    )
    base = select(CatalogMaterial, value_count.label("value_count")).where(*conditions)
    total = (
        db.scalar(select(func.count()).select_from(CatalogMaterial).where(*conditions)) or 0
    )
    limit = clamp_limit(limit)
    rows = db.execute(
        base.order_by(value_count.desc(), CatalogMaterial.name).limit(limit).offset(offset)
    ).all()
    return CatalogMaterialPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            CatalogMaterialOut.model_validate(
                {**one.__dict__, "value_count": count}, from_attributes=False
            )
            for one, count in rows
        ],
    )


@router.get("/materials/{material_id}", response_model=CatalogMaterialDetailOut)
def get_material(
    material_id: uuid.UUID,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CatalogMaterialDetailOut:
    """재료 하나의 모든 물성값 — 값·조건·등급·출처가 한 줄이다.

    **후보를 숨기지 않는다.** 같은 물성에 값이 여럿이면 전부 준다 — 어느 것을
    대표로 볼지는 화면(다음 단계)이 이유와 함께 보여 준다.
    """
    item = db.get(CatalogMaterial, material_id)
    if item is None:
        raise NotFound("MNX-CATALOG-0001", "카탈로그에 없는 재료입니다.")

    rows = db.execute(
        select(CatalogValue, CatalogDefinition, CatalogSource)
        .join(CatalogDefinition, CatalogDefinition.key == CatalogValue.property_key)
        .outerjoin(CatalogSource, CatalogSource.id == CatalogValue.source_id)
        .where(CatalogValue.material_id == item.id)
        .order_by(CatalogDefinition.domain, CatalogDefinition.key, CatalogValue.mt_id)
    ).all()

    values = [
        CatalogValueOut(
            id=value.id,
            property_key=value.property_key,
            property_name=definition.name,
            domain=definition.domain,
            symbol=definition.symbol,
            value_num=value.value_num,
            value_text=value.value_text,
            unit=value.unit,
            uncertainty=value.uncertainty,
            conditions=value.conditions,
            method=value.method,
            quality_tier=value.quality_tier,
            source=(
                CatalogSourceOut.model_validate(source, from_attributes=True)
                if source is not None
                else None
            ),
            source_detail=value.source_detail,
            notes=value.notes,
        )
        for value, definition, source in rows
    ]
    return CatalogMaterialDetailOut(
        id=item.id,
        name=item.name,
        material_code=item.material_code,
        category=item.category,
        description=item.description,
        subsystem=item.subsystem,
        role=item.role,
        manufacturer=item.manufacturer,
        material_class=item.material_class,
        grade=item.grade,
        attributes=item.attributes,
        values=values,
    )
