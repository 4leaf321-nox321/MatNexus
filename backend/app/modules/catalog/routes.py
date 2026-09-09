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
from app.modules.catalog import parameters
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.ontology_models import (
    ALIAS_SOURCES,
    LINK_KINDS,
    PropertyAlias,
    PropertyLink,
)
from app.modules.catalog.schemas import (
    AshbyAxisOut,
    AshbyOut,
    AshbyPointOut,
    CatalogCompareCellOut,
    CatalogCompareOut,
    CatalogCompareRowOut,
    CatalogCoverageOut,
    CatalogLinkIn,
    CatalogLinkOut,
    CatalogMaterialDetailOut,
    CatalogMaterialOut,
    CatalogMaterialPage,
    CatalogParameterSetOut,
    CatalogParameterTermOut,
    CatalogSourceOut,
    CatalogSummaryOut,
    CatalogValueOut,
    DeckBuildIn,
    DeckBuiltOut,
    DeckCandidateOut,
    DeckMatchIn,
    DeckMatchRowOut,
    DeckSkippedOut,
    PropertyAliasCreate,
    PropertyAliasOut,
    PropertyCandidateOut,
    PropertyHitOut,
    PropertyLinkCreate,
    PropertyLinkOut,
    PropertyResolveOut,
    PropertySearchOut,
)
from app.modules.materials.models import Material
from app.modules.vocabulary.models import VocabularyTerm
from app.shared import litdeck as deck_builder
from app.shared import property_names, property_search, representative
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound
from app.shared.pagination import clamp_limit
from app.shared.permissions import require_owner_edit, visible_material_ids, visible_materials
from app.shared.text import clean, compare_key
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


#: 비교에 세울 수 있는 재료 수. 그 이상은 표가 옆으로 무너진다(MT 실측 8).
COMPARE_MAX = 8


def _representative_values(
    db: Session, material_ids: list[uuid.UUID], keys: list[str] | None = None
) -> dict[tuple[uuid.UUID, str], CatalogValue]:
    """재료별·물성별 대표값 — 상세 화면과 **같은 선택**이다.

    한 쿼리로 값을 다 받아 재료 단위로 갈라 대표를 고른다 — 재료마다 쿼리를
    치면 Ashby(2,663종)에서 N+1 이 된다.
    """
    query = select(CatalogValue).where(CatalogValue.material_id.in_(material_ids))
    if keys is not None:
        query = query.where(CatalogValue.property_key.in_(keys))
    by_material: dict[uuid.UUID, list[CatalogValue]] = {}
    for value in db.scalars(query):
        by_material.setdefault(value.material_id, []).append(value)
    out: dict[tuple[uuid.UUID, str], CatalogValue] = {}
    for material_id, values in by_material.items():
        marks = representative.annotate(values)
        for value in values:
            if marks[value.id].representative:
                out[(material_id, value.property_key)] = value
    return out


def _candidate_counts(
    db: Session, material_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], int]:
    rows = db.execute(
        select(
            CatalogValue.material_id,
            CatalogValue.property_key,
            func.count(),
        )
        .where(CatalogValue.material_id.in_(material_ids))
        .group_by(CatalogValue.material_id, CatalogValue.property_key)
    )
    return {(material_id, key): count for material_id, key, count in rows}


