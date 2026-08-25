"""재료·시료·시편 라우터.

소프트 삭제만 한다(`deleted_at`). 시험 데이터가 매달린 계층이라 실제 삭제는
되돌릴 수 없고, "지웠는데 사실은 다른 재료였다"가 실무에서 반드시 생긴다.
대신 **하위가 남아 있으면 지우지 못하게** 막는다 — 위에서부터 지워 내려가면
아래가 고아로 남아 목록 어디에도 안 보이면서 용량만 차지한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.materials import declared, services
from app.modules.materials.models import ORIENTATIONS, Material, Sample, Specimen
from app.modules.materials.schemas import (
    DENSITY_UNIT,
    LENGTH_UNIT,
    ClassificationOut,
    DeclaredPointOut,
    DeclaredPropertyOut,
    MaterialCreateRequest,
    MaterialOut,
    MaterialUpdateRequest,
    MillCheckOut,
    MillCheckRowOut,
    NamePreviewOut,
    NamePreviewRequest,
    PropertyItemOut,
    PropertySourcesOut,
    SampleCreateRequest,
    SampleOut,
    SampleUpdateRequest,
    SpecimenBriefSizeOut,
    SpecimenCreateRequest,
    SpecimenOut,
    SpecimenSizeOut,
    SpecimenSizesOut,
    SpecimenSizesRequest,
    SpecimenUpdateRequest,
    SpecimenWarningOut,
    ValueSourceOut,
)
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.models import VocabularyTerm
from app.shared import audit, specimen_size
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.pagination import Page, clamp_limit
from matcore import naming, units
from matcore import specimen as specimen_kit

router = APIRouter(prefix="/materials", tags=["materials"])
samples_router = APIRouter(prefix="/samples", tags=["materials"])
specimens_router = APIRouter(prefix="/specimens", tags=["materials"])


def _now() -> datetime:
    return datetime.now(UTC)


# --- 매퍼 -------------------------------------------------------------------


def _material_out(
    material: Material, *, sample_count: int, workspace_name: str | None
) -> MaterialOut:
    unit = material.input_units.get("spec_thickness", LENGTH_UNIT)
    density_unit = material.input_units.get("density", DENSITY_UNIT)
    return MaterialOut(
        id=material.id,
        record_name=material.record_name,
        alias=material.alias,
        owner_workspace_id=material.owner_workspace_id,
        owner_workspace_name=workspace_name,
        is_global=material.owner_workspace_id is None,
        family=material.family,
        category=material.category,
        grade=material.grade,
        details=material.details,
        spec_thickness=services.from_si(material.spec_thickness_m, unit),
        spec_thickness_unit=unit,
        applied_product=material.applied_product,
        applied_part=material.applied_part,
        density=services.from_si(material.density_si, density_unit),
        density_unit=density_unit,
        poisson_ratio=material.poisson_ratio,
        declared_properties=[
            _declared_out(row) for row in (material.declared_properties or [])
        ],
        note=material.note,
        legacy_id=material.legacy_id,
        sample_count=sample_count,
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


def _why_not_compared(compared: bool, spec: dict[str, Any], key: str) -> str | None:
    """왜 안 견줬는지. **조용히 빼지 않는다** — 줄이 비면 사람은 잰 값이 0
    이라고 읽거나, 적은 값이 사라진 줄 안다.
    """
    if compared:
        return None
    if spec.get("scales"):
        return (
            "시험 척도로 재는 값이라 우리가 잰 값과 견주지 않습니다 — "
            "척도가 다르면 서로 환산되지 않습니다."
        )
    if not key:
        return (
            "우리가 재는 값으로 이어져 있지 않습니다 — 기준정보의 물성 항목에서 "
            "'우리가 재는 값' 을 고르면 여기서 견줍니다."
        )
    return "이 시료에 채택된 처리 결과가 없습니다."


def _declared_out(row: dict[str, Any]) -> DeclaredPropertyOut:
    """저장된 한 줄을 응답 모양으로.

    **되돌리는 환산도 서버가 한다.** 화면이 나눗셈을 하면 그 규칙이 두 곳에
    생기고(ADR 0004), 갈라진 쪽이 화면이면 사람은 자기가 적은 값과 다른 숫자를
    보면서 그것이 저장된 값이라고 믿는다.
    """
    symbol = row.get("input_unit")
    return DeclaredPropertyOut(
        item=str(row["item"]),
        points=[
            DeclaredPointOut(
                temperature_k=point.get("temperature_k"),
                value_si=float(point["value_si"]),
                # **척도는 환산이 없다.** 적은 값이 곧 저장 값이다.
                value=units.from_si(point["value_si"], symbol)
                if symbol
                else float(point["value_si"]),
            )
            for point in row["points"]
        ],
        input_unit=symbol,
        scale=row.get("scale"),
        source=str(row["source"]),
        reference=str(row["reference"]),
        note=row.get("note"),
    )


#: 시험 상태 집계 한 벌 — (전체, 채택, 실패).
RunTally = tuple[int, int, int]


def _run_tallies(
    db: Session, *, group_by: Any, ids: list[uuid.UUID], join_specimen: bool
) -> dict[uuid.UUID, RunTally]:
    """시험을 **한 번에** 센다.

    줄마다 물으면 시편 11개짜리 시료에서 쿼리가 12번 나간다(CLAUDE.md — N+1 은
    명시적 join 으로 막는다).

    `count(adopted_result_id)` 가 곧 채택 수다 — NULL 은 세지 않는다.
    """
    if not ids:
        return {}
    query = select(
        group_by,
        func.count(TestRun.id),
        func.count(TestRun.adopted_result_id),
        func.count().filter(TestRun.status == "failed"),
    ).where(TestRun.deleted_at.is_(None))
    if join_specimen:
        query = query.join(Specimen, Specimen.id == TestRun.specimen_id).where(
            Specimen.deleted_at.is_(None)
        )
    return {
        key: (total, adopted, failed)
        for key, total, adopted, failed in db.execute(
            query.where(group_by.in_(ids)).group_by(group_by)
        ).all()
    }


def _sample_out(
    sample: Sample,
    *,
    specimen_count: int,
    workspace_name: str | None,
    runs: RunTally = (0, 0, 0),
) -> SampleOut:
    unit = sample.input_units.get("density", DENSITY_UNIT)
    return SampleOut(
        test_run_count=runs[0],
        adopted_count=runs[1],
        failed_count=runs[2],
        id=sample.id,
        material_id=sample.material_id,
        workspace_id=sample.workspace_id,
        workspace_name=workspace_name,
        seq_no=sample.seq_no,
        record_name=sample.record_name,
        alias=sample.alias,
        lot_no=sample.lot_no,
        manufacturer=sample.manufacturer,
        distributor=sample.distributor,
        primary_vendor=sample.primary_vendor,
        sales_type=sample.sales_type,
        production_date=sample.production_date,
        density=services.from_si(sample.density_si, unit),
        density_unit=unit,
        declared_properties=[_declared_out(row) for row in (sample.declared_properties or [])],
        note=sample.note,
        specimen_count=specimen_count,
        created_at=sample.created_at,
    )


def _brief_sizes(sizes: specimen_size.Sizes | None) -> list[SpecimenBriefSizeOut]:
    """접힌 줄에 적을 치수. **이름과 출처를 함께 낸다.**"""
    if sizes is None:
        return []
    known = {field.key: field for field in sizes.fields}
    return [
        SpecimenBriefSizeOut(
            key=item.key,
            label=item.label,
            symbol=known[item.key].symbol if item.key in known else None,
            value=item.value,
            si_unit=item.si_unit,
            dimension=known[item.key].dimension if item.key in known else "length",
            source=item.source,
        )
        for item in sizes.items
    ]


def _specimen_out(
    specimen: Specimen,
    *,
    runs: RunTally = (0, 0, 0),
    sizes: specimen_size.Sizes | None = None,
) -> SpecimenOut:
    unit = specimen.input_units.get("length", LENGTH_UNIT)
    return SpecimenOut(
        test_run_count=runs[0],
        adopted_count=runs[1],
        failed_count=runs[2],
        id=specimen.id,
        sample_id=specimen.sample_id,
        workspace_id=specimen.workspace_id,
        seq_no=specimen.seq_no,
        orientation=specimen.orientation,
        record_name=specimen.record_name,
        standard=specimen.standard,
        thickness=services.from_si(specimen.thickness_m, unit),
        width=services.from_si(specimen.width_m, unit),
        gauge_length=services.from_si(specimen.gauge_length_m, unit),
        length_unit=unit,
        sizes=_brief_sizes(sizes),
        note=specimen.note,
        created_at=specimen.created_at,
    )


# --- 재료 -------------------------------------------------------------------


@router.post("/preview-name", response_model=NamePreviewOut)
def preview_name(
    payload: NamePreviewRequest,
    workspace_slug: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> NamePreviewOut:
    """등록 폼이 입력 중에 부른다.

    이름을 만드는 곳은 서버 하나다. 화면이 같은 규칙을 다시 구현하면 두 구현이
    갈라지고, 그때 화면이 보여 준 이름과 저장된 이름이 달라진다.
    """
    thickness_m = services.to_si(
        payload.spec_thickness, payload.spec_thickness_unit, field="두께"
    )
    record_name = services.material_record_name(
        grade=payload.grade, details=payload.details, spec_thickness_m=thickness_m
    )
    workspace = services.resolve_workspace(db, user, workspace_slug)
    return NamePreviewOut(
        record_name=record_name,
        taken=services.name_taken(
            db, owner_workspace_id=workspace.id, record_name=record_name
        ),
    )


#: 검색이 훑는 칸. **목록에 보이는 것은 전부 들어 있어야 한다.**
#:
#: 실사용 보고: "재료를 검색해도 안 나온다." 이름·별칭·Grade 만 보고 있었는데,
#: 사람은 화면에 떡하니 보이는 Family·Category·Details 로도 찾는다. 검색이
#: 실패했다고 알려 주지도 않으니 **재료가 없는 줄 안다** — 조용히 틀리는 쪽이다.
#: **`OR` 가지는 전부 인덱스가 있어야 한다.** 하나라도 색인이 없으면 그것 때문에
#: 전 행을 훑게 되어 나머지 인덱스가 무의미해진다(실측: 6개 OR 118ms vs 4개 OR
#: 4.6ms, 합성 5만 건). 그래서 이 목록은 trgm 인덱스가 있는 컬럼과 **정확히 같이**
#: 유지한다 — 여기 하나를 더하면 마이그레이션도 따라와야 한다.
#:
#: `grade`·`details` 를 뺀 이유: `record_name` 이 `{grade}_{details}_{두께}` 라서
#: (ADR 0004) 이름 검색이 그 둘을 이미 덮는다. 빼도 잃는 것이 없다.
_SEARCH_TEXT = (
    Material.record_name,
    Material.alias,
)

#: 기준정보를 거치는 검색 축과 그 FK 컬럼. **축으로 좁히는 것이 요점이다**(ADR 0010) —
#: `materials.family` 는 5만 행인데 값은 5가지고, 기준정보 쪽 `family` 축은 5행이다.
#: 축을 안 좁히고 기준정보 전체(23만)를 훑으면 정규화의 이득을 도로 잃는다
#: (실측: 2글자 검색어에서 79ms 대 0.02ms).
_SEARCH_AXES = (
    ("family", Material.family_term_id),
    ("category", Material.category_term_id),
)


def _search_terms(db: Session, q: str | None) -> list[Any]:
    """검색어를 낱말로 나눠 **낱말마다 조건 하나**로 만든다(AND).

    이름은 `SECC_MDOI_1.0` 인데 사람은 `SECC 1.0` 이라고 친다. 구분자가 밑줄이라
    통째로 비교하면 안 맞는다. 낱말마다 나누면 순서도 상관없어진다 — 사람이 이름
    규칙의 순서를 외우고 있지 않다.

    AND 인 이유: OR 로 하면 낱말이 늘수록 결과가 **늘어난다.** 좁히려고 더 쳤는데
    넓어지면 검색이 아니다.
    """
    if not q or not q.strip():
        return []
    conditions: list[Any] = []
    for word in q.split():
        branches: list[Any] = [column.ilike(f"%{word}%") for column in _SEARCH_TEXT]
        # **기준정보를 먼저 찾고 그 id 로 재료를 찾는다.** 상관 서브쿼리
        # (`IN (SELECT ...)`) 로 쓰면 안 된다 — 그건 인덱스 조건이 아니라 필터로
        # 강등돼서 BitmapOr 에 못 낀다. 값이 박힌 `IN (id, ...)` 만 낀다.
        # 실측: 좁은 검색(4건)이 0.08ms → 90ms 로 1000배 느려졌다.
        ids = vocabulary_services.term_ids_matching(
            db, [slug for slug, _ in _SEARCH_AXES], word
        )
        if ids:
            branches += [column.in_(ids) for _, column in _SEARCH_AXES]
        conditions.append(or_(*branches))
    return conditions


# **고정 경로는 `/{material_id}` 보다 위에 둔다.** 아래 두면 FastAPI 가
# `property-items` 를 재료 id 로 읽고 422 를 낸다 — `classifications` 가 여기
# 있는 것과 같은 이유다.
@router.get("/property-items", response_model=list[PropertyItemOut])
def property_items(
    level: str | None = None,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PropertyItemOut]:
    """넣을 수 있는 물성 항목. **목록은 기준정보가 정한다**(D7).

    `level` 로 층을 좁힌다 — `재료` 는 Grade 가 같으면 같은 값(탄성계수·열물성),
    `시료` 는 로트마다 다른 값(항복강도·인장강도)이다. **안 주면 전부** 준다.

    화면이 이 응답만으로 피커와 단위 칸을 그릴 수 있어야 한다 — 항목을 코드에
    박으면 부서가 필요한 물성 하나를 넣으려고 배포를 기다려야 한다.

    감춘 항목은 안 나온다. **이미 넣어 둔 값은 그대로 남는다** — 감추는 것은
    "앞으로 새로 고르지 말라" 는 뜻이지 과거를 지우는 것이 아니다.
    """
    return [
        PropertyItemOut(
            item=name,
            dimension=spec["dimension"],
            si_unit=spec["si_unit"],
            symbol=spec["symbol"],
            level=spec["level"],
            scales=spec["scales"],
            # **척도를 든 항목에는 단위를 안 준다.** 둘 다 주면 화면이 어느
            # 쪽을 그릴지 스스로 판단해야 하고, 그 판단이 서버와 갈라진다.
            units=[] if spec["scales"] else units.units_for(spec["dimension"]),
        )
        for name, spec in sorted(declared.catalog(db, level=level).items())
    ]


@router.get("/classifications", response_model=list[ClassificationOut])
def list_classifications(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ClassificationOut]:
    """쓰이고 있는 Family·Category 조합.

    **`/{material_id}` 보다 먼저 선언해야 한다.** FastAPI 는 선언 순서대로 맞춰
    보므로, 뒤에 두면 `classifications` 가 UUID 자리에 들어가 422 가 난다.

    보이는 범위 안에서만 센다 — 남의 부서 분류가 목록에 뜨면 고를 수는 있는데
    결과가 늘 0건이다.
    """
    visible = services.visible_materials(db, user).subquery()
    # 기준정보를 거쳐 읽는다(ADR 0010 Contract). 문자열 컬럼은 아직 있지만 여기서는
    # 안 본다 — 지우기 전에 FK 경로가 같은 답을 내는지 한 릴리스 지켜본다.
    family_term = aliased(VocabularyTerm)
    category_term = aliased(VocabularyTerm)
    rows = db.execute(
        select(family_term.value, category_term.value, func.count())
        .select_from(visible)
        .join(family_term, family_term.id == visible.c.family_term_id, isouter=True)
        .join(category_term, category_term.id == visible.c.category_term_id, isouter=True)
        .group_by(family_term.value, category_term.value)
        .order_by(family_term.value, category_term.value)
    ).all()
    return [
        ClassificationOut(family=family, category=category, count=count)
        for family, category, count in rows
    ]


@router.get("", response_model=Page[MaterialOut])
def list_materials(
    q: str | None = Query(
        default=None,
        description="이름·별칭·Family·Category·Grade·Details 부분 일치. 낱말마다 나눠 AND",
    ),
    family: str | None = None,
    category: str | None = None,
    scope: str = Query(default="all", pattern="^(all|mine|global)$"),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[MaterialOut]:
    query = services.visible_materials(db, user)
    for condition in _search_terms(db, q):
        query = query.where(condition)
    # **없는 값으로 거르면 0건이어야 한다.** `== None` 으로 두면 그 축이 비어 있는
    # 재료가 전부 걸린다 — 조용히 틀리는 쪽이다.
    for value, slug, column in (
        (family, "family", Material.family_term_id),
        (category, "category", Material.category_term_id),
    ):
        if not value:
            continue
        term = vocabulary_services.resolve(
            db, vocabulary_services.get_vocabulary(db, slug), value
        )
        query = query.where(column == term.id if term else false())
    if scope == "global":
        query = query.where(Material.owner_workspace_id.is_(None))
    elif scope == "mine":
        query = query.where(Material.owner_workspace_id.is_not(None))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    rows = list(db.scalars(query.order_by(Material.record_name).limit(size).offset(offset)))

    counts = services.sample_counts(db, [m.id for m in rows])
    names = services.workspace_names(db, [m.owner_workspace_id for m in rows])
    return Page(
        items=[
            _material_out(
                m,
                sample_count=counts.get(m.id, 0),
                workspace_name=(
                    names.get(m.owner_workspace_id) if m.owner_workspace_id else None
                ),
            )
            for m in rows
        ],
        total=total,
        limit=size,
        offset=offset,
    )


@router.post("", response_model=MaterialOut, status_code=201)
def create_material(
    payload: MaterialCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialOut:
    workspace = services.resolve_workspace(db, user, payload.workspace_slug)
    thickness_m = services.to_si(
        payload.spec_thickness, payload.spec_thickness_unit, field="두께"
    )
    record_name = services.material_record_name(
        grade=payload.grade, details=payload.details, spec_thickness_m=thickness_m
    )
    services.ensure_name_free(db, owner_workspace_id=workspace.id, record_name=record_name)

    material = Material(
        owner_workspace_id=workspace.id,
        record_name=record_name,
        alias=payload.alias,
        details=payload.details,
        spec_thickness_m=thickness_m,
        applied_product=payload.applied_product,
        applied_part=payload.applied_part,
        density_si=services.to_si(payload.density, payload.density_unit, field="밀도"),
        poisson_ratio=payload.poisson_ratio,
        input_units={
            "spec_thickness": payload.spec_thickness_unit,
            "density": payload.density_unit,
        },
        note=payload.note,
        legacy_id=payload.legacy_id,
        registered_by_id=user.id,
    )
    # Grade 는 기준정보를 거친다(ADR 0010). `SECC`/`secc` 가 서로 다른 재료를 만드는
    # 것을 막는다 — 이 축의 이득이 가장 크다.
    vocabulary_services.apply_bindings(
        db,
        material,
        vocabulary_services.MATERIAL_BINDINGS,
        payload.model_dump(),
        created_by_id=user.id,
    )
    db.add(material)
    db.commit()
    return _material_out(material, sample_count=0, workspace_name=workspace.name)


@router.get("/{material_id}", response_model=MaterialOut)
def get_material(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialOut:
    material = services.get_material(db, user, material_id)
    names = services.workspace_names(db, [material.owner_workspace_id])
    return _material_out(
        material,
        sample_count=services.sample_counts(db, [material.id]).get(material.id, 0),
        workspace_name=(
            names.get(material.owner_workspace_id) if material.owner_workspace_id else None
        ),
    )


def _thickness_origin(measured: list[float], total: int) -> str:
    """실측 두께가 몇 개나 채워졌는가. **평균이 아니라 채움 정도가 요점이다** —
    하나라도 비면 그 시편의 응력은 못 낸다."""
    if not total:
        return "시편이 없습니다."
    if not measured:
        return f"시편 {total}개 모두 두께가 비어 있습니다."
    mean_mm = services.from_si(sum(measured) / len(measured), LENGTH_UNIT) or 0.0
    return f"시편 {len(measured)}/{total}개에 있습니다 (평균 {mean_mm:.4g} {LENGTH_UNIT})."


@router.get("/{material_id}/property-sources", response_model=PropertySourcesOut)
def property_sources(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertySourcesOut:
    """이 재료의 값들이 **어디서 와서 어디에 쓰이는가.**

    같은 이름의 값이 여러 층에 산다. 규격 두께는 재료에 있고 이름의 한 칸이지만
    계산에 들어가는 것은 시편의 실측 두께다. 밀도는 재료(공칭)와 시료(실측)에
    둘 다 있고 카드는 실측을 먼저 본다. 푸아송비는 재료에만 있다.

    **이 배치를 사람이 외우게 하면 안 된다.** 외우게 하면 "밀도를 넣었는데
    내보내기가 안 된다"(시료에 넣어야 했는데 재료에 넣었거나 그 반대) 가 난다.
    한 화면에서 값·출처·쓰임을 함께 보여 준다.
    """
    material = services.get_material(db, user, material_id)
    samples = list(db.scalars(select(Sample).where(Sample.material_id == material.id)))
    specimens = list(
        db.scalars(
            select(Specimen)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Sample.material_id == material.id, Specimen.deleted_at.is_(None))
        )
    )

    length_unit = material.input_units.get("spec_thickness", LENGTH_UNIT)
    rows: list[ValueSourceOut] = [
        ValueSourceOut(
            key="spec_thickness",
            label="규격 두께",
            value=services.from_si(material.spec_thickness_m, length_unit),
            display_unit=length_unit,
            level="material",
            origin="재료 이름의 한 칸입니다 — 고치면 이름이 바뀝니다.",
            status="ok" if material.spec_thickness_m is not None else "missing",
            used_for="재료 이름과 검색. 계산에는 쓰지 않습니다.",
            edit_hint=None if material.spec_thickness_m is not None else "재료 수정",
        )
    ]

    # **규격이 치수를 정한다.** 두 줄을 나란히 둬야 그 관계가 보인다 — 규격을
    # 알면서 치수를 비워 두는 것은 대개 아직 안 적은 것이지 없는 것이 아니다.
    standards = {s.standard for s in specimens if s.standard}
    rows.append(
        ValueSourceOut(
            key="specimen_standard",
            label="시편 규격",
            value=None,
            display_unit="",
            level="specimen",
            origin=(
                ", ".join(sorted(standards)) + f" (시편 {len(specimens)}개 중 "
                f"{sum(1 for s in specimens if s.standard)}개에 적힘)"
                if standards
                else "적혀 있지 않습니다. 장비 파일에는 없는 값이라 사람이 넣어야 합니다."
            ),
            status="ok"
            if standards and len(standards) == 1
            else "conflict"
            if standards
            else "missing",
            used_for=(
                "게이지 길이·폭이 여기서 나옵니다. "
                "다른 규격끼리는 연신율을 비교할 수 없습니다."
            ),
            edit_hint=None if len(standards) == 1 else "시편 수정",
        )
    )

    measured = [s.thickness_m for s in specimens if s.thickness_m is not None]
    rows.append(
        ValueSourceOut(
            key="specimen_thickness",
            label="실측 두께",
            value=(
                services.from_si(sum(measured) / len(measured), LENGTH_UNIT)
                if measured
                else None
            ),
            display_unit=LENGTH_UNIT,
            level="specimen",
            origin=_thickness_origin(measured, len(specimens)),
            status=(
                "ok"
                if measured and len(measured) == len(specimens)
                else "conflict"
                if measured
                else "missing"
            ),
            used_for="단면적(폭 곱하기 두께) — 공칭 응력을 만드는 데 씁니다.",
            edit_hint=(
                None
                if measured and len(measured) == len(specimens)
                else "시편 수정 또는 일괄 등록"
            ),
        )
    )

    density_unit = material.input_units.get("density", DENSITY_UNIT)
    lot = {s.density_si for s in samples if s.density_si is not None}
    if len(lot) == 1:
        value, level, origin, status = (
            next(iter(lot)),
            "sample",
            "시료에서 잰 값입니다. 재료 공칭값보다 먼저 씁니다.",
            "ok",
        )
    elif len(lot) > 1:
        joined = ", ".join(f"{v:.4g}" for v in sorted(lot))
        value, level, origin, status = (
            None,
            "sample",
            f"시료마다 다릅니다({joined} kg/m³) — 카드에서 쓸 값을 직접 넣어야 합니다.",
            "conflict",
        )
    elif material.density_si is not None:
        value, level, origin, status = (
            material.density_si,
            "material",
            "재료의 공칭값입니다. 로트에서 잰 값이 있으면 그쪽이 우선합니다.",
            "ok",
        )
    else:
        value, level, origin, status = (None, "material", None, "missing")
    rows.append(
        ValueSourceOut(
            key="density",
            label="밀도",
            value=services.from_si(value, density_unit),
            display_unit=density_unit,
            level=level,
            origin=origin,
            status=status,
            used_for="CAE 카드. OpenRadioss 는 이 값 없이 내보낼 수 없습니다.",
            edit_hint=None if status == "ok" else "재료 수정(공칭) 또는 시료 수정(실측)",
        )
    )

    rows.append(
        ValueSourceOut(
            key="poisson_ratio",
            label="푸아송비",
            value=material.poisson_ratio,
            display_unit="",
            level="material",
            origin=(
                "재료에 적힌 값입니다."
                if material.poisson_ratio is not None
                else "인장시험은 이 값을 주지 않습니다 — 문헌값을 넣습니다."
            ),
            status="ok" if material.poisson_ratio is not None else "missing",
            used_for="CAE 카드. Abaqus·OpenRadioss 모두 이 값이 있어야 합니다.",
            edit_hint=None if material.poisson_ratio is not None else "재료 수정",
        )
    )

    rows.append(
        ValueSourceOut(
            key="youngs_modulus",
            label="탄성계수",
            value=None,
            display_unit="GPa",
            level="result",
            origin="처리에서 잽니다 — 적어 넣는 값이 아닙니다.",
            status="ok",
            used_for="CAE 카드의 탄성. 물성 탭에서 채택된 결과들의 평균을 씁니다.",
            edit_hint=None,
        )
    )

    return PropertySourcesOut(
        material_id=material.id, material_name=material.record_name, rows=rows
    )


@router.patch("/{material_id}", response_model=MaterialOut)
def update_material(
    material_id: uuid.UUID,
    payload: MaterialUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialOut:
    material = services.get_material(db, user, material_id)
    services.require_writable(db, user, material)

    data = payload.model_dump(exclude_unset=True)
    for field in (
        "details",
        "alias",
        "note",
        "poisson_ratio",
        "applied_product",
        "applied_part",
    ):
        if field in data:
            setattr(material, field, data[field])

    if "declared_properties" in data:
        # **통째로 갈아 끼운다.** 검사·단위 변환은 `declared.check` 가 한다 —
        # 차원이 안 맞으면 거기서 막힌다(비열 자리에 열전도도 같은 것).
        material.declared_properties = declared.check(db, data["declared_properties"] or [])

    if "density" in data or "density_unit" in data:
        unit = data.get("density_unit") or material.input_units.get("density", DENSITY_UNIT)
        value = (
            data["density"]
            if "density" in data
            else services.from_si(material.density_si, unit)
        )
        material.density_si = services.to_si(value, unit, field="밀도")
        material.input_units = {**material.input_units, "density": unit}

    if "spec_thickness" in data or "spec_thickness_unit" in data:
        unit = data.get("spec_thickness_unit") or material.input_units.get(
            "spec_thickness", LENGTH_UNIT
        )
        value = (
            data["spec_thickness"]
            if "spec_thickness" in data
            else services.from_si(material.spec_thickness_m, unit)
        )
        material.spec_thickness_m = services.to_si(value, unit, field="두께")
        material.input_units = {**material.input_units, "spec_thickness": unit}

    vocabulary_services.apply_bindings(
        db, material, vocabulary_services.MATERIAL_BINDINGS, data, created_by_id=user.id
    )

    renamed = services.material_record_name(
        grade=material.grade,
        details=material.details,
        spec_thickness_m=material.spec_thickness_m,
    )
    if renamed != material.record_name:
        services.ensure_name_free(
            db,
            owner_workspace_id=material.owner_workspace_id,
            record_name=renamed,
            exclude_id=material.id,
        )
        material.record_name = renamed
        # 이름은 참조 키가 아니므로 다시 계산해 덮으면 그만이다(ADR 0004).
        services.rename_descendants(db, material)

    db.commit()
    names = services.workspace_names(db, [material.owner_workspace_id])
    return _material_out(
        material,
        sample_count=services.sample_counts(db, [material.id]).get(material.id, 0),
        workspace_name=(
            names.get(material.owner_workspace_id) if material.owner_workspace_id else None
        ),
    )


@router.delete("/{material_id}", status_code=204)
def delete_material(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    material = services.get_material(db, user, material_id)
    services.require_writable(db, user, material)

    remaining = services.sample_counts(db, [material.id]).get(material.id, 0)
    if remaining:
        raise Conflict(
            "MNX-MATERIALS-0006",
            f"시료 {remaining}건이 남아 있어 지울 수 없습니다. 먼저 시료를 정리하세요.",
        )
    material.deleted_at = _now()
    vocabulary_services.release_bindings(db, material, vocabulary_services.MATERIAL_BINDINGS)
    # 소프트 삭제라 행은 남지만 **목록에서 사라진다.** 누가 치웠는지 남지 않으면
    # "있던 재료가 없어졌다" 를 설명할 길이 없다.
    audit.record(
        db,
        action=audit.MATERIAL_DELETED,
        actor=user,
        target_table="materials",
        target_id=material.id,
        target_label=material.record_name,
        workspace_id=material.owner_workspace_id,
        changes={"deleted_at": {"after": material.deleted_at.isoformat()}},
    )
    db.commit()
    return Response(status_code=204)


# --- 시료 -------------------------------------------------------------------


@router.get("/{material_id}/samples", response_model=list[SampleOut])
def list_samples(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[SampleOut]:
    material = services.get_material(db, user, material_id)
    rows = list(
        db.scalars(
            select(Sample)
            .where(Sample.material_id == material.id, Sample.deleted_at.is_(None))
            .order_by(Sample.seq_no)
        )
    )
    counts = services.specimen_counts(db, [s.id for s in rows])
    names = services.workspace_names(db, [s.workspace_id for s in rows])
    tallies = _run_tallies(
        db, group_by=Specimen.sample_id, ids=[s.id for s in rows], join_specimen=True
    )
    return [
        _sample_out(
            s,
            specimen_count=counts.get(s.id, 0),
            workspace_name=names.get(s.workspace_id),
            runs=tallies.get(s.id, (0, 0, 0)),
        )
        for s in rows
    ]


@router.post("/{material_id}/samples", response_model=SampleOut, status_code=201)
def create_sample(
    material_id: uuid.UUID,
    payload: SampleCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SampleOut:
    material = services.get_material(db, user, material_id)
    workspace = services.resolve_workspace(db, user, payload.workspace_slug)

    seq_no = services.next_sample_seq(db, material.id)
    sample = Sample(
        workspace_id=workspace.id,
        material_id=material.id,
        seq_no=seq_no,
        record_name=naming.sample_name(material=material.record_name, seq_no=seq_no),
        alias=payload.alias,
        lot_no=payload.lot_no,
        # 기준정보를 거치는 값들은 아래 `apply_bindings` 가 넣는다.
        production_date=payload.production_date,
        density_si=services.to_si(payload.density, payload.density_unit, field="밀도"),
        input_units={"density": payload.density_unit},
        note=payload.note,
        registered_by_id=user.id,
    )
    # **기준정보를 거쳐 들어간다**(ADR 0010). 문자열도 함께 채운다 — 아직 옮기는
    # 중이라 읽는 쪽이 문자열을 본다(Expand 단계).
    vocabulary_services.apply_bindings(
        db,
        sample,
        vocabulary_services.SAMPLE_BINDINGS,
        payload.model_dump(),
        created_by_id=user.id,
    )
    db.add(sample)
    db.commit()
    return _sample_out(sample, specimen_count=0, workspace_name=workspace.name)


def _get_sample(db: Session, user: User, sample_id: uuid.UUID) -> Sample:
    sample = db.scalar(
        select(Sample).where(Sample.id == sample_id, Sample.deleted_at.is_(None))
    )
    if sample is None:
        raise NotFound("MNX-MATERIALS-0002", "시료를 찾을 수 없습니다.")
    services.get_material(db, user, sample.material_id)  # 가시 범위 확인
    return sample


@samples_router.get("/{sample_id}/mill-check", response_model=MillCheckOut)
def mill_check(
    sample_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MillCheckOut:
    """밀시트가 말한 값과 **우리가 잰 값을 나란히.**

    이것이 시료 층 선언 물성의 쓸모다. 값을 적어 두기만 하면 기록으로 끝나는데,
    같은 물성을 우리 처리 결과가 낸다 — `proof_stress`·`tensile_strength` 가
    밀시트의 항복강도·인장강도와 같은 값이다.

    ## 무엇을 세는가

    **채택된 처리 결과만**(ADR 0007). 채택은 "이 계산을 이 시험의 답으로 삼는다"
    는 선언이고, 안 채택된 것까지 평균에 넣으면 시험해 본 것과 결론을 낸 것이
    섞인다.

    ## 판정하지 않는다

    차이를 비율로 낼 뿐 「맞다/틀리다」를 말하지 않는다. 몇 %부터 문제인지는
    규격과 용도가 정하고, 그것을 여기서 상수로 박으면 **그 숫자가 곧 규격 행세를
    한다.**
    """
    sample = _get_sample(db, user, sample_id)
    known = declared.catalog(db)

    # 이 시료의 시편들에서 채택된 결과의 스칼라를 모은다.
    measured: dict[str, list[float]] = {}
    rows = db.execute(
        select(ProcessingResult.scalars)
        .join(TestRun, TestRun.adopted_result_id == ProcessingResult.id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .where(
            Specimen.sample_id == sample.id,
            Specimen.deleted_at.is_(None),
            TestRun.deleted_at.is_(None),
        )
    ).scalars()
    for scalars in rows:
        for scalar in scalars or []:
            value = scalar.get("value")
            if isinstance(value, (int, float)):
                measured.setdefault(str(scalar.get("key", "")), []).append(float(value))

    out: list[MillCheckRowOut] = []
    for row in sample.declared_properties or []:
        spec = known.get(str(row.get("item"))) or {}
        # **척도로 재는 물성은 안 견준다.** 우리가 내는 스칼라는 SI 값이고
        # 밀시트의 경도는 척도 위의 숫자다 — 둘을 빼면 숫자는 나오는데 뜻이
        # 없다. 이어져 있더라도 여기서 끊는다.
        key = "" if spec.get("scales") else str(spec.get("measured_key") or "")
        found = measured.get(key) or []
        mean = sum(found) / len(found) if found else None
        # **첫 점과 견준다.** 밀시트는 대개 상온 한 점이고, 여러 온도를 적어
        # 두었다면 우리가 잰 온도와 짝지을 방법이 없다 — 그 짝짓기는 시험
        # 조건까지 봐야 하는 다른 일이다.
        points = row.get("points") or []
        if not points:
            continue
        stated = float(points[0]["value_si"])
        out.append(
            MillCheckRowOut(
                item=str(row["item"]),
                label=str(row["item"]),
                declared=stated,
                declared_unit=str(row.get("scale") or row.get("input_unit") or ""),
                reference=str(row.get("reference") or ""),
                measured=mean,
                measured_count=len(found),
                si_unit=str(spec.get("si_unit") or "1"),
                # **적은 값이 0 이면 비율이 뜻을 잃는다.** 나눗셈을 막는 것이
                # 아니라, 그 자리에 낼 답이 없다는 뜻이다.
                difference=(
                    (mean - stated) / stated if mean is not None and stated != 0 else None
                ),
                note=_why_not_compared(bool(found), spec, key),
            )
        )
    return MillCheckOut(sample_name=sample.record_name, rows=out)


@samples_router.get("/{sample_id}", response_model=SampleOut)
def get_sample(
    sample_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SampleOut:
    sample = _get_sample(db, user, sample_id)
    names = services.workspace_names(db, [sample.workspace_id])
    return _sample_out(
        sample,
        specimen_count=services.specimen_counts(db, [sample.id]).get(sample.id, 0),
        workspace_name=names.get(sample.workspace_id),
    )


@samples_router.patch("/{sample_id}", response_model=SampleOut)
def update_sample(
    sample_id: uuid.UUID,
    payload: SampleUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SampleOut:
    sample = _get_sample(db, user, sample_id)
    data = payload.model_dump(exclude_unset=True)

    for field in (
        "lot_no",
        "alias",
        "production_date",
        "note",
    ):
        if field in data:
            setattr(sample, field, data[field])

    vocabulary_services.apply_bindings(
        db, sample, vocabulary_services.SAMPLE_BINDINGS, data, created_by_id=user.id
    )

    if "declared_properties" in data:
        # **시료 층이다.** 항목이 그 층의 것인지는 `check` 가 본다 — 탄성계수를
        # 여기 적으면 같은 값을 로트 수만큼 적게 되고, 그중 하나만 고쳐진다.
        sample.declared_properties = declared.check(
            db, data["declared_properties"] or [], level="시료"
        )

    if "density" in data or "density_unit" in data:
        unit = data.get("density_unit") or sample.input_units.get("density", DENSITY_UNIT)
        value = (
            data["density"] if "density" in data else services.from_si(sample.density_si, unit)
        )
        sample.density_si = services.to_si(value, unit, field="밀도")
        sample.input_units = {**sample.input_units, "density": unit}

    db.commit()
    names = services.workspace_names(db, [sample.workspace_id])
    return _sample_out(
        sample,
        specimen_count=services.specimen_counts(db, [sample.id]).get(sample.id, 0),
        workspace_name=names.get(sample.workspace_id),
    )


@samples_router.delete("/{sample_id}", status_code=204)
def delete_sample(
    sample_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    sample = _get_sample(db, user, sample_id)
    remaining = services.specimen_counts(db, [sample.id]).get(sample.id, 0)
    if remaining:
        raise Conflict(
            "MNX-MATERIALS-0006",
            f"시편 {remaining}건이 남아 있어 지울 수 없습니다.",
        )
    sample.deleted_at = _now()
    vocabulary_services.release_bindings(db, sample, vocabulary_services.SAMPLE_BINDINGS)
    db.commit()
    return Response(status_code=204)


# --- 시편 -------------------------------------------------------------------


@samples_router.get("/{sample_id}/specimens", response_model=list[SpecimenOut])
def list_specimens(
    sample_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[SpecimenOut]:
    sample = _get_sample(db, user, sample_id)
    rows = list(
        db.scalars(
            select(Specimen)
            .where(Specimen.sample_id == sample.id, Specimen.deleted_at.is_(None))
            .order_by(Specimen.orientation, Specimen.seq_no)
        )
    )
    tallies = _run_tallies(
        db,
        group_by=TestRun.specimen_id,
        ids=[item.id for item in rows],
        join_specimen=False,
    )
    # **규격별로 한 번에 읽는다.** 시편마다 읽으면 N+1 이고, 한 시료의 시편은
    # 대개 같은 규격이라 한 벌만 읽으면 된다.
    sizes = specimen_size.sizes_for(db, rows)
    return [
        _specimen_out(item, runs=tallies.get(item.id, (0, 0, 0)), sizes=sizes.get(item.id))
        for item in rows
    ]


@samples_router.post("/{sample_id}/specimens", response_model=SpecimenOut, status_code=201)
def create_specimen(
    sample_id: uuid.UUID,
    payload: SpecimenCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenOut:
    sample = _get_sample(db, user, sample_id)

    orientation = payload.orientation.upper()
    if orientation not in ORIENTATIONS:
        raise AppError(
            "MNX-MATERIALS-0012",
            f"방향은 {', '.join(ORIENTATIONS)} 중 하나여야 합니다.",
            status=422,
        )

    seq_no = payload.seq_no or services.next_specimen_seq(db, sample.id, orientation)
    specimen = Specimen(
        workspace_id=sample.workspace_id,
        sample_id=sample.id,
        seq_no=seq_no,
        orientation=orientation,
        record_name=naming.specimen_name(
            sample=sample.record_name, orientation=orientation, seq_no=seq_no
        ),
        thickness_m=services.to_si(payload.thickness, payload.length_unit, field="두께"),
        width_m=services.to_si(payload.width, payload.length_unit, field="폭"),
        gauge_length_m=services.to_si(
            payload.gauge_length, payload.length_unit, field="게이지 길이"
        ),
        input_units={"length": payload.length_unit},
        note=payload.note,
        registered_by_id=user.id,
    )
    vocabulary_services.apply_bindings(
        db,
        specimen,
        vocabulary_services.SPECIMEN_BINDINGS,
        payload.model_dump(),
        created_by_id=user.id,
    )
    db.add(specimen)
    try:
        db.commit()
    except Exception as exc:  # 같은 방향·번호가 이미 있다
        db.rollback()
        raise Conflict(
            "MNX-MATERIALS-0013",
            f"{orientation} 방향 {seq_no}번 시편이 이미 있습니다.",
        ) from exc
    return _specimen_out(specimen)


def _get_specimen(db: Session, user: User, specimen_id: uuid.UUID) -> Specimen:
    specimen = db.scalar(
        select(Specimen).where(Specimen.id == specimen_id, Specimen.deleted_at.is_(None))
    )
    if specimen is None:
        raise NotFound("MNX-MATERIALS-0003", "시편을 찾을 수 없습니다.")
    _get_sample(db, user, specimen.sample_id)  # 가시 범위 확인
    return specimen


@specimens_router.get("/{specimen_id}", response_model=SpecimenOut)
def get_specimen(
    specimen_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenOut:
    return _specimen_out(_get_specimen(db, user, specimen_id))


@specimens_router.patch("/{specimen_id}", response_model=SpecimenOut)
def update_specimen(
    specimen_id: uuid.UUID,
    payload: SpecimenUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenOut:
    specimen = _get_specimen(db, user, specimen_id)
    data = payload.model_dump(exclude_unset=True)
    unit = data.get("length_unit") or specimen.input_units.get("length", LENGTH_UNIT)

    for field, column in (
        ("thickness", "thickness_m"),
        ("width", "width_m"),
        ("gauge_length", "gauge_length_m"),
    ):
        if field in data:
            setattr(specimen, column, services.to_si(data[field], unit, field=field))
    if "note" in data:
        specimen.note = data["note"]
    vocabulary_services.apply_bindings(
        db, specimen, vocabulary_services.SPECIMEN_BINDINGS, data, created_by_id=user.id
    )
    specimen.input_units = {**specimen.input_units, "length": unit}

    db.commit()
    return _specimen_out(specimen)


@specimens_router.get("/{specimen_id}/dimensions", response_model=SpecimenSizesOut)
def get_specimen_dimensions(
    specimen_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenSizesOut:
    """이 시편이 가질 수 있는 치수 칸과 지금 값.

    **칸 목록을 화면에 적지 않는다.** 규격이 정하기 때문이다 — 환봉 규격에는
    직경 칸이 나오고 평판 규격에는 안 나온다. 화면에 세 칸(두께·폭·게이지)을
    박아 두면 환봉을 영영 못 담는다.
    """
    specimen = _get_specimen(db, user, specimen_id)
    sizes = specimen_size.sizes_of(db, specimen)
    area = specimen_size.area_detail(db, specimen)
    shape = specimen_kit.CROSS_SECTIONS.get(sizes.cross_section or "")

    known = {field.key for field in sizes.fields}
    # 규격이 정한 칸 + 규격에서 사라졌는데 값이 남은 칸. **뒤엣것을 숨기면
    # 사람은 안 지워지는 값을 보게 된다** — 규격을 바꿔도 옛 실측은 남는다.
    orphans = [
        vocabulary_services.Field(
            key=key,
            label=specimen_size.LEGACY_LABELS.get(key, key),
            dimension="length",
            si_unit="m",
            is_required=False,
            help="지금 규격에는 없는 칸입니다. 비우면 사라집니다.",
            inherited=False,
        )
        for key in sizes.measured
        if key not in known
    ]

    fields: list[SpecimenSizeOut] = []
    for field in [*sizes.fields, *orphans]:
        measured = sizes.measured.get(field.key)
        nominal = sizes.nominal.get(field.key)
        source = "measured" if measured is not None else None
        if source is None and nominal is not None:
            source = "nominal"
        fields.append(
            SpecimenSizeOut(
                key=field.key,
                label=field.label,
                dimension=field.dimension,
                si_unit=field.si_unit,
                is_required=field.is_required,
                help=field.help,
                inherited=field.inherited,
                nominal=nominal,
                measured=measured,
                source=source,
            )
        )

    return SpecimenSizesOut(
        warnings=[
            SpecimenWarningOut(
                condition=item.check.label({f.key: f.label for f in sizes.fields}),
                actual=item.actual,
                help=item.check.help,
            )
            for item in sizes.violations()
        ],
        standard=sizes.standard,
        cross_section=sizes.cross_section,
        cross_section_label=shape.label if shape else None,
        area=area.value,
        area_problem=area.problem,
        fields=fields,
    )


@specimens_router.put("/{specimen_id}/dimensions", response_model=SpecimenSizesOut)
def put_specimen_dimensions(
    specimen_id: uuid.UUID,
    payload: SpecimenSizesRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenSizesOut:
    """잰 값을 적는다. **규격의 공칭은 복사하지 않는다.**

    복사하면 그 순간 둘이 같아 보이고, 규격을 고쳐도 시편은 옛 값을 든 채 남는다.
    """
    specimen = _get_specimen(db, user, specimen_id)

    values: dict[str, float] = {}
    for key, raw in payload.dimensions.items():
        value = float(raw)
        if value <= 0:
            raise AppError(
                "MNX-MATERIALS-0016",
                f"{key} 는 0 보다 커야 합니다. 안 쟀으면 칸을 비우세요 — "
                "0 은 '쟀는데 0' 이라는 뜻이고 그것으로 나누면 응력이 무한대가 됩니다.",
                status=422,
            )
        values[key] = value
    specimen.dimensions = values

    # **옛 컬럼도 함께 적는다**(ADR 0010 Expand). 아직 그쪽을 읽는 코드가 있다.
    for key, column in specimen_size.LEGACY_COLUMNS.items():
        setattr(specimen, column, values.get(key))

    db.commit()
    return get_specimen_dimensions(specimen_id, user=user, db=db)


@specimens_router.delete("/{specimen_id}", status_code=204)
def delete_specimen(
    specimen_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    specimen = _get_specimen(db, user, specimen_id)
    runs = (
        db.scalar(
            select(func.count())
            .select_from(TestRun)
            .where(TestRun.specimen_id == specimen.id, TestRun.deleted_at.is_(None))
        )
        or 0
    )
    if runs:
        raise Conflict("MNX-MATERIALS-0006", f"시험 {runs}건이 남아 있어 지울 수 없습니다.")
    specimen.deleted_at = _now()
    vocabulary_services.release_bindings(db, specimen, vocabulary_services.SPECIMEN_BINDINGS)
    db.commit()
    return Response(status_code=204)
