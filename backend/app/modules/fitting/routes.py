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
from dataclasses import dataclass
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
    BlockSpecOut,
    CardValueOut,
    ExportFormatOut,
    FamilyOut,
    FitOut,
    FitPreviewOut,
    FitPreviewRequest,
    FittedParameterOut,
    InheritedValueOut,
    PropertyCardOut,
    PropertyCardSaveRequest,
    PropertyCardUpdateRequest,
    ViscoelasticCardSaveRequest,
)
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.statistics import services as statistics_services
from app.modules.tests.models import TestType
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.modules.workspaces.models import Workspace
from app.shared import audit, permissions
from app.shared.auth import current_user
from app.shared.errors import AppError, Forbidden, NotFound
from matcore import cards, export, fitting, prony, runtime, statistics
from matcore.fitting import hyperelastic
from matcore.registry import Produced

router = APIRouter(prefix="/fitting", tags=["fitting"])

#: 적합 곡선을 그릴 점 수. 데이터와 겹쳐 보는 용도라 이 정도면 충분하다.
CURVE_POINTS = 120

#: 경화식 적합에 쓰는 축. **공칭이 아니라 진응력·진소성변형률이다** — 솔버가
#: 받는 것이 이쪽이고, 공칭으로 맞춘 파라미터를 넣으면 조용히 틀린 해석이 된다.
FIT_X = "strain_true_plastic"
FIT_Y = "stress_true"


