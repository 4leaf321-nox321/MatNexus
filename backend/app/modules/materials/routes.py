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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.materials import declared, services
from app.modules.materials.models import ORIENTATIONS, Material, Sample, Specimen
from app.modules.materials.schemas import (
    DENSITY_UNIT,
    LENGTH_UNIT,
    BulkBlockedOut,
    BulkDeletePlanOut,
    BulkMadeOut,
    BulkMaterialRequest,
    BulkOut,
    BulkRequest,
    CascadeDeleteOut,
    CascadeDeleteRequest,
    ClassificationOut,
    DeclaredPointOut,
    DeclaredPropertyOut,
    DeletePlanOut,
    MaterialBlockedOut,
    MaterialCreateRequest,
    MaterialDeleteOut,
    MaterialDeleteRequest,
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
    SpecimenBulkUpdateOut,
    SpecimenBulkUpdateRequest,
    SpecimenCreateRequest,
    SpecimenOut,
    SpecimenRowOut,
    SpecimenSizeOut,
    SpecimenSizesOut,
    SpecimenSizesRequest,
    SpecimenUpdateOut,
    SpecimenUpdateRequest,
    SpecimenWarningOut,
    ValueSourceOut,
)
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.models import VocabularyTerm
from app.modules.workspaces.models import Workspace
from app.shared import audit, contention, display, permissions, sorting, specimen_size
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
    material: Material,
    *,
    sample_count: int,
    workspace_name: str | None,
    uses: dict[str, list[str]] | None = None,
) -> MaterialOut:
    """`uses` 는 **밖에서 미리 읽어 넘긴다** — 목록이 재료마다 물으면 N+1 이다."""
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
        applied_products=(uses or {}).get("product", []),
        applied_parts=(uses or {}).get("part", []),
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
    registered_by: str | None = None,
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
        registered_by=registered_by,
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
    registered_by: str | None = None,
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
        registered_by=registered_by,
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
        payload.spec_thickness,
        payload.spec_thickness_unit,
        field="두께",
        dimension="length",
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

