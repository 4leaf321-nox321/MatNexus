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
from app.modules.catalog import deck as deck_builder
from app.modules.catalog import representative
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.schemas import (
    CatalogLinkIn,
    CatalogLinkOut,
    CatalogMaterialDetailOut,
    CatalogMaterialOut,
    CatalogMaterialPage,
    CatalogSourceOut,
    CatalogSummaryOut,
    CatalogValueOut,
    DeckBuildIn,
    DeckBuiltOut,
    DeckCandidateOut,
    DeckMatchIn,
    DeckMatchRowOut,
    DeckSkippedOut,
)
from app.modules.materials.models import Material
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound
from app.shared.pagination import clamp_limit
from app.shared.permissions import require_owner_edit, visible_materials
from matcore import export

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


def _my_material(db: Session, user: User, material_id: uuid.UUID) -> Material:
    """보이는 사내 재료 — 가시 범위(전역+열린 부서+내 부서)를 지킨다."""
    item = db.scalar(visible_materials(db, user).where(Material.id == material_id))
    if item is None:
        raise NotFound("MNX-CATALOG-0002", "재료를 찾을 수 없습니다.")
    return item


@router.get("/links/{material_id}", response_model=CatalogLinkOut)
def get_link(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CatalogLinkOut:
    """이 사내 재료의 문헌 연결. **없어도 200 이다** — 비어 있는 상태가 정상이라
    404 로 만들면 화면이 오류와 「아직 없음」 을 구별 못 한다."""
    _my_material(db, user, material_id)
    row = db.execute(
        select(CatalogLink, CatalogMaterial)
        .join(CatalogMaterial, CatalogMaterial.id == CatalogLink.catalog_material_id)
        .where(CatalogLink.material_id == material_id)
    ).first()
    if row is None:
        return CatalogLinkOut()
    _link, linked = row
    count = (
        db.scalar(
            select(func.count())
            .select_from(CatalogValue)
            .where(CatalogValue.material_id == linked.id)
        )
        or 0
    )
    return CatalogLinkOut(
        catalog_material_id=linked.id,
        name=linked.name,
        category=linked.category,
        subsystem=linked.subsystem,
        value_count=count,
    )


@router.put("/links/{material_id}", response_model=CatalogLinkOut)
def put_link(
    material_id: uuid.UUID,
    payload: CatalogLinkIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CatalogLinkOut:
    """연결하거나 바꾼다 — 재료당 하나라 다시 걸면 교체다.

    권한은 재료 편집과 같다(부서 관리자, 전역은 시스템 관리자) — 연결이 채택의
    기본 대상이 되므로 아무나 걸면 남의 재료 물성이 엉뚱한 문헌으로 채워진다.
    """
    material = _my_material(db, user, material_id)
    require_owner_edit(
        db,
        user,
        material.owner_workspace_id,
        what="재료의 문헌 연결",
        code="MNX-CATALOG-0003",
    )
    linked = db.get(CatalogMaterial, payload.catalog_material_id)
    if linked is None:
        raise NotFound("MNX-CATALOG-0001", "카탈로그에 없는 재료입니다.")
    row = db.scalar(select(CatalogLink).where(CatalogLink.material_id == material_id))
    if row is None:
        db.add(CatalogLink(material_id=material_id, catalog_material_id=linked.id))
    else:
        row.catalog_material_id = linked.id
    db.commit()
    return get_link(material_id, user, db)


@router.delete("/links/{material_id}", status_code=204)
def delete_link(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    material = _my_material(db, user, material_id)
    require_owner_edit(
        db,
        user,
        material.owner_workspace_id,
        what="재료의 문헌 연결",
        code="MNX-CATALOG-0003",
    )
    row = db.scalar(select(CatalogLink).where(CatalogLink.material_id == material_id))
    if row is not None:
        db.delete(row)
        db.commit()


@router.post("/deck/match", response_model=list[DeckMatchRowOut])
def deck_match(
    payload: DeckMatchIn,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[DeckMatchRowOut]:
    """BOM 붙여넣기 → 줄마다 문헌 재료 후보. **고르는 것은 사람이다.**"""
    try:
        lines = deck_builder.parse_lines(payload.text)
    except export.ExportError as refused:
        raise AppError("MNX-CATALOG-0004", str(refused), status=422) from refused
    return [
        DeckMatchRowOut(
            query=line.query,
            mid=line.mid,
            candidates=[
                DeckCandidateOut(
                    id=one.id,
                    name=one.name,
                    category=one.category,
                    value_count=count,
                    score=score,
                )
                for one, count, score in deck_builder.candidates(db, line.query)
            ],
        )
        for line in lines
    ]


@router.post("/deck/build", response_model=DeckBuiltOut)
def deck_build(
    payload: DeckBuildIn,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DeckBuiltOut:
    """확정된 목록 → LS-DYNA 덱 한 파일. 쓰인 값마다 출처 각주가 $ 주석으로
    들어간다. 모자란 재료는 거르지 않고 알린다."""
    try:
        built = deck_builder.build(
            db,
            [(item.mid, item.catalog_material_id) for item in payload.items],
            payload.format,
            payload.units,
        )
    except export.ExportError as refused:
        raise AppError("MNX-CATALOG-0005", str(refused), status=422) from refused
    suffix = "" if payload.format == "dyna_elastic" else "_thermal"
    units_key = payload.units or "si"
    return DeckBuiltOut(
        filename=f"matnexus_catalog{suffix}_{units_key}.k",
        text=built.text,
        material_count=built.material_count,
        skipped=[
            DeckSkippedOut(mid=one.mid, name=one.name, missing=list(one.missing))
            for one in built.skipped
        ],
        notes=list(built.notes),
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

    # 같은 물성의 후보들 중 대표를 고르고 — 진 후보는 이유와 함께 그대로 낸다.
    marks = representative.annotate([value for value, _, _ in rows])
    # 무리 안에서 대표가 먼저 서도록 정렬만 바꾼다(도메인·키 차례는 유지).
    rows = sorted(
        rows,
        key=lambda row: (
            row[1].domain,
            row[1].key,
            0 if marks[row[0].id].representative else 1,
            row[0].mt_id,
        ),
    )

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
            representative=marks[value.id].representative,
            n_candidates=marks[value.id].n_candidates,
            separated_by=marks[value.id].separated_by,
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