@router.get("/families", response_model=list[FamilyOut])
def list_families(
    material_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[FamilyOut]:
    """등록된 적합식. **화면이 이 응답만으로 목록을 그린다.**

    재료를 주면 그 재료군에서 뜻이 있는 것만 낸다. **금속 경화식과 고무 초탄성을
    한 목록에 섞어 RMSE 로 줄 세우면 안 된다** — 같은 물음의 답이 아니다.
    """
    fitting.load_builtin()
    material = db.get(Material, material_id) if material_id else None
    return [
        FamilyOut(
            key=family.key,
            label=family.label,
            describe=family.describe,
            parameter_names=list(family.parameter_names),
            parameter_units=list(family.parameter_units),
            block=family.block,
            x_label=family.x_label,
            y_label=family.y_label,
        )
        for family in fitting.families_for(material.family if material else None)
    ]


def _produced(item: Produced) -> CardValueOut:
    return CardValueOut(key=item.key, label=item.label, si_unit=item.si_unit, help=item.help)


@router.get("/blocks", response_model=list[BlockSpecOut])
def list_blocks(user: User = Depends(current_user)) -> list[BlockSpecOut]:
    """등록된 물성 블록. **화면이 이 응답만으로 카드를 그린다.**

    화면이 `elastic`·`viscoelastic` 같은 이름을 하나도 모른다 — 그것이 새 물성을
    더하는 값을 마이그레이션 0·화면 0 으로 만드는 자리다(D7).
    """
    cards.load_builtin()
    # **어느 블록이 덱에 실리는지는 렌더러들이 안다.** 전에는 블록이 스스로
    # 선언했는데(`to_card is not None`), 실제로 쓰이는지와 어긋날 수 있었다 —
    # 지금은 등록된 솔버들이 실제로 요구하는 것에서 계산한다.
    in_decks = export.blocks_in_decks()
    return [
        BlockSpecOut(
            key=spec.key,
            label=spec.label,
            help=spec.help,
            produces=[_produced(one) for one in spec.produces],
            rows=[_produced(one) for one in spec.rows],
            in_deck=spec.key in in_decks,
        )
        for spec in cards.list_blocks()
    ]


#: 출처 코드 → 덱에 적을 말. **7850 이 실측인지 관례값인지 덱만 봐서는 모른다.**
#: 솔버 결과를 놓고 "이 물성 어디서 났나" 를 묻는 자리에서, 값만 있고 출처가
#: 없으면 되짚을 데가 없다.
SOURCE_NOTES = {
    "measured": "이 시험들에서 잰 값",
    "sample": "시료에서 잰 값",
    "material": "재료에 적힌 공칭값",
    "manual": "사람이 직접 넣은 값",
}


@dataclass(frozen=True)
class Inherited:
    """물려받은 값 하나와 **어디서 왔는지.**

    카드는 불변이라 값을 참조로 두면 안 된다 — 재료의 밀도를 고치는 순간 이미
    확정한 카드가 조용히 달라진다. 그래서 값은 복사한다. 대신 출처를 함께
    복사한다: 덱만 받은 사람이 7850 을 보고 그것이 실측인지 관례값인지 물을 때,
    답할 데가 있어야 한다.
    """

    value: float | None
    source: str
    """`sample` | `material` | `manual` | `measured` | `conflict` | `missing`."""
    detail: str | None = None
    """사람이 읽는 한 줄. 갈렸으면 무엇과 무엇이 갈렸는지 여기 적는다."""


def _samples_of(db: Session, group: statistics_services.Group) -> list[Sample]:
    ids = {member.specimen.sample_id for member in group.members}
    return list(db.scalars(select(Sample).where(Sample.id.in_(ids)))) if ids else []


def _inherit_density(
    material: Material, samples: list[Sample], override: float | None
) -> Inherited:
    """시료 실측 → 재료 공칭 순. **로트마다 다를 수 있는 값이다.**

    강판은 로트가 달라도 7850 이지만 복합재·발포재·소결재는 실제로 다르다.
    그래서 실측이 있으면 그것을 먼저 쓴다.
    """
    if override is not None:
        return Inherited(override, "manual", "직접 입력한 값입니다.")

    measured = {s.density_si for s in samples if s.density_si is not None}
    if len(measured) == 1:
        value = next(iter(measured))
        return Inherited(value, "sample", f"시료에서 잰 값입니다 ({value:.4g} kg/m³).")
    if len(measured) > 1:
        # **말없이 하나 고르지 않는다.** 어느 로트의 값을 썼는지 모르는 카드는
        # 근거가 없는 것과 같다.
        joined = ", ".join(f"{v:.4g}" for v in sorted(measured))
        return Inherited(
            None,
            "conflict",
            f"시료마다 밀도가 다릅니다({joined} kg/m³) — 쓸 값을 직접 넣으세요.",
        )
    if material.density_si is not None:
        return Inherited(
            material.density_si,
            "material",
            f"재료의 공칭값입니다 ({material.density_si:.4g} kg/m³).",
        )
    return Inherited(None, "missing", "재료에도 시료에도 밀도가 없습니다.")


def _inherit_poisson(material: Material, override: float | None) -> Inherited:
    """**재료에서만 온다.** 로트마다 달라지는 값이 아니다."""
    if override is not None:
        return Inherited(override, "manual", "직접 입력한 값입니다.")
    if material.poisson_ratio is not None:
        return Inherited(material.poisson_ratio, "material", "재료에 적힌 값입니다.")
    return Inherited(
        None,
        "missing",
        "재료에 푸아송비가 없습니다 — 인장시험은 이 값을 주지 않습니다.",
    )


def _representative(
    db: Session,
    user: User,
    material_id: uuid.UUID,
    test_type_key: str,
    orientation: str,
    family: fitting.Family | None = None,
) -> tuple[statistics_services.Group, np.ndarray, np.ndarray, list[str]]:
    """대표 곡선에서 **그 식이 쓰는 축**을 꺼낸다.

    금속 경화식은 진응력·진소성변형률, 고무 초탄성은 공칭이다 — 축은 식이 안다
    (`Family.x_column`). 전에는 이 함수가 금속의 축을 상수로 들고 있었다.

    **여러 개의 평균이 낫다.** 하나로 적합하면 그 시편의 물성을 재료의 물성이라고
    부르는 셈이고, 그 시편이 하필 이상치였는지 알 방법이 없다.

    그렇다고 **막지는 않는다.** 한 번 재고 해석부터 돌려 보는 것은 정상 작업이고,
    막으면 사람은 시스템 밖에서 계산해 카드 없이 덱을 만든다 — 그러면 근거가
    아무 데도 안 남는다. 대신 표본 수를 카드에 박고(`source.sample_count`),
    1건이면 그 사실을 근거에 문장으로 남긴다.
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
    if not group.members:
        raise AppError(
            "MNX-FITTING-0002",
            "채택된 시험이 없습니다. 시험 상세의 '처리' 탭에서 돌려 보고 저장한 뒤 "
            "'채택' 을 누르면 그 곡선이 여기로 들어옵니다.",
            status=422,
        )

    x_column = family.x_column if family else FIT_X
    y_column = family.y_column if family else FIT_Y
    curve, notes = statistics_services.curve_table(db, group, x=x_column, y=y_column)
    if curve is None:
        raise AppError(
            "MNX-FITTING-0003",
            "대표 곡선을 만들 수 없습니다. "
            + " ".join(notes)
            + f" 레시피가 '{x_column}'·'{y_column}' 열을 만드는지 확인하세요.",
            status=422,
        )
    mean = np.asarray(curve["mean"], dtype=np.float64)
    # **적합 전에 구간을 다듬는다.** 무엇을 다듬는지는 식이 안다 — 금속은 탄성
    # 구간의 자국을 걷고(안 걷으면 x 가 전부 0 인 점 수십 개가 적합을 지배해서
    # 식이 맞는데도 R² 가 0.4 로 나온다), 고무는 식이 성립하지 않는 점을 걷는다.
    prepare = (family.prepare if family else None) or fitting.plastic_branch
    strain, stress, trimmed = prepare(mean[:, 0], mean[:, 1])
    single = (
        [
            "시편 1개의 곡선으로 적합했습니다 — 재료의 대푯값이 아니라 그 시편의 "
            "값입니다. 흩어짐을 모르므로 이 파라미터가 얼마나 재현되는지도 알 수 "
            "없습니다."
        ]
        if len(group.members) == 1
        else []
    )
    return group, strain, stress, [*notes, *single, *trimmed]


def _fit_out(result: fitting.FitResult) -> FitOut:
    # 적합된 식을 그려 함께 준다. 숫자만 보고는 맞는지 알 수 없다 — 데이터와
    # 겹쳐 봐야 어디가 어긋났는지 보인다.
    grid = np.linspace(result.strain_min, result.strain_max, CURVE_POINTS)
    drawn = result.evaluate(grid)
    return FitOut(
        x_label=fitting.FAMILIES[result.family].x_label,
        y_label=fitting.FAMILIES[result.family].y_label,
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
    fitting.load_builtin()
    material = db.get(Material, payload.material_id)
    chosen = [
        item
        for item in fitting.families_for(material.family if material else None)
        if not payload.families or item.key in payload.families
    ]
    if not chosen:
        raise NotFound("MNX-FITTING-0013", "고른 식이 이 재료군에 없습니다.")

    # **축이 다르면 곡선도 다르다.** 같은 대표 곡선에서 금속은 진응력을, 고무는
    # 공칭을 꺼낸다 — 축마다 한 번씩만 꺼내고 그 축을 쓰는 식들에 함께 물린다.
    results: list[fitting.FitResult] = []
    group = None
    strain = np.asarray([], dtype=np.float64)
    stress = np.asarray([], dtype=np.float64)
    notes: list[str] = []
    for axes in dict.fromkeys((item.x_column, item.y_column) for item in chosen):
        same = [item for item in chosen if (item.x_column, item.y_column) == axes]
        found, x, y, axis_notes = _representative(
            db, user, payload.material_id, payload.test_type_key, payload.orientation, same[0]
        )
        if group is None:
            # **점은 첫 축의 것이다.** 축이 섞이면 아래에서 그 사실을 말한다 —
            # 그래프 하나에 두 축의 점을 겹쳐 놓으면 무엇을 보는지 알 수 없다.
            group, strain, stress = found, x, y
            notes.extend(axis_notes)
        # **자기 축의 곡선에 맞춘다.** 여기서 `strain`(첫 축의 점)을 넘기면 두
        # 번째 축의 식이 남의 데이터에 맞춰지고, 그 결과는 그럴듯하게 나온다.
        results.extend(fitting.compare(x, y, families=tuple(item.key for item in same)))
    results.sort(key=lambda item: item.relative_rmse)
    assert group is not None
    axis_pairs = {(item.x_column, item.y_column) for item in chosen}
    if len(axis_pairs) > 1:
        notes.append(
            "축이 다른 식이 섞여 있습니다 — 아래 그래프의 점은 첫 번째 축의 것이고, "
            "다른 축에 맞춘 식은 그 점 위에 겹쳐 그리면 안 됩니다. 재료군을 정하면 "
            "한 축만 남습니다."
        )
    if not results:
        raise AppError(
            "MNX-FITTING-0004",
            f"어느 식도 맞추지 못했습니다. 대표 곡선이 {len(strain)}점인데 "
            f"적합에는 {fitting.MIN_POINTS}점 이상이 필요합니다 — "
            f"레시피의 재샘플 점 수를 늘려 보세요.",
            status=422,
        )
    # **카드가 쓸 값을 미리 보여 준다.** 만들 때와 같은 계산이다 — 화면이 재료
    # API 를 따로 불러 나름대로 판정하면 규칙이 두 벌이 되고, 어긋나는 순간
    # 화면이 거짓말을 한다.
    samples = _samples_of(db, group)
    return FitPreviewOut(
        source_points=[(float(x), float(y)) for x, y in zip(strain, stress, strict=True)],
        sample_count=len(group.members),
        fits=[_fit_out(item) for item in results],
        elastic=[
            InheritedValueOut(
                key=key, label=label, value=got.value, source=got.source, detail=got.detail
            )
            for key, label, got in (
                ("poisson_ratio", "푸아송비", _inherit_poisson(group.material, None)),
                ("density", "밀도", _inherit_density(group.material, samples, None)),
            )
        ],
        notes=notes,
    )


def _deck(item: PropertyCard, *, name: str, provenance: tuple[str, ...] = ()) -> export.Deck:
    """카드 행을 솔버 덱으로. **블록을 그대로 넘긴다.**

    전에는 여기서 `card_kwargs` 로 블록을 "카드 양식" 의 칸에 옮겨 담았다. 그
    양식이 없어졌으므로 옮길 일도 없다 — 무엇이 필요한지는 렌더러가 안다.
    """
    return export.Deck(
        name=name,
        solver_id=export.solver_id_from(str(item.id)),
        blocks=item.blocks,
        provenance=provenance,
    )


def _card_out(db: Session, item: PropertyCard) -> PropertyCardOut:
    cards.load_builtin()
    material = db.get(Material, item.material_id)
    test_type = db.get(TestType, item.test_type_id)
    # **낼 수 있는 형식을 미리 말한다.** 내려받기를 누른 뒤에 "푸아송비가
    # 없습니다" 를 보는 것은 늦다.
    #
    # 모르는 블록이 실려 있으면(그 물성을 만든 계산이 지금 코드에 없으면) 목록
    # 전체가 죽지 않게 붙잡되, **없던 일로 하지는 않는다** — `problem` 에 담아
    # 화면이 그 카드만 짚을 수 있게 한다.
    strays = cards.unknown(item.blocks)
    problem = (
        f"모르는 물성 블록입니다: {', '.join(strays)}. 이 카드를 만든 계산이 지금 "
        f"코드에 없습니다."
        if strays
        else None
    )
    formats = list(export.available_formats(_deck(item, name="CARD")))
    return PropertyCardOut(
        id=item.id,
        material_id=item.material_id,
        material_name=material.record_name if material else "?",
        test_type_key=test_type.key if test_type else "?",
        orientation=item.orientation,
        label=item.label,
        status=item.status,
        source=item.source,
        blocks=item.blocks,
        available_formats=formats,
        problem=problem,
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
    fitting.load_builtin()
    spec = fitting.FAMILIES.get(payload.family) if payload.family else None
    if payload.family and spec is None:
        raise NotFound("MNX-FITTING-0013", f"모르는 적합식입니다: {payload.family}")

    group, strain, stress, notes = _representative(
        db, user, payload.material_id, payload.test_type_key, payload.orientation, spec
    )

    fitted: dict[str, Any] = {}
    if spec is not None:
        try:
            result = fitting.fit(spec.key, strain, stress)
        except fitting.FittingError as exc:
            raise AppError("MNX-FITTING-0004", str(exc), status=422) from exc
        # ── 두 식을 섞을까 ──────────────────────────────────────────────
        #
        # **적합을 좋게 하려는 것이 아니라 외삽을 조정하는 것이다.** 측정 구간에서는
        # 두 식이 거의 같은데 그 밖에서 크게 갈린다.
        curve: fitting.FitResult | fitting.Blended = result
        rows = [
            {
                "name": item.name,
                "value": item.value,
                "si_unit": item.si_unit,
                "lower": item.lower,
                "upper": item.upper,
                "initial": item.initial,
            }
            for item in result.parameters
        ]
        blend_values: dict[str, Any] = {}
        if payload.blend_with is not None:
            if payload.blend_weight is None:
                raise AppError(
                    "MNX-FITTING-0015",
                    "섞을 비중을 함께 주세요. 데이터가 정하지 못하는 값이라 "
                    "기본값을 두지 않습니다.",
                    status=422,
                )
            other = fitting.FAMILIES.get(payload.blend_with)
            if other is None or other.block != spec.block:
                raise AppError(
                    "MNX-FITTING-0015",
                    f"'{payload.blend_with}' 는 '{spec.label}' 과 섞을 수 있는 식이 아닙니다.",
                    status=422,
                )
            try:
                second = fitting.fit(other.key, strain, stress)
                curve = fitting.blend(result, second, payload.blend_weight, strain, stress)
            except fitting.FittingError as exc:
                raise AppError("MNX-FITTING-0015", str(exc), status=422) from exc
            # **어느 식의 계수인지 이름에 남긴다.** 둘이 섞여 들어오므로 이름만으로는
            # 구별이 안 된다.
            rows = [
                {**row, "name": f"{parent.label}·{row['name']}"}
                for parent, source in ((result, result), (second, second))
                for row in (
                    {
                        "name": item.name,
                        "value": item.value,
                        "si_unit": item.si_unit,
                        "lower": item.lower,
                        "upper": item.upper,
                        "initial": item.initial,
                    }
                    for item in source.parameters
                )
            ]
            blend_values = {
                "blend_with": second.family,
                "blend_weight": payload.blend_weight,
            }
            notes.extend(curve.notes)

        # **식이 자기 요약값을 낸다.** 초탄성의 초기 전단탄성률처럼, 식마다
        # 계산이 다른데 서로 견줄 수 있는 값이 있다. 혼합에는 파라미터 배열이
        # 하나가 아니므로 낼 수 없다.
        values = np.asarray([item.value for item in result.parameters], dtype=np.float64)
        extras = spec.extras(values) if spec.extras and payload.blend_with is None else {}
        fitted = {
            "values": {
                "family": curve.family,
                "label": curve.label,
                # **적합도를 함께 저장한다.** 파라미터만 남기면 그 값이 데이터와
                # 얼마나 맞는지 다시 알 수 없고, 그러면 카드를 믿을 근거가 사라진다.
                "rmse": curve.rmse,
                "relative_rmse": curve.relative_rmse,
                "r_squared": curve.r_squared,
                "max_residual": curve.max_residual,
                "strain_min": curve.strain_min,
                "strain_max": curve.strain_max,
                **extras,
                **blend_values,
            },
            # **행이 자기 단위를 든다.** 경화식 파라미터는 식마다 단위가 다르다 —
            # Voce 의 `b` 는 무차원이고 `q` 는 Pa 다. 열 선언 하나로는 못 적는다.
            "rows": rows,
            "notes": list(curve.notes),
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
    samples = _samples_of(db, group)
    poisson = _inherit_poisson(group.material, payload.poisson_ratio)
    density = _inherit_density(group.material, samples, payload.density)
    inherited_notes = [
        f"푸아송비: {poisson.detail}" if poisson.detail else "",
        f"밀도: {density.detail}" if density.detail else "",
    ]

    # ── 소성 표를 어디까지 낼까 ─────────────────────────────────────────
    #
    # **측정 구간만 내보내는 것도 결정이다.** 솔버는 표 밖에서 마지막 응력을
    # 붙들고 가는데, 금속은 계속 경화하므로 그 구간에서 하중을 낮게 계산한다.
    # 지어내지 않는 것이 아니라 다른 값을 조용히 지어내는 것이다.
    table_values: dict[str, Any] = {"source": "측정", "measured_max": float(strain[-1])}
    table_rows = [
        {"plastic_strain": float(x), "true_stress": float(y)}
        for x, y in zip(strain, stress, strict=True)
    ]
    if payload.extrapolate_to is not None:
        if spec is None:
            raise AppError(
                "MNX-FITTING-0014",
                "늘릴 식을 안 골랐습니다. 표만 저장하면 늘릴 근거가 없습니다.",
                status=422,
            )
        if spec.block != "hardening":
            raise AppError(
                "MNX-FITTING-0014",
                f"'{spec.label}' 은 소성 표를 만드는 식이 아닙니다.",
                status=422,
            )
        try:
            extended = fitting.extend_table(curve, strain, stress, to=payload.extrapolate_to)
        except fitting.FittingError as exc:
            raise AppError("MNX-FITTING-0014", str(exc), status=422) from exc
        table_rows = [
            {"plastic_strain": float(x), "true_stress": float(y)} for x, y in extended.points
        ]
        table_values = {
            "source": "외삽",
            "measured_max": extended.measured_max,
            "extrapolated_to": extended.extrapolated_to,
            "family": curve.label,
            "junction_gap": extended.junction_gap,
        }
        notes.extend(extended.notes)

    elastic = {
        # **없는 값은 넣지 않는다.** 0 이나 0.3 으로 채우면 그것이 측정값인지
        # 기본값인지 나중에 알 수 없다.
        #
        # 값과 함께 **출처**를 박는다(`<키>_source`). 재료·시료를 나중에 고쳐도
        # 이 카드가 무엇을 썼는지는 그대로 남는다.
        **(
            {"youngs_modulus": modulus, "youngs_modulus_source": "measured"}
            if modulus is not None
            else {}
        ),
        **(
            {"poisson_ratio": poisson.value, "poisson_ratio_source": poisson.source}
            if poisson.value is not None
            else {}
        ),
        **(
            {"density": density.value, "density_source": density.source}
            if density.value is not None
            else {}
        ),
    }

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
            "notes": [*notes, *[line for line in inherited_notes if line]],
            # **카드가 자기 근거를 들고 있다** 는 원칙의 나머지 절반이다 —
            # 값이 무엇에서 나왔는지에 더해 **무엇 위에서 계산됐는지**.
            "runtime": runtime.manifest(),
        },
        blocks={
            **({"elastic": {"values": elastic}} if elastic else {}),
            **({spec.block: fitted} if spec is not None and fitted else {}),
            # **소성 표는 금속 카드의 것이다.** 고무는 공칭 축에 맞췄고, 그 점을
            # `*PLASTIC` 자리에 넣으면 덱은 돌고 재료만 딴판이 된다.
            **(
                {"table": {"values": table_values, "rows": table_rows}}
                if spec is None or spec.block == "hardening"
                else {}
            ),
        },
        point_count=len(table_rows) if spec is None or spec.block == "hardening" else 0,
        note=payload.note,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _card_out(db, item)


@router.post("/cards/viscoelastic", response_model=PropertyCardOut, status_code=201)
def create_viscoelastic_card(
    payload: ViscoelasticCardSaveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyCardOut:
    """Prony 적합에서 점탄성 카드를 만든다.

    **묶음을 받지 않는다.** 경화 카드는 재료+시험종류+방향의 대표 곡선에서
    나오지만 Prony 는 마스터커브 하나에 매달려 있다. 그것을 묶음에 억지로 끼우면
    "여러 시편의 평균" 이라는 묶음의 뜻이 무너진다 — 재료·방향은 체인을 따라간다.

    시편 1건짜리 카드는 이미 허용하기로 한 것이다(`_representative` 참조). 막으면
    사람은 시스템 밖에서 계산해 카드 없이 덱을 만들고, 그러면 근거가 아무 데도
    안 남는다. 대신 **표본 1건이라는 사실을 카드에 박는다.**

    ## `*ELASTIC` 은 순간 탄성률이다

    E₀ 를 **탄성 블록에** 출처 `prony` 로 넣는다. Abaqus 는 `*VISCOELASTIC` 이
    있을 때 `*ELASTIC` 을 순간 탄성률로 읽는데, 평형 탄성률을 넣으면 재료가
    통째로 무르게 계산되고 **덱은 멀쩡히 돌고 결과도 그럴듯하다.**
    """
    cards.load_builtin()
    fit = db.get(PronyFit, payload.prony_fit_id)
    if fit is None:
        raise NotFound("MNX-FITTING-0011", "Prony 적합을 찾을 수 없습니다.")
    curve = db.get(MasterCurve, fit.master_curve_id)
    if curve is None:
        raise NotFound("MNX-FITTING-0011", "마스터커브를 찾을 수 없습니다.")
    run = permissions.get_run(db, user, curve.test_run_id)  # 볼 권한이 있는가
    specimen = db.get(Specimen, run.specimen_id)
    sample = db.get(Sample, specimen.sample_id) if specimen else None
    material = db.get(Material, sample.material_id) if sample else None
    if specimen is None or sample is None or material is None:
        raise NotFound("MNX-FITTING-0011", "이 적합이 어느 재료의 것인지 따라갈 수 없습니다.")

    series = prony.PronySeries(
        equilibrium_pa=fit.equilibrium_pa,
        terms=tuple(
            prony.PronyTerm(
                modulus_pa=float(term["modulus_pa"]),
                relaxation_time_s=float(term["relaxation_time_s"]),
            )
            for term in fit.terms
        ),
        normalized_rmse=fit.normalized_rmse,
        bic=fit.bic,
        at_bound=tuple(fit.at_bound),
    )
    try:
        relative = series.relative_moduli
    except prony.PronyError as exc:
        raise AppError("MNX-FITTING-0012", str(exc), status=422) from exc

    poisson = _inherit_poisson(material, payload.poisson_ratio)
    density = _inherit_density(material, [sample], payload.density)
    notes = [
        # **1건이라는 사실이 덱까지 따라가야 한다.** 솔버 결과를 놓고 "이 물성
        # 어디서 났나" 를 묻는 자리에서 그 오해가 제일 비싸다.
        f"시편 {specimen.record_name} 한 건의 마스터커브에서 만들었습니다 — "
        f"재료의 대푯값이 아니라 그 시편의 값입니다.",
        f"푸아송비: {poisson.detail}" if poisson.detail else "",
        f"밀도: {density.detail}" if density.detail else "",
    ]
    if series.at_bound:
        # **관측 밖을 외삽하고 있다.** 조용히 넘기면 덱을 받은 사람이 모른다.
        notes.append(
            f"완화시간 {len(series.at_bound)}개가 관측 범위 경계에 붙어 있습니다 — "
            f"그만큼은 잰 범위 밖을 외삽한 값입니다."
        )

    item = PropertyCard(
        material_id=material.id,
        test_type_id=run.test_type_id,
        orientation=specimen.orientation,
        label=payload.label,
        status="draft",
        # **적합을 외래키로 잡지 않는다.** 시험을 지우면 마스터커브와 적합이
        # 함께 지워지는데(CASCADE), 그때 카드까지 못 지우게 막거나 값을 잃으면
        # 안 된다 — 카드는 **자기 근거를 들고 있는 스냅샷**이다. 가리키던 적합이
        # 사라져도 계수·기준 온도·표본 수는 카드 안에 그대로 남는다.
        source={
            "sample_count": 1,
            "test_run_ids": [str(run.id)],
            "record_names": [run.record_name],
            "prony_fit_id": str(fit.id),
            "master_curve_id": str(curve.id),
            "notes": [line for line in notes if line],
            # **카드가 자기 근거를 들고 있다** 는 원칙의 나머지 절반이다 —
            # 값이 무엇에서 나왔는지에 더해 **무엇 위에서 계산됐는지**.
            "runtime": runtime.manifest(),
        },
        blocks={
            "elastic": {
                "values": {
                    # **순간 탄성률이다.** 평형 탄성률을 넣으면 재료가 무르게 계산된다.
                    "youngs_modulus": series.instantaneous_pa,
                    "youngs_modulus_source": "prony",
                    **(
                        {
                            "poisson_ratio": poisson.value,
                            "poisson_ratio_source": poisson.source,
                        }
                        if poisson.value is not None
                        else {}
                    ),
                    **(
                        {"density": density.value, "density_source": density.source}
                        if density.value is not None
                        else {}
                    ),
                }
            },
            "viscoelastic": {
                "values": {
                    "equilibrium_pa": fit.equilibrium_pa,
                    "instantaneous_pa": series.instantaneous_pa,
                    "reference_temperature_k": curve.reference_temperature_k,
                    "normalized_rmse": fit.normalized_rmse,
                    "bic": fit.bic,
                    "shift_method": curve.method,
                },
                "rows": [
                    {
                        "relaxation_time_s": term.relaxation_time_s,
                        "modulus_pa": term.modulus_pa,
                        "relative_modulus": ratio,
                    }
                    for term, ratio in zip(series.terms, relative, strict=True)
                ],
                "notes": list(curve.notes),
            },
        },
        point_count=0,
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


def _card_workspace(db: Session, item: PropertyCard) -> uuid.UUID | None:
    """카드가 어느 부서의 것인가. 감사 목록의 가시성 판정에 쓴다."""
    material = db.get(Material, item.material_id)
    return material.owner_workspace_id if material else None


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
            requires=list(export.requires_labels(item.key)),
        )
        for item in export.list_renderers()
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
    cards.load_builtin()
    elastic = cards.values_of(item.blocks.get("elastic"))
    hardening = cards.values_of(item.blocks.get("hardening"))
    hyper = cards.values_of(item.blocks.get("hyperelastic"))
    table = cards.values_of(item.blocks.get("table"))
    provenance = [
        f"재료 {material.record_name if material else '?'} · "
        f"{test_type.key if test_type else '?'} · {item.orientation}",
        # **덱을 나중에 읽는 사람에게는 이 줄이 근거의 전부다.** 1개짜리를
        # '대표 곡선' 이라고 쓰면 여러 시편의 평균으로 읽힌다 — 솔버 결과를
        # 놓고 "이 물성 어디서 났나" 를 물을 때 그 오해가 제일 비싸다.
        (
            "시편 1개의 곡선에서 만들었습니다 — 재료의 대푯값이 아니라 그 시편의 값입니다."
            if item.source.get("sample_count") == 1
            else f"시편 {item.source.get('sample_count', '?')}개의 대표 곡선에서 만들었습니다."
        ),
        f"카드 {item.id} ({STATUS_NOTES.get(item.status, item.status)})",
    ]
    # 값마다 어디서 왔는지 한 줄씩. 없는 값은 애초에 카드에 없다.
    for key, label in (
        ("youngs_modulus", "탄성계수"),
        ("poisson_ratio", "푸아송비"),
        ("density", "밀도"),
    ):
        origin = SOURCE_NOTES.get(str(elastic.get(f"{key}_source", "")))
        if elastic.get(key) is not None and origin:
            provenance.append(f"{label}: {origin}")

    if table.get("source") == "외삽":
        # **덱만 받은 사람이 알아야 한다.** 어디까지가 시험이고 어디부터가 식인지
        # 표만 봐서는 구별이 안 된다 — 점이 나란히 있을 뿐이다.
        provenance.append(
            f"소성 표: 소성변형률 {float(table.get('measured_max', 0.0)):.5g} 까지는 측정, "
            f"그 위 {float(table.get('extrapolated_to', 0.0)):.5g} 까지는 "
            f"{table.get('family', '?')} 으로 늘렸습니다 — 외삽 구간은 시험으로 "
            f"검증되지 않았습니다."
        )
    if hyper.get("label"):
        # **단축 하나로 맞췄다는 사실이 덱까지 따라가야 한다.** 평면 전단·등이축
        # 에서는 크게 빗나갈 수 있다 — 덱만 받은 사람은 알 길이 없다.
        provenance.append(
            f"초탄성 식: {hyper['label']} · {hyper.get('mode', '?')} 데이터 · 상대 RMSE "
            f"{float(hyper.get('relative_rmse', 0.0)) * 100:.3g}% · 공칭 변형률 "
            f"{float(hyper.get('strain_min', 0.0)):.5g}~"
            f"{float(hyper.get('strain_max', 0.0)):.5g} "
            f"(그 밖은 검증되지 않았습니다)"
        )
        provenance.append(hyperelastic.UNIAXIAL_ONLY)
    if hardening.get("label"):
        # **경화식은 덱에 안 들어간다.** 표로 나간다. 그래도 어떤 식으로 봤는지는
        # 적어 둔다 — 이 표가 어디까지 검증된 것인지가 거기에 있다.
        provenance.append(
            f"경화식 참고: {hardening['label']} · 상대 RMSE "
            f"{float(hardening.get('relative_rmse', 0.0)) * 100:.3g}% · "
            f"적합 구간 소성변형률 {float(hardening.get('strain_min', 0.0)):.5g}~"
            f"{float(hardening.get('strain_max', 0.0)):.5g} (그 밖은 검증되지 않았습니다)"
        )

    deck = _deck(item, name=export.sanitize_name(base), provenance=tuple(provenance))
    try:
        rendered = export.render(format, deck)
        target = export.renderer(format)
    except export.ExportError as exc:
        raise AppError("MNX-FITTING-0009", str(exc), status=422) from exc

    return Response(
        content=rendered.text,
        media_type=target.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{deck.name}.{target.extension}"'
        },
    )


#: 카드 상태를 덱 주석에 적는 말. 초안인 덱이 돌아다닐 수 있다.
STATUS_NOTES = {
    "draft": "초안 — 아직 확정되지 않았습니다",
    "published": "확정",
    "deprecated": "내려진 카드 — 쓰지 마세요",
}


@router.patch("/cards/{card_id}", response_model=PropertyCardOut)
def update_card(
    card_id: uuid.UUID,
    payload: PropertyCardUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyCardOut:
    """이름과 메모를 고친다. **초안일 때만.**

    값은 여기서도 못 바꾼다 — 바꾸는 길이 아예 없어야 "이 카드가 무엇으로
    나왔나" 에 항상 답할 수 있다. 다만 이름 오타 하나 때문에 카드를 지우고
    적합을 다시 돌리게 하는 것은 그 원칙이 지키려던 것과 무관하다.
    """
    item = _visible_card(db, user, card_id)
    if item.status != "draft":
        raise AppError(
            "MNX-FITTING-0009",
            "확정된 카드는 이름을 바꿀 수 없습니다. 그 이름으로 덱이 이미 "
            "나갔을 수 있습니다 — 새 카드를 만드세요.",
            status=409,
        )

    data = payload.model_dump(exclude_unset=True)
    for field in ("label", "note"):
        if field in data:
            setattr(item, field, data[field])
    db.commit()
    db.refresh(item)
    return _card_out(db, item)


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
    # **이 값으로 해석이 돌 수 있다.** 누가 언제 올렸는지가 남아야 하고, 카드를
    # 나중에 지워도 그 기록은 남는다.
    audit.record(
        db,
        action=audit.CARD_PUBLISHED,
        actor=user,
        target_table="property_cards",
        target_id=item.id,
        target_label=item.label,
        workspace_id=_card_workspace(db, item),
        changes={"status": {"before": "draft", "after": "published"}},
    )
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
    before = item.status
    item.status = "deprecated"
    audit.record(
        db,
        action=audit.CARD_DEPRECATED,
        actor=user,
        target_table="property_cards",
        target_id=item.id,
        target_label=item.label,
        workspace_id=_card_workspace(db, item),
        changes={"status": {"before": before, "after": "deprecated"}},
    )
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
    # **지워도 기록은 남는다.** 대상에 외래키를 안 건 이유가 이것이다 — 카드가
    # 사라져도 "그 카드가 있었고 누가 지웠다" 는 남아야 한다.
    audit.record(
        db,
        action=audit.CARD_DELETED,
        actor=user,
        target_table="property_cards",
        target_id=item.id,
        target_label=item.label,
        workspace_id=_card_workspace(db, item),
    )
    db.delete(item)
    db.commit()
    return Response(status_code=204)
