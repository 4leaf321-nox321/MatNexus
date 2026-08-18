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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.materials import services
from app.modules.materials.models import ORIENTATIONS, Material, Sample, Specimen
from app.modules.materials.schemas import (
    DENSITY_UNIT,
    LENGTH_UNIT,
    ClassificationOut,
    MaterialCreateRequest,
    MaterialOut,
    MaterialUpdateRequest,
    NamePreviewOut,
    NamePreviewRequest,
    PropertySourcesOut,
    SampleCreateRequest,
    SampleOut,
    SampleUpdateRequest,
    SpecimenCreateRequest,
    SpecimenOut,
    SpecimenUpdateRequest,
    ValueSourceOut,
)
from app.modules.tests.models import TestRun
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.pagination import Page, clamp_limit
from matcore import naming

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
        density=services.from_si(material.density_si, density_unit),
        density_unit=density_unit,
        poisson_ratio=material.poisson_ratio,
        note=material.note,
        legacy_id=material.legacy_id,
        sample_count=sample_count,
        created_at=material.created_at,
        updated_at=material.updated_at,
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
        applied_product=sample.applied_product,
        applied_part=sample.applied_part,
        production_date=sample.production_date,
        density=services.from_si(sample.density_si, unit),
        density_unit=unit,
        note=sample.note,
        specimen_count=specimen_count,
        created_at=sample.created_at,
    )


def _specimen_out(specimen: Specimen, *, runs: RunTally = (0, 0, 0)) -> SpecimenOut:
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
        thickness=services.from_si(specimen.thickness_m, unit),
        width=services.from_si(specimen.width_m, unit),
        gauge_length=services.from_si(specimen.gauge_length_m, unit),
        length_unit=unit,
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
_SEARCH_COLUMNS = (
    Material.record_name,
    Material.alias,
    Material.family,
    Material.category,
    Material.grade,
    Material.details,
)


def _search_terms(q: str | None) -> list[Any]:
    """검색어를 낱말로 나눠 **낱말마다 조건 하나**로 만든다(AND).

    이름은 `SECC_MDOI_1.0` 인데 사람은 `SECC 1.0` 이라고 친다. 구분자가 밑줄이라
    통째로 비교하면 안 맞는다. 낱말마다 나누면 순서도 상관없어진다 — 사람이 이름
    규칙의 순서를 외우고 있지 않다.

    AND 인 이유: OR 로 하면 낱말이 늘수록 결과가 **늘어난다.** 좁히려고 더 쳤는데
    넓어지면 검색이 아니다.
    """
    if not q or not q.strip():
        return []
    return [
        or_(*(column.ilike(f"%{word}%") for column in _SEARCH_COLUMNS)) for word in q.split()
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
    rows = db.execute(
        select(visible.c.family, visible.c.category, func.count())
        .group_by(visible.c.family, visible.c.category)
        .order_by(visible.c.family, visible.c.category)
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
    for condition in _search_terms(q):
        query = query.where(condition)
    if family:
        query = query.where(Material.family == family)
    if category:
        query = query.where(Material.category == category)
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
        family=payload.family,
        category=payload.category,
        grade=payload.grade,
        details=payload.details,
        spec_thickness_m=thickness_m,
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
    for field in ("family", "category", "grade", "details", "alias", "note", "poisson_ratio"):
        if field in data:
            setattr(material, field, data[field])

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
        manufacturer=payload.manufacturer,
        distributor=payload.distributor,
        primary_vendor=payload.primary_vendor,
        sales_type=payload.sales_type,
        applied_product=payload.applied_product,
        applied_part=payload.applied_part,
        production_date=payload.production_date,
        density_si=services.to_si(payload.density, payload.density_unit, field="밀도"),
        input_units={"density": payload.density_unit},
        note=payload.note,
        registered_by_id=user.id,
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
        "manufacturer",
        "distributor",
        "primary_vendor",
        "sales_type",
        "applied_product",
        "applied_part",
        "production_date",
        "note",
    ):
        if field in data:
            setattr(sample, field, data[field])

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
    return [_specimen_out(item, runs=tallies.get(item.id, (0, 0, 0))) for item in rows]


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
    specimen.input_units = {**specimen.input_units, "length": unit}

    db.commit()
    return _specimen_out(specimen)


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
    db.commit()
    return Response(status_code=204)