#: 정렬할 수 있는 열. **화면이 목록을 정하지 않는다** — 모르는 이름은 거절한다.
#:
#: 두께·시료 수가 없는 이유는 거르기와 같다. 두께는 컬럼이 있어 넣었고, 시료 수는
#: 세어야 나오는 값이라 정렬하려면 매번 집계를 걸어야 한다 — 그건 이 목록이
#: 느려지는 첫 번째 이유가 된다.
MATERIAL_SORTS = {
    "created_at": Material.created_at,
    "record_name": Material.record_name,
    "alias": Material.alias,
    "family": Material.family,
    "category": Material.category,
    "spec_thickness": Material.spec_thickness_m,
}

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
    name: str | None = Query(default=None, description="이름만 부분 일치"),
    alias: str | None = Query(default=None, description="별칭만 부분 일치"),
    family: str | None = None,
    category: str | None = None,
    scope: str = Query(default="all", pattern="^(all|mine|global)$"),
    workspace: str | None = Query(default=None),
    sort: str | None = Query(default=None, description="정렬할 열. 기본은 등록 일시"),
    desc: bool = Query(default=True, description="내림차순. 기본은 최근 등록순"),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[MaterialOut]:
    query = services.visible_materials(db, user)
    for condition in _search_terms(db, q):
        query = query.where(condition)
    # **열 머리의 거르기.** `q` 는 여러 칸을 한꺼번에 뒤지는데(이름·별칭·분류),
    # 열 머리에서 거를 때는 **그 열만** 봐야 한다 — 「이름」 칸에 친 글자가 별칭에
    # 걸려 나오면 그 칸이 무엇을 거르는지 알 수 없게 된다.
    if name:
        query = query.where(Material.record_name.ilike(f"%{name}%"))
    if alias:
        query = query.where(Material.alias.ilike(f"%{alias}%"))
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
    # **어느 부서 것인가.** `scope` 는 「전역인가 아닌가」 만 갈랐다 — 부서가 여럿인
    # 곳에서는 그것으로 「고분자팀 재료」 를 못 찾는다. slug 로 그 부서만 남긴다.
    if workspace:
        query = query.where(
            Material.owner_workspace_id == permissions.workspace_by_slug(db, workspace).id
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    rows = list(
        db.scalars(
            query.order_by(
                *sorting.order_by(
                    MATERIAL_SORTS,
                    sort=sort,
                    desc=desc,
                    default="created_at",
                    tiebreaker=Material.id,
                )
            )
            .limit(size)
            .offset(offset)
        )
    )

    counts = services.sample_counts(db, [m.id for m in rows])
    names = services.workspace_names(db, [m.owner_workspace_id for m in rows])
    # **한 번에 읽는다.** 재료마다 물으면 200건짜리 화면에서 200번이 된다.
    uses = services.uses_of(db, [m.id for m in rows])
    return Page(
        items=[
            _material_out(
                m,
                sample_count=counts.get(m.id, 0),
                workspace_name=(
                    names.get(m.owner_workspace_id) if m.owner_workspace_id else None
                ),
                uses=uses.get(m.id),
            )
            for m in rows
        ],
        total=total,
        limit=size,
        offset=offset,
    )


def _record_name(payload: MaterialCreateRequest) -> str:
    """이 값들이 만들 재료 이름. **이름을 만드는 곳은 서버 하나다**(ADR 0004)."""
    return services.material_record_name(
        grade=payload.grade,
        details=payload.details,
        spec_thickness_m=services.to_si(
            payload.spec_thickness,
            payload.spec_thickness_unit,
            field="두께",
            dimension="length",
        ),
    )


def _make_material(
    db: Session, user: User, payload: MaterialCreateRequest, *, workspace: Workspace
) -> Material:
    """재료 하나를 만들어 세션에 넣는다 — **커밋은 부르는 쪽이 한다.**

    하나씩 등록하는 길과 한꺼번에 넣는 길이 같은 코드를 지나게 하려고 뺐다.
    두 벌로 두면 한쪽에만 기준정보 연결이 붙거나, 한쪽만 단위를 기록하는 일이
    생긴다 — 그때 나는 차이는 몇 달 뒤 목록에서야 보인다.
    """
    record_name = _record_name(payload)
    services.ensure_name_free(db, owner_workspace_id=workspace.id, record_name=record_name)

    material = Material(
        owner_workspace_id=workspace.id,
        record_name=record_name,
        alias=payload.alias,
        details=payload.details,
        spec_thickness_m=services.to_si(
            payload.spec_thickness,
            payload.spec_thickness_unit,
            field="두께",
            dimension="length",
        ),
        density_si=services.to_si(
            payload.density, payload.density_unit, field="밀도", dimension="density"
        ),
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
    try:
        db.flush()
    except IntegrityError as exc:
        # **`ensure_name_free` 를 지나왔어도 부딪힌다.** 검사와 넣기 사이에 남이
        # 같은 이름을 넣을 수 있다 — 그때 500 을 내면 사람은 자기가 뭘 잘못했는지
        # 알 수 없다. 이름은 사람이 정한 값이라 말없이 바꾸지 않는다.
        db.rollback()
        raise Conflict(
            "MNX-MATERIALS-0004",
            f"같은 이름의 재료가 이미 있습니다: {material.record_name}",
        ) from exc
    # 용도는 재료의 칸이 아니라 매달린 줄이라, 재료가 id 를 받은 뒤에 붙는다.
    services.set_uses(db, material, "product", payload.applied_products, created_by_id=user.id)
    services.set_uses(db, material, "part", payload.applied_parts, created_by_id=user.id)
    return material


@router.post("", response_model=MaterialOut, status_code=201)
def create_material(
    payload: MaterialCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialOut:
    workspace = services.resolve_workspace(db, user, payload.workspace_slug)
    material = _make_material(db, user, payload, workspace=workspace)
    db.commit()
    return _material_out(
        material,
        sample_count=0,
        workspace_name=workspace.name,
        uses=services.uses_of(db, [material.id]).get(material.id),
    )


@router.post("/delete-plan", response_model=BulkDeletePlanOut)
def bulk_delete_plan(
    payload: MaterialDeleteRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BulkDeletePlanOut:
    """고른 것들을 아래까지 지우면 **모두 합쳐** 무엇이 사라지는가.

    낱개로 세어 보여 주지 않는다 — 200건을 고른 화면에서 200줄을 읽는 사람은
    없다. 대신 **못 지우는 것(권한)은 낱개로** 말한다. 그건 사람이 손을 써야
    하는 자리이고, 개수만 주면 무엇을 해야 할지 알 수 없다.
    """
    totals = {"samples": 0, "specimens": 0, "test_runs": 0}
    blocked: list[MaterialBlockedOut] = []
    counted = 0

    for material_id in payload.material_ids:
        try:
            material = services.get_material(db, user, material_id)
            services.require_writable(db, user, material)
        except AppError as exc:
            blocked.append(MaterialBlockedOut(id=material_id, name=None, reason=exc.message))
            continue
        plan = services.delete_plan(db, material)
        totals["samples"] += plan.samples
        totals["specimens"] += plan.specimens
        totals["test_runs"] += plan.test_runs
        counted += 1

    return BulkDeletePlanOut(materials=counted, blocked=blocked, **totals)


@router.post("/delete", response_model=MaterialDeleteOut)
def delete_materials(
    payload: MaterialDeleteRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialDeleteOut:
    """여러 개를 한 번에 지운다. **하나가 막혀도 나머지는 지운다.**

    막히는 이유가 둘이라 이유를 함께 돌려준다 — 권한이 없는 것과 시료가 남아
    있는 것. 사람이 해야 할 일이 다르다(관리자에게 말하기 · 시료 먼저 치우기).
    개수만 주면 그 둘을 구별할 수 없다.

    `DELETE` 가 아니라 `POST /delete` 인 이유는 시험 쪽과 같다: 본문에 목록을
    싣는다.
    """
    counts = services.sample_counts(db, payload.material_ids)
    deleted = 0
    blocked: list[MaterialBlockedOut] = []
    tally = {"samples": 0, "specimens": 0, "test_runs": 0}
    now = _now()

    for material_id in payload.material_ids:
        try:
            material = services.get_material(db, user, material_id)
            services.require_writable(db, user, material)
        except AppError as exc:
            # **이름을 모르면 id 라도 준다.** 조용히 세지 않는 것이 요점이다.
            blocked.append(MaterialBlockedOut(id=material_id, name=None, reason=exc.message))
            continue

        if not payload.cascade:
            remaining = counts.get(material.id, 0)
            if remaining:
                blocked.append(
                    MaterialBlockedOut(
                        id=material.id,
                        name=material.record_name,
                        reason=f"시료 {remaining}건이 남아 있습니다",
                    )
                )
                continue
        elif not payload.include_test_runs:
            # **시험은 따로 허락을 받는다.** 하나라도 시험을 물고 있으면 그 하나만
            # 막는다 — 200건 중 하나 때문에 199건을 못 지우게 하지 않는다.
            waiting = services.delete_plan(db, material)
            if waiting.test_runs:
                blocked.append(
                    MaterialBlockedOut(
                        id=material.id,
                        name=material.record_name,
                        reason=f"시험 {waiting.test_runs}건이 매달려 있습니다",
                    )
                )
                continue

        if payload.cascade:
            done = services.delete_tree(db, material, actor=user, now=now)
            tally["samples"] += done.samples
            tally["specimens"] += done.specimens
            tally["test_runs"] += done.test_runs
        else:
            material.deleted_at = now
            vocabulary_services.release_bindings(
                db, material, vocabulary_services.MATERIAL_BINDINGS
            )
            services.release_uses(db, material)
            audit.record(
                db,
                action=audit.MATERIAL_DELETED,
                actor=user,
                target_table="materials",
                target_id=material.id,
                target_label=material.record_name,
                workspace_id=material.owner_workspace_id,
                changes={"deleted_at": {"after": now.isoformat()}},
            )
        deleted += 1

    db.commit()
    return MaterialDeleteOut(deleted=deleted, blocked=blocked, **tally)


def _skipped(material: BulkMaterialRequest, why: str) -> list[BulkBlockedOut]:
    """재료가 막혔으면 그 아래도 못 만든다. **말 없이 사라지게 두지 않는다.**"""
    out: list[BulkBlockedOut] = []
    for sample in material.samples:
        out.append(BulkBlockedOut(row=sample.row, reason=why))
        out.extend(BulkBlockedOut(row=item.row, reason=why) for item in sample.specimens)
    return out


@router.post("/bulk", response_model=BulkOut)
def create_bulk(
    payload: BulkRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BulkOut:
    """재료·시료·시편을 한 번에 넣는다.

    ## 마디마다 세이브포인트

    시편 하나가 막혔다고 재료와 시료까지 되돌리면, 사람은 스무 줄을 다시
    적어야 한다. **만들 수 있는 것은 만들고, 못 만든 마디는 줄 번호와 이유로
    돌려준다.** 그래서 마디마다 `begin_nested()` 로 감싼다 — 실패한 마디만
    되감기고 세션은 계속 쓸 수 있다.

    ## 이미 있는 재료는 찾아 쓴다

    같은 재료 아래에 시료를 여러 벌 넣는 것이 이 기능의 요점이다. 그런데
    **딸린 것이 없는데 이름만 겹치면 그것은 실수다** — 조용히 넘어가면 아무것도
    안 만들어졌는데 성공으로 읽힌다. 그때만 막는다.
    """
    made: list[BulkMadeOut] = []
    blocked: list[BulkBlockedOut] = []
    materials = samples = specimens = 0

    for item in payload.materials:
        try:
            with db.begin_nested():
                workspace = services.resolve_workspace(db, user, item.workspace_slug)
                record_name = _record_name(item)
                material = services.find_by_name(
                    db, owner_workspace_id=workspace.id, record_name=record_name
                )
                reused = material is not None
                if material is None:
                    material = _make_material(db, user, item, workspace=workspace)
                elif not item.samples:
                    raise Conflict(
                        "MNX-MATERIALS-0004",
                        f"같은 이름의 재료가 이미 있습니다: {record_name}. "
                        f"그 재료에 시료·시편을 더하려면 **같은 줄에 시료·시편을 "
                        f"함께 적으세요** — 그러면 있는 재료를 그대로 씁니다.",
                    )
                else:
                    services.require_writable(db, user, material)
        except AppError as exc:
            blocked.append(BulkBlockedOut(row=item.row, reason=exc.message))
            blocked.extend(_skipped(item, "재료를 만들지 못해 건너뛰었습니다"))
            continue

        made.append(
            BulkMadeOut(row=item.row, kind="material", name=record_name, reused=reused)
        )
        if not reused:
            materials += 1

        for entry in item.samples:
            try:
                with db.begin_nested():
                    sample = _make_sample(db, user, material, entry, workspace=workspace)
            except AppError as exc:
                blocked.append(BulkBlockedOut(row=entry.row, reason=exc.message))
                blocked.extend(
                    BulkBlockedOut(row=one.row, reason="시료를 만들지 못해 건너뛰었습니다")
                    for one in entry.specimens
                )
                continue

            samples += 1
            made.append(BulkMadeOut(row=entry.row, kind="sample", name=sample.record_name))

            for one in entry.specimens:
                try:
                    with db.begin_nested():
                        specimen = _make_specimen(db, user, sample, one)
                except AppError as exc:
                    blocked.append(BulkBlockedOut(row=one.row, reason=exc.message))
                    continue
                specimens += 1
                made.append(
                    BulkMadeOut(row=one.row, kind="specimen", name=specimen.record_name)
                )

    db.commit()
    return BulkOut(
        materials=materials,
        samples=samples,
        specimens=specimens,
        made=made,
        blocked=blocked,
    )


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
        uses=services.uses_of(db, [material.id]).get(material.id),
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
        joined = ", ".join(display.density_text(v) for v in sorted(lot))
        value, level, origin, status = (
            None,
            "sample",
            f"시료마다 다릅니다({joined}) — 카드에서 쓸 값을 직접 넣어야 합니다.",
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
    for field in ("details", "alias", "note", "poisson_ratio"):
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
        material.density_si = services.to_si(value, unit, field="밀도", dimension="density")
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
        material.spec_thickness_m = services.to_si(
            value, unit, field="두께", dimension="length"
        )
        material.input_units = {**material.input_units, "spec_thickness": unit}

    for field, axis in (("applied_products", "product"), ("applied_parts", "part")):
        if field in data:
            # 안 보낸 것과 비운 것을 구별한다 — 빈 목록을 보내면 다 지우는 뜻이다.
            services.set_uses(db, material, axis, data[field] or [], created_by_id=user.id)

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
        uses=services.uses_of(db, [material.id]).get(material.id),
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
    services.release_uses(db, material)
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


@router.get("/{material_id}/delete-plan", response_model=DeletePlanOut)
def delete_plan(
    material_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DeletePlanOut:
    """지우기 전에 **무엇이 함께 사라지는지** 보여 준다.

    화면이 세지 않게 서버가 낸다. 화면이 나름대로 세면 사람이 본 숫자와 실제로
    지워지는 것이 어긋나고, 그러면 그 「예」 는 다른 것에 대한 대답이 된다.
    """
    material = services.get_material(db, user, material_id)
    plan = services.delete_plan(db, material)
    return DeletePlanOut(
        material_name=material.record_name,
        samples=plan.samples,
        specimens=plan.specimens,
        test_runs=plan.test_runs,
    )


@router.post("/{material_id}/delete-cascade", response_model=CascadeDeleteOut)
def delete_material_cascade(
    material_id: uuid.UUID,
    payload: CascadeDeleteRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CascadeDeleteOut:
    """재료를 **아래까지 통째로** 지운다 — 시험 → 시편 → 시료 → 재료 순서로.

    ## 왜 따로 두나

    `DELETE /materials/{id}` 는 시료가 남아 있으면 막는다. 그게 맞다 — 재료 하나를
    지우는 뜻으로 누른 버튼이 시험 200건을 함께 지우면 안 된다. 그런데 그러면
    **정리할 방법이 아예 없다.** 시편을 하나씩, 시료를 하나씩 지워 올라가야 하는데
    이관을 다시 돌릴 때마다 그 일을 한다.

    그래서 「통째로」 를 **다른 문**으로 낸다. 실수로 눌리지 않고, 무엇이 사라지는지
    먼저 보고 나서 부르게 한다(`GET /delete-plan`).

    ## 왜 시험만 따로 허락을 받나

    시료·시편은 이름표에 가깝지만 **시험은 잰 값이다** — 곡선과 처리 결과가 거기
    매달려 있다. 한 칸으로 묶으면 「시료 정리하려다 측정 데이터를 날렸다」 가 난다.

    ## 순서

    아래에서 위로 간다. 위에서부터 지우면 중간에 실패했을 때 **부모는 사라지고
    자식은 남는다** — 그 자식은 화면 어디에서도 닿을 수 없게 된다.
    """
    material = services.get_material(db, user, material_id)
    services.require_writable(db, user, material)

    # **허락을 먼저 본다.** 지우기 시작한 뒤에 막으면 절반만 지워진 트리가 남는다.
    waiting = services.delete_plan(db, material)
    if waiting.test_runs and not payload.include_test_runs:
        raise Conflict(
            "MNX-MATERIALS-0029",
            f"시험 {waiting.test_runs}건이 함께 지워집니다 — 곡선과 처리 결과가 거기 "
            f"매달려 있습니다. 그래도 지우려면 시험까지 지우기를 함께 켜세요.",
        )

    done = services.delete_tree(db, material, actor=user, now=_now())
    db.commit()
    return CascadeDeleteOut(
        material_name=material.record_name,
        samples=done.samples,
        specimens=done.specimens,
        test_runs=done.test_runs,
    )


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
    # **한 번에 읽는다** — 줄마다 물으면 시료 20개짜리 화면에 쿼리가 20개 붙는다.
    people = services.registrant_names(rows, db)
    tallies = _run_tallies(
        db, group_by=Specimen.sample_id, ids=[s.id for s in rows], join_specimen=True
    )
    return [
        _sample_out(
            s,
            specimen_count=counts.get(s.id, 0),
            workspace_name=names.get(s.workspace_id),
            registered_by=people.get(s.registered_by_id),
            runs=tallies.get(s.id, (0, 0, 0)),
        )
        for s in rows
    ]


def _make_sample(
    db: Session,
    user: User,
    material: Material,
    payload: SampleCreateRequest,
    *,
    workspace: Workspace,
) -> Sample:
    """시료 하나. **커밋은 부르는 쪽이 한다** — `_make_material` 과 같은 이유다."""
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
        density_si=services.to_si(
            payload.density, payload.density_unit, field="밀도", dimension="density"
        ),
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
    db.flush()
    return sample


@router.post("/{material_id}/samples", response_model=SampleOut, status_code=201)
def create_sample(
    material_id: uuid.UUID,
    payload: SampleCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SampleOut:
    services.get_material(db, user, material_id)  # 볼 권한이 있는가
    workspace = services.resolve_workspace(db, user, payload.workspace_slug)
    # **둘이 같은 순간에 만들면 같은 번호를 읽는다**(실측 2026-08-28). 번호는
    # 사람이 고른 값이 아니므로 다시 받으면 그만이다 — 되돌린 세션에서 재료를
    # 다시 읽어야 하므로 그것까지 안에서 한다.
    sample = contention.with_retry(
        db,
        lambda: _make_sample(
            db,
            user,
            services.get_material(db, user, material_id),
            payload,
            workspace=workspace,
        ),
        code="MNX-MATERIALS-0032",
        message="같은 순간에 여러 사람이 시료를 만들고 있습니다. 다시 시도해 주세요.",
    )
    db.commit()
    return _sample_out(
        sample,
        specimen_count=0,
        workspace_name=workspace.name,
        registered_by=services.registrant_names([sample], db).get(sample.registered_by_id),
    )


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
        registered_by=services.registrant_names([sample], db).get(sample.registered_by_id),
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
        sample.density_si = services.to_si(value, unit, field="밀도", dimension="density")
        sample.input_units = {**sample.input_units, "density": unit}

    db.commit()
    names = services.workspace_names(db, [sample.workspace_id])
    return _sample_out(
        sample,
        specimen_count=services.specimen_counts(db, [sample.id]).get(sample.id, 0),
        workspace_name=names.get(sample.workspace_id),
        registered_by=services.registrant_names([sample], db).get(sample.registered_by_id),
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
    people = services.registrant_names(rows, db)
    return [
        _specimen_out(
            item,
            runs=tallies.get(item.id, (0, 0, 0)),
            sizes=sizes.get(item.id),
            registered_by=people.get(item.registered_by_id),
        )
        for item in rows
    ]


def _make_specimen(
    db: Session, user: User, sample: Sample, payload: SpecimenCreateRequest
) -> Specimen:
    """시편 하나. 같은 방향·번호가 이미 있으면 `Conflict` 로 바꿔 올린다 —
    `IntegrityError` 를 그대로 흘리면 화면은 "서버 오류" 만 본다."""
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
        thickness_m=services.to_si(
            payload.thickness, payload.length_unit, field="두께", dimension="length"
        ),
        width_m=services.to_si(
            payload.width, payload.length_unit, field="폭", dimension="length"
        ),
        gauge_length_m=services.to_si(
            payload.gauge_length,
            payload.length_unit,
            field="게이지 길이",
            dimension="length",
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
        db.flush()
    except IntegrityError as exc:
        raise Conflict(
            "MNX-MATERIALS-0013",
            f"{orientation} 방향 {seq_no}번 시편이 이미 있습니다.",
        ) from exc
    return specimen


@samples_router.post("/{sample_id}/specimens", response_model=SpecimenOut, status_code=201)
def create_specimen(
    sample_id: uuid.UUID,
    payload: SpecimenCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenOut:
    sample = _get_sample(db, user, sample_id)
    try:
        specimen = _make_specimen(db, user, sample, payload)
    except AppError:
        # 플러시가 깨진 세션을 그대로 두면 다음 요청이 엉뚱한 데서 터진다.
        db.rollback()
        raise
    db.commit()
    return _specimen_out(
        specimen,
        registered_by=services.registrant_names([specimen], db).get(specimen.registered_by_id),
    )


def _get_specimen(db: Session, user: User, specimen_id: uuid.UUID) -> Specimen:
    specimen = db.scalar(
        select(Specimen).where(Specimen.id == specimen_id, Specimen.deleted_at.is_(None))
    )
    if specimen is None:
        raise NotFound("MNX-MATERIALS-0003", "시편을 찾을 수 없습니다.")
    _get_sample(db, user, specimen.sample_id)  # 가시 범위 확인
    return specimen


# --- 시편 평면 목록 ------------------------------------------------------------
#
# **재료를 거치지 않고 시편을 찾는다.** 지금까지 시편은 중첩 경로로만 닿았다
# (`/materials/{id}/samples` → `/samples/{id}/specimens`) — 재료를 먼저 골라야
# 시편이 보였다. 그래서 「ASTM E8/E8M 박판형 시편 전부」 처럼 **시편을 가로지르는**
# 물음에 답할 자리가 없었다. 규격은 시편에 붙는데(ADR 0010) 시편을 가로질러 보는
# 화면이 없으면 규격으로는 아무것도 못 찾는다.
#
# 물성 카드가 같은 이유로 `/cards` 를 얻었다 — "그 카드가 어느 재료였더라" 에
# 답할 데가 없었다.
#
# **고정 경로는 `/{specimen_id}` 보다 위에 둔다.** 아래 두면 FastAPI 가 빈 경로를
# 시편 id 로 읽는다.


#: 시편 평면 목록에서 정렬할 수 있는 열. **join 한 표의 열도 고를 수 있다** —
#: 표에 재료·로트가 보이므로 그것으로 정렬하는 것이 자연스럽다.
SPECIMEN_SORTS = {
    "created_at": Specimen.created_at,
    "material_name": Material.record_name,
    "lot_no": Sample.lot_no,
    "record_name": Specimen.record_name,
    "orientation": Specimen.orientation,
    "standard": Specimen.standard,
}

#: 시편에서 글자로 뒤지는 칸. 재료의 `_SEARCH_TEXT` 와 같은 자리다.
_SPECIMEN_TEXT = (Specimen.record_name, Specimen.standard)


@specimens_router.get("", response_model=Page[SpecimenRowOut])
def list_all_specimens(
    q: str | None = Query(default=None, description="시편 이름·규격 부분 일치"),
    material: str | None = Query(default=None, description="재료 이름 부분 일치"),
    lot: str | None = Query(default=None, description="로트 부분 일치"),
    orientation: str | None = Query(default=None, description="방향. 정확히 맞아야 한다"),
    standard: str | None = Query(default=None, description="시편 규격 부분 일치"),
    sort: str | None = Query(default=None, description="정렬할 열. 기본은 등록 일시"),
    desc: bool = Query(default=True, description="내림차순. 기본은 최근 등록순"),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[SpecimenRowOut]:
    """시편을 **재료를 거치지 않고** 찾는다.

    ## 걸러지는 범위는 재료와 같다

    시편은 재료를 따라간다 — 전역 재료 밑에는 여러 부서의 시료가 매달리므로,
    시편만 따로 부서로 가두면 재료 화면에서는 보이는 것이 여기서는 안 보인다.
    그래서 `visible_materials` 를 그대로 타고 내려온다.

    ## 방향만 정확히 맞춘다

    나머지는 부분 일치인데 방향은 아니다. `MD`·`TD`·`DD`·`NA` 넷뿐이라 부분
    일치로 두면 `D` 가 셋을 함께 물어 거른 뜻이 사라진다.
    """
    # **명시적 join 이다.** 시편마다 시료·재료를 물으면 N+1 이고, 그건 이 화면이
    # 느려지는 첫 번째 이유가 된다.
    query = (
        select(Specimen, Sample, Material)
        .join(Sample, Specimen.sample_id == Sample.id)
        .join(Material, Sample.material_id == Material.id)
        .where(
            Specimen.deleted_at.is_(None),
            Sample.deleted_at.is_(None),
            Material.id.in_(select(services.visible_materials(db, user).subquery().c.id)),
        )
    )

    for word in (q or "").split():
        query = query.where(or_(*[column.ilike(f"%{word}%") for column in _SPECIMEN_TEXT]))
    if material:
        query = query.where(Material.record_name.ilike(f"%{material}%"))
    if lot:
        query = query.where(Sample.lot_no.ilike(f"%{lot}%"))
    if standard:
        query = query.where(Specimen.standard.ilike(f"%{standard}%"))
    if orientation:
        query = query.where(Specimen.orientation == orientation)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    rows = list(
        db.execute(
            query.order_by(
                *sorting.order_by(
                    SPECIMEN_SORTS,
                    sort=sort,
                    desc=desc,
                    default="created_at",
                    tiebreaker=Specimen.id,
                )
            )
            .limit(size)
            .offset(offset)
        )
    )

    specimens = [row[0] for row in rows]
    # 치수는 **규격별로 한 번에** 읽는다(`sizes_for`). 시편마다 읽으면 N+1 이다.
    sizes = specimen_size.sizes_for(db, specimens)
    tallies = _run_tallies(
        db,
        group_by=TestRun.specimen_id,
        ids=[one.id for one in specimens],
        join_specimen=False,
    )
    people = services.registrant_names(specimens, db)

    return Page(
        items=[
            SpecimenRowOut(
                **_specimen_out(
                    specimen,
                    runs=tallies.get(specimen.id, (0, 0, 0)),
                    sizes=sizes.get(specimen.id),
                    registered_by=people.get(specimen.registered_by_id),
                ).model_dump(),
                material_id=material_row.id,
                material_name=material_row.record_name,
                lot_no=sample_row.lot_no,
                sample_name=sample_row.record_name,
            )
            for specimen, sample_row, material_row in rows
        ],
        total=int(total),
        limit=size,
        offset=offset,
    )


@specimens_router.post("/bulk-update", response_model=SpecimenBulkUpdateOut)
def bulk_update_specimens(
    payload: SpecimenBulkUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenBulkUpdateOut:
    """고른 시편의 **칸 하나**를 같은 값으로 맞춘다.

    ## 왜 이 길이 필요한가

    이관에서 규격이 빈 시편이 무더기로 생겼다(2026-08-28). 규격은 그 시편의
    치수 칸을 정하므로(ADR 0010) 비어 있으면 치수를 받을 자리조차 없는데,
    고칠 길이 **시편을 하나씩 여는 것뿐**이었다. 수백 장이면 그것은 길이 아니다.

    ## 한 건이 막혀도 나머지는 간다

    권한 밖이거나 사라진 시편이 섞여 있어도 전부 되돌리지 않는다 — 그러면 사람은
    어느 것이 문제인지 모른 채 다시 골라야 한다. **안 된 것을 이름으로 돌려준다**
    (지우기·시험 일괄 수정과 같은 규칙).

    ## 방향은 이름과 번호를 바꾼다

    칸 하나를 갈아 끼우는 일이 아니다. `services.change_orientation` 이 옮겨 가는
    방향에서 번호를 새로 받고 시험 이름까지 따라가게 한다 — 한 건 수정이 하는
    것과 **같은 함수**다. 여기서 다시 구현하면 두 길이 갈라진다.
    """
    field = payload.field
    raw = (payload.value or "").strip() or None

    # **방향은 미리 판정한다.** 열 건을 고치다 열한 번째에서 틀렸다고 멈추면
    # 앞의 열 건만 바뀐 상태가 남는다. 값이 하나뿐인 요청이니 손대기 전에 거른다.
    if field == "orientation":
        if raw is None:
            raise AppError(
                "MNX-MATERIALS-0031",
                "방향은 비울 수 없습니다. 시편 이름의 한 칸입니다.",
                status=422,
            )
        raw = raw.upper()
        if raw not in ORIENTATIONS:
            raise AppError(
                "MNX-MATERIALS-0030",
                f"방향은 {', '.join(ORIENTATIONS)} 중 하나여야 합니다.",
                status=422,
            )

    updated = 0
    unchanged = 0
    blocked: list[str] = []
    renamed: list[str] = []

    for specimen_id in payload.specimen_ids:
        try:
            specimen = _get_specimen(db, user, specimen_id)
        except AppError:
            # **이름을 모르면 id 라도 준다.** 조용히 세지 않는 것이 요점이다.
            blocked.append(str(specimen_id))
            continue

        before = getattr(specimen, field)
        if before == raw:
            unchanged += 1
            continue

        if field == "orientation":
            assert raw is not None  # 위에서 걸렀다
            said = services.change_orientation(db, specimen, raw)
            if said:
                renamed.append(said)
            # **건마다 흘려보낸다.** 번호는 `max(seq_no) + 1` 로 받는데, 앞 건이
            # 아직 DB 에 안 갔으면 그 질의가 못 본다 — 셋을 한 번에 옮기면 셋이
            # 같은 번호를 받고 커밋에서 유니크가 터진다(실측 2026-08-28).
            #
            # 한 건 수정에서는 안 났다. 그쪽은 한 번 바꾸고 바로 커밋한다.
            db.flush()
        else:
            # 규격은 기준정보를 거친다(ADR 0010). `usage_count` 도 여기서
            # 옮겨진다 — 옛 값은 하나 줄고 새 값은 하나 는다.
            vocabulary_services.apply_bindings(
                db,
                specimen,
                vocabulary_services.SPECIMEN_BINDINGS,
                {field: raw},
                created_by_id=user.id,
            )
        updated += 1

    db.commit()
    return SpecimenBulkUpdateOut(
        updated=updated, unchanged=unchanged, blocked=blocked, renamed=renamed
    )


@specimens_router.get("/{specimen_id}", response_model=SpecimenOut)
def get_specimen(
    specimen_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenOut:
    one = _get_specimen(db, user, specimen_id)
    return _specimen_out(
        one,
        registered_by=services.registrant_names([one], db).get(one.registered_by_id),
    )


@specimens_router.patch("/{specimen_id}", response_model=SpecimenUpdateOut)
def update_specimen(
    specimen_id: uuid.UUID,
    payload: SpecimenUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpecimenUpdateOut:
    """시편을 고친다.

    **방향을 바꾸면 이름과 번호가 다시 매겨진다.** 그 사실을 `renamed` 로
    돌려준다 — 방향만 골랐는데 번호까지 달라지는 것은 사람이 예상 못 하는
    일이라 조용히 하면 안 된다.
    """
    specimen = _get_specimen(db, user, specimen_id)
    data = payload.model_dump(exclude_unset=True)
    unit = data.get("length_unit") or specimen.input_units.get("length", LENGTH_UNIT)

    for field, column in (
        ("thickness", "thickness_m"),
        ("width", "width_m"),
        ("gauge_length", "gauge_length_m"),
    ):
        if field in data:
            setattr(
                specimen,
                column,
                services.to_si(data[field], unit, field=field, dimension="length"),
            )
    if "note" in data:
        specimen.note = data["note"]

    # **방향은 이름과 번호를 바꾼다.** 칸 하나가 아니라서 따로 다룬다.
    renamed = ""
    if data.get("orientation"):
        want = str(data["orientation"]).upper()
        if want not in ORIENTATIONS:
            raise AppError(
                "MNX-MATERIALS-0030",
                f"방향은 {', '.join(ORIENTATIONS)} 중 하나여야 합니다.",
                status=422,
            )
        renamed = services.change_orientation(db, specimen, want)

    vocabulary_services.apply_bindings(
        db, specimen, vocabulary_services.SPECIMEN_BINDINGS, data, created_by_id=user.id
    )
    specimen.input_units = {**specimen.input_units, "length": unit}

    db.commit()
    return SpecimenUpdateOut(
        specimen=_specimen_out(
            specimen,
            registered_by=services.registrant_names([specimen], db).get(
                specimen.registered_by_id
            ),
        ),
        renamed=renamed or None,
    )


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
