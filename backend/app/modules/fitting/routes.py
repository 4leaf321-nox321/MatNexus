"""적합과 물성 카드 — **해석에 들어가는 값을 만든다.**

입력은 통계가 낸 대표 곡선이다. 시편 하나가 아니라 여러 개의 평균이어야 하는
이유는 간단하다 — 시편 하나의 물성은 그 시편의 물성이다.

**어느 식이 맞는지 고르지 않는다.** 여러 식을 같은 데이터에 맞춰 나란히 주고
상대 RMSE 로 정렬만 한다. 적합 구간에서 비슷한 두 식이 그 밖에서 갈리므로(Swift 는
계속 올라가고 Voce 는 포화한다), 어디까지 쓸 것인지가 선택을 바꾸고 그것은
해석하는 사람이 안다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.fitting.schemas import (
    ExportFormatOut,
    FamilyOut,
    FitOut,
    FitPreviewOut,
    FitPreviewRequest,
    FittedParameterOut,
    PropertyCardOut,
    PropertyCardSaveRequest,
)
from app.modules.materials.models import Material
from app.modules.statistics import services as statistics_services
from app.modules.tests.models import TestType
from app.modules.workspaces.models import Workspace
from app.shared import permissions
from app.shared.auth import current_user
from app.shared.errors import AppError, Forbidden, NotFound
from matcore import export, fitting, statistics

router = APIRouter(prefix="/fitting", tags=["fitting"])

#: 적합 곡선을 그릴 점 수. 데이터와 겹쳐 보는 용도라 이 정도면 충분하다.
CURVE_POINTS = 120

#: 경화식 적합에 쓰는 축. **공칭이 아니라 진응력·진소성변형률이다** — 솔버가
#: 받는 것이 이쪽이고, 공칭으로 맞춘 파라미터를 넣으면 조용히 틀린 해석이 된다.
FIT_X = "strain_true_plastic"
FIT_Y = "stress_true"


@router.get("/families", response_model=list[FamilyOut])
def list_families(user: User = Depends(current_user)) -> list[FamilyOut]:
    """등록된 경화식. **화면이 이 응답만으로 목록을 그린다.**"""
    return [
        FamilyOut(
            key=family.key,
            label=family.label,
            describe=family.describe,
            parameter_names=list(family.parameter_names),
            parameter_units=list(family.parameter_units),
        )
        for family in fitting.FAMILIES.values()
    ]


def _representative(
    db: Session, user: User, material_id: uuid.UUID, test_type_key: str, orientation: str
) -> tuple[statistics_services.Group, np.ndarray, np.ndarray, list[str]]:
    """대표 곡선에서 (소성변형률, 진응력) 을 꺼낸다.

    **시편 하나가 아니라 여러 개의 평균이다.** 하나로 적합하면 그 시편의 물성을
    재료의 물성이라고 부르는 셈이다.
    """
    _, groups = statistics_services.groups_for_material(db, user, material_id)
    group = next(
        (
            item
            for item in groups
            if item.test_type.key == test_type_key and item.orientation == orientation
        ),
        None,
    )
    if group is None:
        raise NotFound("MNX-FITTING-0001", "그 묶음을 찾을 수 없습니다.")
    if len(group.members) < statistics.MIN_SAMPLES:
        raise AppError(
            "MNX-FITTING-0002",
            f"채택된 시험이 {len(group.members)}건입니다. "
            f"{statistics.MIN_SAMPLES}건 이상이어야 대표 곡선이 나옵니다 — "
            f"처리한 뒤 결과 탭에서 채택하세요.",
            status=422,
        )

    curve, notes = statistics_services.curve_table(db, group, x=FIT_X, y=FIT_Y)
    if curve is None:
        raise AppError(
            "MNX-FITTING-0003",
            "대표 곡선을 만들 수 없습니다. "
            + " ".join(notes)
            + " 레시피에 '진응력·진소성변형률' 단계가 들어 있는지도 확인하세요.",
            status=422,
        )
    mean = np.asarray(curve["mean"], dtype=np.float64)
    return group, mean[:, 0], mean[:, 1], notes


def _fit_out(result: fitting.FitResult) -> FitOut:
    # 적합된 식을 그려 함께 준다. 숫자만 보고는 맞는지 알 수 없다 — 데이터와
    # 겹쳐 봐야 어디가 어긋났는지 보인다.
    grid = np.linspace(result.strain_min, result.strain_max, CURVE_POINTS)
    drawn = result.evaluate(grid)
    return FitOut(
        family=result.family,
        label=result.label,
        parameters=[
            FittedParameterOut(
                name=item.name,
                value=item.value,
                si_unit=item.si_unit,
                lower=item.lower,
                upper=item.upper,
                initial=item.initial,
            )
            for item in result.parameters
        ],
        rmse=result.rmse,
        relative_rmse=result.relative_rmse,
        r_squared=result.r_squared,
        max_residual=result.max_residual,
        point_count=result.point_count,
        strain_min=result.strain_min,
        strain_max=result.strain_max,
        notes=list(result.notes),
        curve=[(float(x), float(y)) for x, y in zip(grid, drawn, strict=True)],
    )


@router.post("/preview", response_model=FitPreviewOut)
def preview(
    payload: FitPreviewRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FitPreviewOut:
    """**저장하지 않고** 여러 식을 견줘 본다.

    상대 RMSE 순으로 주되 **어느 것이 맞는지는 고르지 않는다.** 적합 구간에서
    비슷한 두 식이 그 밖에서 갈리고, 어디까지 쓸 것인지는 해석하는 사람이 안다.
    """
    group, strain, stress, notes = _representative(
        db, user, payload.material_id, payload.test_type_key, payload.orientation
    )
    results = fitting.compare(strain, stress, families=tuple(payload.families))
    if not results:
        raise AppError(
            "MNX-FITTING-0004",
            f"어느 식도 맞추지 못했습니다. 대표 곡선이 {len(strain)}점인데 "
            f"적합에는 {fitting.MIN_POINTS}점 이상이 필요합니다 — "
            f"레시피의 재샘플 점 수를 늘려 보세요.",
            status=422,
        )
    return FitPreviewOut(
        source_points=[(float(x), float(y)) for x, y in zip(strain, stress, strict=True)],
        sample_count=len(group.members),
        fits=[_fit_out(item) for item in results],
        notes=notes,
    )


def _card_out(db: Session, item: PropertyCard) -> PropertyCardOut:
    material = db.get(Material, item.material_id)
    test_type = db.get(TestType, item.test_type_id)
    return PropertyCardOut(
        id=item.id,
        material_id=item.material_id,
        material_name=material.record_name if material else "?",
        test_type_key=test_type.key if test_type else "?",
        orientation=item.orientation,
        label=item.label,
        status=item.status,
        source=item.source,
        elastic=item.elastic,
        hardening=item.hardening,
        table=item.table,
        point_count=item.point_count,
        note=item.note,
        published_at=item.published_at,
        created_at=item.created_at,
    )


@router.post("/cards", response_model=PropertyCardOut, status_code=201)
def create_card(
    payload: PropertyCardSaveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyCardOut:
    """물성 카드를 만든다. **초안으로 시작한다**(D8).

    **표는 언제나 저장한다.** 많은 솔버가 식보다 표를 그대로 받고, 식이 안 맞는
    재료에서는 표가 더 정확하다. 식은 골랐을 때만 함께 넣는다.
    """
    group, strain, stress, notes = _representative(
        db, user, payload.material_id, payload.test_type_key, payload.orientation
    )

    hardening: dict[str, Any] = {}
    if payload.family:
        try:
            result = fitting.fit(payload.family, strain, stress)
        except fitting.FittingError as exc:
            raise AppError("MNX-FITTING-0004", str(exc), status=422) from exc
        hardening = {
            "family": result.family,
            "label": result.label,
            # **적합도를 함께 저장한다.** 파라미터만 남기면 그 값이 데이터와 얼마나
            # 맞는지 다시 알 수 없고, 그러면 카드를 믿을 근거가 사라진다.
            "parameters": [
                {
                    "name": item.name,
                    "value": item.value,
                    "si_unit": item.si_unit,
                    "lower": item.lower,
                    "upper": item.upper,
                    "initial": item.initial,
                }
                for item in result.parameters
            ],
            "rmse": result.rmse,
            "relative_rmse": result.relative_rmse,
            "r_squared": result.r_squared,
            "max_residual": result.max_residual,
            "strain_min": result.strain_min,
            "strain_max": result.strain_max,
            "notes": list(result.notes),
        }

    modulus = next(
        (
            row["mean"]
            for row in statistics_services.scalar_table(
                group, threshold=statistics.DEFAULT_OUTLIER_THRESHOLD
            )
            if row["key"] == "youngs_modulus"
        ),
        None,
    )
    item = PropertyCard(
        material_id=group.material.id,
        test_type_id=group.test_type.id,
        orientation=group.orientation,
        label=payload.label,
        status="draft",
        source={
            "sample_count": len(group.members),
            "test_run_ids": [str(member.run.id) for member in group.members],
            "record_names": [member.run.record_name for member in group.members],
            "strain_min": float(strain[0]),
            "strain_max": float(strain[-1]),
            "notes": notes,
        },
        elastic={
            # **없는 값은 넣지 않는다.** 0 이나 0.3 으로 채우면 그것이 측정값인지
            # 기본값인지 나중에 알 수 없다.
            **({"youngs_modulus": modulus} if modulus is not None else {}),
            **({"poisson_ratio": payload.poisson_ratio} if payload.poisson_ratio else {}),
            **({"density": payload.density} if payload.density else {}),
        },
        hardening=hardening,
        table=[
            {"plastic_strain": float(x), "true_stress": float(y)}
            for x, y in zip(strain, stress, strict=True)
        ],
        point_count=len(strain),
        note=payload.note,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _card_out(db, item)


@router.get("/cards", response_model=list[PropertyCardOut])
def list_cards(
    material_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PropertyCardOut]:
    query = select(PropertyCard).order_by(PropertyCard.created_at.desc())
    if material_id:
        statistics_services.groups_for_material(db, user, material_id)  # 가시성 판정
        query = query.where(PropertyCard.material_id == material_id)
    else:
        # 재료를 안 주면 볼 수 있는 재료의 카드만 준다. 안 그러면 남의 부서
        # 재료의 물성이 목록에 섞인다.
        query = query.where(
            PropertyCard.material_id.in_(permissions.visible_material_ids(db, user))
        )
    return [_card_out(db, item) for item in db.scalars(query)]


@router.get("/cards/{card_id}", response_model=PropertyCardOut)
def get_card(
    card_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyCardOut:
    item = _visible_card(db, user, card_id)
    return _card_out(db, item)


def _visible_card(db: Session, user: User, card_id: uuid.UUID) -> PropertyCard:
    item = db.get(PropertyCard, card_id)
    if item is None:
        raise NotFound("MNX-FITTING-0005", "물성 카드를 찾을 수 없습니다.")
    statistics_services.groups_for_material(db, user, item.material_id)  # 가시성 판정
    return item


@router.get("/formats", response_model=list[ExportFormatOut])
def list_formats(user: User = Depends(current_user)) -> list[ExportFormatOut]:
    """내보낼 수 있는 솔버. **화면이 이 응답만으로 목록을 그린다.**"""
    return [
        ExportFormatOut(
            key=item.key,
            label=item.label,
            extension=item.extension,
            describe=item.describe,
            requires=[export.VALUE_LABELS[name] for name in item.requires],
        )
        for item in export.FORMATS.values()
    ]


@router.get("/cards/{card_id}/export")
def export_card(
    card_id: uuid.UUID,
    format: str = Query(default="json"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """솔버 카드를 텍스트로 만든다.

    **초안도 내보낼 수 있다.** 확정 전에 덱에 넣어 한 번 돌려 보는 것이 검토의
    실체다 — 돌려 보지 않고 확정하라고 하면 확정이 형식이 된다. 대신 초안이면
    카드 안에 그렇게 적어 둔다.
    """
    item = _visible_card(db, user, card_id)
    material = db.get(Material, item.material_id)
    test_type = db.get(TestType, item.test_type_id)

    # 솔버 덱의 이름은 재료 이름에서 만든다. 카드 이름은 한국어일 때가 많고,
    # 그러면 이름이 통째로 사라진다.
    base = f"{material.record_name if material else item.label}_{item.orientation}"
    hardening = item.hardening or {}
    provenance = [
        f"재료 {material.record_name if material else '?'} · "
        f"{test_type.key if test_type else '?'} · {item.orientation}",
        f"시편 {item.source.get('sample_count', '?')}개의 대표 곡선에서 만들었습니다.",
        f"카드 {item.id} ({STATUS_NOTES.get(item.status, item.status)})",
    ]
    if hardening.get("label"):
        # **경화식은 덱에 안 들어간다.** 표로 나간다. 그래도 어떤 식으로 봤는지는
        # 적어 둔다 — 이 표가 어디까지 검증된 것인지가 거기에 있다.
        provenance.append(
            f"경화식 참고: {hardening['label']} · 상대 RMSE "
            f"{float(hardening.get('relative_rmse', 0.0)) * 100:.3g}% · "
            f"적합 구간 소성변형률 {float(hardening.get('strain_min', 0.0)):.5g}~"
            f"{float(hardening.get('strain_max', 0.0)):.5g} (그 밖은 검증되지 않았습니다)"
        )

    card = export.Card(
        name=export.sanitize_name(base),
        solver_id=export.solver_id_from(str(item.id)),
        youngs_modulus=item.elastic.get("youngs_modulus"),
        poisson_ratio=item.elastic.get("poisson_ratio"),
        density=item.elastic.get("density"),
        points=tuple(
            (float(row["plastic_strain"]), float(row["true_stress"])) for row in item.table
        ),
        provenance=tuple(provenance),
    )
    try:
        rendered = export.render(format, card)
    except export.ExportError as exc:
        raise AppError("MNX-FITTING-0009", str(exc), status=422) from exc

    target = export.FORMATS[format]
    return Response(
        content=rendered.text,
        media_type=target.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{card.name}.{target.extension}"'
        },
    )


#: 카드 상태를 덱 주석에 적는 말. 초안인 덱이 돌아다닐 수 있다.
STATUS_NOTES = {
    "draft": "초안 — 아직 확정되지 않았습니다",
    "published": "확정",
    "deprecated": "내려진 카드 — 쓰지 마세요",
}


@router.post("/cards/{card_id}/publish", response_model=PropertyCardOut)
def publish(
    card_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyCardOut:
    """초안을 확정한다. **부서 관리자만**(D12).

    올린 뒤에는 값을 바꿀 수 없다 — 그 값으로 해석이 돌았을 수 있다. 고치려면
    내리고(`deprecated`) 새 카드를 만든다.

    **리뷰 큐는 없다**(D8). 상태만 두고, 절차는 운영 규칙이 보인 뒤에 만든다 —
    절차를 먼저 만들면 그 절차가 일을 정의해 버린다.
    """
    item = _visible_card(db, user, card_id)
    _require_publisher(db, user, item)

    if item.status == "published":
        raise AppError("MNX-FITTING-0007", "이미 확정된 카드입니다.", status=409)
    item.status = "published"
    item.published_by_id = user.id
    item.published_at = datetime.now(UTC)
    db.commit()
    db.refresh(item)
    return _card_out(db, item)


def _require_publisher(db: Session, user: User, item: PropertyCard) -> None:
    """**확정은 부서 관리자만**(D12). 전역 재료는 시스템 관리자만.

    카드를 만드는 것은 누구나 할 수 있다 — 만드는 것은 초안이고, 초안은 아직
    아무 해석에도 안 들어간다. 확정만 막는다.
    """
    if user.is_system_admin:
        return
    material = db.get(Material, item.material_id)
    if material is None:
        raise NotFound("MNX-MATERIALS-0001", "재료를 찾을 수 없습니다.")
    if material.owner_workspace_id is None:
        raise Forbidden(
            "MNX-FITTING-0006",
            "전역 재료의 물성은 시스템 관리자만 확정할 수 있습니다.",
        )
    workspace = db.get(Workspace, material.owner_workspace_id)
    if workspace is None:
        raise NotFound("MNX-FITTING-0006", "재료의 소속 부서를 찾을 수 없습니다.")
    permissions.require_manager(db, workspace=workspace, user=user)


@router.post("/cards/{card_id}/deprecate", response_model=PropertyCardOut)
def deprecate(
    card_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyCardOut:
    """카드를 내린다. **지우지 않는다** — 이 값으로 해석이 돌았을 수 있다."""
    item = _visible_card(db, user, card_id)
    if item.status == "published":
        # 올린 사람과 같은 권한으로만 내린다. 확정된 값을 아무나 무를 수 있으면
        # 확정에 권한을 둔 뜻이 없다.
        _require_publisher(db, user, item)
    item.status = "deprecated"
    db.commit()
    db.refresh(item)
    return _card_out(db, item)


@router.delete("/cards/{card_id}", status_code=204)
def remove_card(
    card_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """**초안만 지울 수 있다.** 확정된 적이 있는 카드는 내리기만 한다."""
    item = _visible_card(db, user, card_id)
    if item.status != "draft":
        raise AppError(
            "MNX-FITTING-0008",
            "확정된 카드는 지울 수 없습니다. 내리기를 쓰세요 — "
            "이 값으로 해석이 돌았을 수 있습니다.",
            status=409,
        )
    db.delete(item)
    db.commit()
    return Response(status_code=204)