@router.get("/compare", response_model=CatalogCompareOut)
def compare(
    ids: str = Query(description="쉼표로 이은 카탈로그 재료 id (2~8)"),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CatalogCompareOut:
    """재료 나란히 보기 — 물성마다 각 재료의 대표값 한 줄.

    **후보 수를 함께 준다.** 칸의 숫자가 N개 중 하나라는 사실 자체가 사용자가
    알아야 할 정보다(상세 화면과 같은 원칙).
    """
    try:
        material_ids = [uuid.UUID(one.strip()) for one in ids.split(",") if one.strip()]
    except ValueError:
        raise AppError(
            "MNX-CATALOG-0006", "재료 id 가 올바르지 않습니다.", status=422
        ) from None
    if not 2 <= len(material_ids) <= COMPARE_MAX:
        raise AppError(
            "MNX-CATALOG-0006",
            f"비교는 2~{COMPARE_MAX}종입니다 — 지금 {len(material_ids)}종.",
            status=422,
        )
    found = {
        one.id: one
        for one in db.scalars(
            select(CatalogMaterial).where(CatalogMaterial.id.in_(material_ids))
        )
    }
    missing = [str(one) for one in material_ids if one not in found]
    if missing:
        raise NotFound("MNX-CATALOG-0001", f"카탈로그에 없는 재료입니다: {', '.join(missing)}")

    reps = _representative_values(db, material_ids)
    counts = _candidate_counts(db, material_ids)
    keys = sorted({key for _, key in reps})
    definitions = {
        one.key: one
        for one in db.scalars(select(CatalogDefinition).where(CatalogDefinition.key.in_(keys)))
    }
    rows = [
        CatalogCompareRowOut(
            property_key=key,
            name=definitions[key].name,
            domain=definitions[key].domain,
            symbol=definitions[key].symbol,
            unit=definitions[key].si_unit,
            cells=[
                (
                    CatalogCompareCellOut(
                        value_num=rep.value_num,
                        value_text=rep.value_text,
                        quality_tier=rep.quality_tier,
                        n_candidates=counts.get((material_id, key), 0),
                        conditions=representative.semantic_conditions(rep.conditions) or None,
                    )
                    if (rep := reps.get((material_id, key))) is not None
                    else CatalogCompareCellOut()
                )
                for material_id in material_ids
            ],
        )
        for key in sorted(keys, key=lambda one: (definitions[one].domain, one))
    ]
    return CatalogCompareOut(
        materials=[
            CatalogMaterialOut.model_validate(
                {**found[one].__dict__, "value_count": 0}, from_attributes=False
            )
            for one in material_ids
        ],
        rows=rows,
    )


@router.get("/axes", response_model=list[AshbyAxisOut])
def axes(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AshbyAxisOut]:
    """Ashby 축 후보 — 수치값을 가진 재료 수가 많은 물성부터.

    재료 5종 미만인 축은 뺀다 — 점 서넛으로는 지도가 아니라 소음이다.
    """
    rows = db.execute(
        select(
            CatalogValue.property_key,
            func.count(func.distinct(CatalogValue.material_id)),
        )
        .where(CatalogValue.value_num.is_not(None))
        .group_by(CatalogValue.property_key)
        .having(func.count(func.distinct(CatalogValue.material_id)) >= 5)
    ).all()
    definitions = {
        one.key: one
        for one in db.scalars(
            select(CatalogDefinition).where(
                CatalogDefinition.key.in_([key for key, _ in rows])
            )
        )
    }
    return sorted(
        (
            AshbyAxisOut(
                key=key,
                name=definitions[key].name,
                domain=definitions[key].domain,
                unit=definitions[key].si_unit,
                material_count=count,
            )
            for key, count in rows
        ),
        key=lambda one: -one.material_count,
    )


@router.get("/ashby", response_model=AshbyOut)
def ashby(
    x: str = Query(),
    y: str = Query(),
    color: str = Query(default="category", pattern="^(category|subsystem)$"),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AshbyOut:
    """물성-물성 산점도 — 두 축의 수치 대표값을 다 가진 재료만 점이 된다."""
    definitions = {
        one.key: one
        for one in db.scalars(
            select(CatalogDefinition).where(CatalogDefinition.key.in_([x, y]))
        )
    }
    for key in (x, y):
        if key not in definitions:
            raise NotFound("MNX-CATALOG-0007", f"모르는 물성입니다: {key}")

    material_ids = list(
        db.scalars(
            select(CatalogValue.material_id)
            .where(CatalogValue.property_key.in_([x, y]), CatalogValue.value_num.is_not(None))
            .group_by(CatalogValue.material_id)
            .having(func.count(func.distinct(CatalogValue.property_key)) == 2)
        )
    )
    reps = _representative_values(db, material_ids, keys=[x, y])
    materials = {
        one.id: one
        for one in db.scalars(
            select(CatalogMaterial).where(CatalogMaterial.id.in_(material_ids))
        )
    }
    points = []
    for material_id in material_ids:
        x_rep = reps.get((material_id, x))
        y_rep = reps.get((material_id, y))
        if x_rep is None or y_rep is None:
            continue
        if x_rep.value_num is None or y_rep.value_num is None:
            continue
        one = materials[material_id]
        group = (one.category if color == "category" else one.subsystem) or "미분류"
        points.append(
            AshbyPointOut(
                id=material_id,
                name=one.name,
                group=group,
                x=x_rep.value_num,
                y=y_rep.value_num,
            )
        )
    return AshbyOut(
        x_unit=definitions[x].si_unit, y_unit=definitions[y].si_unit, points=points
    )


@router.get("/coverage", response_model=CatalogCoverageOut)
def coverage(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CatalogCoverageOut:
    """계통-도메인 값 수 격자 — 이 카탈로그가 어디에 두껍고 어디가 비었나."""
    rows = db.execute(
        select(
            CatalogMaterial.subsystem,
            CatalogDefinition.domain,
            func.count(),
        )
        .select_from(CatalogValue)
        .join(CatalogMaterial, CatalogMaterial.id == CatalogValue.material_id)
        .join(CatalogDefinition, CatalogDefinition.key == CatalogValue.property_key)
        .group_by(CatalogMaterial.subsystem, CatalogDefinition.domain)
    ).all()
    cells: dict[str, dict[str, int]] = {}
    for subsystem, domain, count in rows:
        cells.setdefault(subsystem or "", {})[domain] = count
    domains = sorted({domain for _, domain, _ in rows})
    # 값 많은 계통부터 — 미분류("")는 맨 뒤.
    subsystems = sorted(
        cells,
        key=lambda one: (one == "", -sum(cells[one].values())),
    )
    return CatalogCoverageOut(domains=domains, subsystems=subsystems, cells=cells)


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
            term=(value.conditions or {}).get(parameters.TERM),
            term_unit=(value.conditions or {}).get(parameters.UNIT_OF_TERM),
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
            distinguishing=marks[value.id].distinguishing,
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


# --- 물성 이름 사전 -----------------------------------------------------------
#
# **MCP/AI 가 값을 묻기 전에 거치는 자리다.** 「항복응력」이 어느 물성인지 모르면
# 그 뒤의 모든 질문이 틀린 물성에 답한다 — 실측(2026-09-08): 이름이 정확히
# 「항복응력」인 정의는 유변학 물성(9건, 8~20 Pa)이고, 사람이 뜻하는 금속 항복강도는
# 「항복강도」(486건)다.


@router.get("/properties/resolve", response_model=PropertyResolveOut)
def resolve_property(
    q: str = Query(min_length=1, description="사람이 부르는 이름·기호·별칭"),
    limit: int = Query(default=12, ge=1, le=50),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyResolveOut:
    """이름 → 물성 후보들. **고르지 않고 나란히 준다.**

    `ambiguous` 가 참이면 도메인이 다른 후보가 나란히 섰다는 뜻이고, 그때 하나를
    고르면 조용히 틀린다 — 부르는 쪽이 되물어야 한다.
    """
    found = property_names.describe(property_names.resolve(db, q, limit=limit))
    return PropertyResolveOut(
        query=q,
        ambiguous=bool(found["ambiguous"]),
        candidates=[PropertyCandidateOut(**one) for one in found["candidates"]],
    )


@router.get("/properties/{property_key}/aliases", response_model=list[PropertyAliasOut])
def list_property_aliases(
    property_key: str,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PropertyAliasOut]:
    rows = db.scalars(
        select(PropertyAlias)
        .where(PropertyAlias.property_key == property_key)
        .order_by(PropertyAlias.alias)
    ).all()
    return [PropertyAliasOut.model_validate(row) for row in rows]


@router.post(
    "/properties/{property_key}/aliases", response_model=PropertyAliasOut, status_code=201
)
def add_property_alias(
    property_key: str,
    payload: PropertyAliasCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyAliasOut:
    """별칭 하나를 더한다.

    **이미 있으면 그것을 돌려준다** — 409 가 아니다. 기준정보 값 추가와 같은
    판단이다: 실제로 일어난 일이 「이미 있는 것을 또 적었다」 뿐인데 화면이
    멈추면 안 된다.
    """
    if payload.source not in ALIAS_SOURCES:
        raise AppError(
            "MNX-CATALOG-0020",
            f"별칭 출처는 {', '.join(ALIAS_SOURCES)} 중 하나여야 합니다.",
            status=422,
        )
    definition = db.scalar(
        select(CatalogDefinition).where(CatalogDefinition.key == property_key)
    )
    if definition is None:
        raise NotFound("MNX-CATALOG-0021", f"'{property_key}' 물성 정의를 찾을 수 없습니다.")

    cleaned = clean(payload.alias)
    if cleaned is None:
        raise AppError("MNX-CATALOG-0022", "별칭이 비었습니다.", status=422)
    normalized = compare_key(cleaned)

    found = db.scalar(
        select(PropertyAlias).where(
            PropertyAlias.property_key == property_key,
            PropertyAlias.normalized == normalized,
        )
    )
    if found is None:
        found = PropertyAlias(
            property_key=property_key,
            alias=cleaned,
            normalized=normalized,
            source=payload.source,
            note=payload.note,
            created_by_id=user.id,
        )
        db.add(found)
        db.commit()
        db.refresh(found)
    return PropertyAliasOut.model_validate(found)


@router.delete("/properties/aliases/{alias_id}", status_code=204)
def remove_property_alias(
    alias_id: uuid.UUID,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(PropertyAlias, alias_id)
    if row is None:
        raise NotFound("MNX-CATALOG-0023", "그 별칭을 찾을 수 없습니다.")
    db.delete(row)
    db.commit()


@router.get("/properties/links", response_model=list[PropertyLinkOut])
def list_property_links(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[PropertyLinkOut]:
    """문헌 물성 ↔ 사내 물성 항목 매핑 전부(ADR 0027 이 미뤄 둔 그 표)."""
    rows = db.execute(
        select(PropertyLink, VocabularyTerm.value)
        .join(VocabularyTerm, VocabularyTerm.id == PropertyLink.term_id)
        .order_by(PropertyLink.property_key)
    ).all()
    return [
        PropertyLinkOut(
            id=link.id,
            property_key=link.property_key,
            term_id=link.term_id,
            item=item,
            kind=link.kind,
            note=link.note,
        )
        for link, item in rows
    ]


@router.post("/properties/links", response_model=PropertyLinkOut, status_code=201)
def add_property_link(
    payload: PropertyLinkCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyLinkOut:
    """매핑 하나. **`same_as` 를 함부로 쓰지 않는다** — 다른 것은 다르게 적는다."""
    if payload.kind not in LINK_KINDS:
        raise AppError(
            "MNX-CATALOG-0024",
            f"매핑 종류는 {', '.join(LINK_KINDS)} 중 하나여야 합니다.",
            status=422,
        )
    if (
        db.scalar(
            select(CatalogDefinition).where(CatalogDefinition.key == payload.property_key)
        )
        is None
    ):
        raise NotFound(
            "MNX-CATALOG-0021", f"'{payload.property_key}' 물성 정의를 찾을 수 없습니다."
        )
    term = next(
        (
            one
            for one in property_names.item_terms(db)
            if compare_key(one.value) == compare_key(payload.item)
        ),
        None,
    )
    if term is None:
        raise NotFound(
            "MNX-CATALOG-0025",
            f"'{payload.item}' 이(가) 사내 물성 항목에 없습니다. 기준정보에서 먼저 만드세요.",
        )
    found = db.scalar(
        select(PropertyLink).where(
            PropertyLink.property_key == payload.property_key,
            PropertyLink.term_id == term.id,
        )
    )
    if found is None:
        found = PropertyLink(
            property_key=payload.property_key,
            term_id=term.id,
            kind=payload.kind,
            note=payload.note,
            created_by_id=user.id,
        )
        db.add(found)
        db.commit()
        db.refresh(found)
    return PropertyLinkOut(
        id=found.id,
        property_key=found.property_key,
        term_id=found.term_id,
        item=term.value,
        kind=found.kind,
        note=found.note,
    )


@router.get("/properties/search", response_model=PropertySearchOut)
def search_by_property(
    q: str = Query(min_length=1, description="물성 이름 — 「항복응력」·「UTS」"),
    unit: str = Query(min_length=1, description="**필수.** 「MPa」·「GPa」"),
    near: float | None = Query(default=None, description="이 값 ±10%"),
    min_value: float | None = Query(default=None, alias="min"),
    max_value: float | None = Query(default=None, alias="max"),
    term: str | None = Query(
        default=None, description="파라미터형 물성에서 어느 변수인가 — 「A」·「h0」"
    ),
    scope: str = Query(default="all", description="`all` · `catalog` · `internal`"),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertySearchOut:
    """**값으로 재료를 찾는다** — 「항복응력이 200MPa 근처인 재료」.

    ## 단위가 필수인 이유

    값은 SI 로 저장돼 있어 200MPa 는 `200,000,000` 이다. 사람은 「200」 이라고
    치는데 그대로 걸면 **8 Pa 짜리가 나온다.** 짐작해서 답하면 조용히 틀린다.

    ## 갈리면 값을 안 찾는다

    「항복응력」 은 금속 항복강도(486건)와 유변학 항복응력(9건) 둘에 걸린다.
    어느 쪽인지 모른 채 찾은 값은 **엉뚱한 물성의 정답**이다 — 후보만 돌려주고
    부르는 쪽이 고르게 한다.
    """
    candidates = property_names.resolve(db, q, limit=5)
    if not candidates:
        return PropertySearchOut(query=q, notes=[f"'{q}' 로 물성을 찾지 못했습니다."])
    if property_names.ambiguous(candidates):
        return PropertySearchOut(
            query=q,
            ambiguous=True,
            candidates=[
                PropertyCandidateOut(**one)
                for one in property_names.describe(candidates)["candidates"]
            ],
            notes=[
                "물성이 갈립니다 — 어느 것인지 골라 주세요. 도메인이 다른 후보가 "
                "나란히 섰습니다."
            ],
        )

    chosen = candidates[0]

    # **한 키에 여러 변수가 든 물성이 있다**(ADR 0029). Anand 하나에 9개 상수가
    # 들어 있고 단위도 `1`·`1/s`·`MPa`·`K` 로 제각각이라, 변수를 안 정하고 찾으면
    # 그것들을 섞어서 답한다 — 그리고 틀렸다는 신호가 어디에도 안 남는다.
    grouped = parameters.is_parameterized(db, chosen.key)
    if grouped and not term:
        found = parameters.terms(db, chosen.key)
        raise AppError(
            "MNX-CATALOG-0034",
            f"'{chosen.name}' 은 변수 여러 개를 담고 있습니다 — 어느 변수인지 "
            f"`term` 으로 정해 주세요: "
            + " · ".join(f"{one.name}[{one.unit or '?'}]" for one in found[:12]),
            status=422,
        )
    # 파라미터형은 저장된 값이 SI 가 아니라 그 항의 원래 단위다(D2) — 환산하지 않는다.
    real_unit = parameters.unit_of(db, chosen.key, term) if grouped else chosen.si_unit
    if grouped and term and real_unit and unit.strip().lower() != real_unit.strip().lower():
        raise AppError(
            "MNX-CATALOG-0035",
            f"'{chosen.name} · {term}' 의 단위는 '{real_unit}' 입니다 — '{unit}' 로는 "
            "비교할 수 없습니다(이 값은 SI 로 저장돼 있지 않아 환산하지 않습니다).",
            status=422,
        )

    low, high = property_search.bounds(
        unit=unit,
        si_unit=chosen.si_unit,
        minimum=min_value,
        maximum=max_value,
        near=near,
        convert=not grouped,
    )

    hits: list[property_search.Hit] = []
    notes: list[str] = []
    if scope in ("all", "catalog"):
        hits += property_search.catalog_hits(
            db,
            property_key=chosen.key,
            low=low,
            high=high,
            unit=unit,
            limit=limit,
            term=term,
            convert=not grouped,
        )
    if scope in ("all", "internal") and grouped:
        # 파라미터 집합은 아직 사내로 받아 가는 길이 열리지 않았다(ADR 0029 2단계).
        notes.append("사내 재료는 안 봤습니다 — 모델 파라미터는 아직 채택 경로가 없습니다.")
    elif scope in ("all", "internal"):
        if chosen.items:
            for item in chosen.items:
                hits += property_search.internal_hits(
                    db,
                    item=item,
                    low=low,
                    high=high,
                    unit=unit,
                    limit=limit,
                    visible=visible_material_ids(db, user),
                )
        else:
            # **못 찾은 게 아니라 이어져 있지 않은 것이다.** 그 차이를 말한다.
            notes.append(
                "사내 재료는 안 봤습니다 — 이 문헌 물성이 사내 물성 항목과 아직 "
                "이어져 있지 않습니다(물성 매핑에서 이을 수 있습니다)."
            )

    hits.sort(key=lambda one: one.value_si)
    return PropertySearchOut(
        query=q,
        resolved=PropertyCandidateOut(**property_names.describe([chosen])["candidates"][0]),
        unit=unit,
        range_si=[low, high],
        total=len(hits),
        hits=[
            PropertyHitOut(
                world=one.world,
                material_id=one.material_id,
                material_name=one.material_name,
                value=one.value_shown,
                unit=one.unit_shown,
                value_si=one.value_si,
                quality_tier=one.quality_tier,
                source_detail=one.source_detail,
                category=one.category,
            )
            for one in hits[:limit]
        ],
        notes=notes,
    )


@router.get(
    "/materials/{material_id}/parameter-sets", response_model=list[CatalogParameterSetOut]
)
def catalog_parameter_sets(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[CatalogParameterSetOut]:
    """이 문헌 재료가 가진 **모델 파라미터 벌들**(ADR 0029).

    Anand 9개처럼 여럿이 한 벌이어야 뜻이 있는 값을, 값 표에 낱개로 흩지 않고
    묶어서 준다 — 사내 재료로 받아 갈 때도 이 한 벌이 단위다.
    """
    made: list[CatalogParameterSetOut] = []
    keys = db.scalars(
        select(CatalogValue.property_key)
        .where(CatalogValue.material_id == material_id)
        .distinct()
    ).all()
    for key in keys:
        if not parameters.is_parameterized(db, key):
            continue
        definition = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key))
        label = parameters.label(definition) if definition else key
        for one in parameters.sets(db, key=key, material_id=material_id):
            made.append(
                CatalogParameterSetOut(
                    property_key=key,
                    label=label,
                    model=one.model,
                    set_id=one.set_id,
                    quality_tier=one.quality_tier,
                    source_detail=one.source,
                    terms=[CatalogParameterTermOut(**term) for term in one.terms],
                )
            )
    return made
