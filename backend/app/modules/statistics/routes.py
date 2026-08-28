"""통계 — 재료 단위 물성과 앙상블 곡선.

**화면은 늘 최신을 본다. 저장은 사람이 명시적으로 한다**(ADR 0007 과 같은 모델).
시험이 하나 더 붙으면 평균이 달라지는데, 어제 보고서에 적은 값은 어제의 표본으로
나온 것이다. 그래서 조회는 매번 계산하고, 남겨야 할 때만 `EnsembleResult` 를 만든다.

**아무것도 버리지 않는다.** 이상치는 후보로 표시하고, 채택되지 않아 빠진 시험은
몇 건인지 말한다 — 조용히 빼면 n 이 왜 그 수인지 알 수 없다.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.statistics import services
from app.modules.statistics.models import EnsembleResult
from app.modules.statistics.schemas import (
    CurveStatsOut,
    DistributableKeyOut,
    DistributionCandidateOut,
    DistributionReportOut,
    DivisionOverviewOut,
    DivisionTallyOut,
    EnsembleResultOut,
    EnsembleSaveRequest,
    GroupOut,
    MaterialStatisticsOut,
    MemberCurveOut,
    ObservationOut,
    OutlierOut,
    OverviewOut,
    ScalarStatsOut,
    TallyOut,
    YearTallyOut,
)
from app.modules.tests.models import TestRun, TestType
from app.shared import divisions as divisions_order
from app.shared import permissions
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound
from matcore import distributions, statistics

router = APIRouter(prefix="/statistics", tags=["statistics"])


def _group_out(db: Session, group: services.Group, *, threshold: float) -> GroupOut:
    notes = [*services.setting_warnings(group), *services.sample_warnings(db, group)]
    curve = None
    # **1건이어도 곡선은 낸다.** 그 한 곡선이 곧 대표다 — 평균을 낼 상대가
    # 없다는 것과 그릴 곡선이 없다는 것은 다르다. `curve_table` 이 1건을
    # 따로 다루고, 응답의 `sample_count` 와 안내가 그 사실을 말한다.
    if group.members:
        # **격자가 맞는 축을 고른다.** 레시피가 어느 축에서 재샘플했는지에 따라
        # 공칭이 맞을 수도 진소성이 맞을 수도 있다. 하나만 보고 포기하면
        # "적합은 되는데 곡선은 안 보인다" 가 된다 — 실제로 그렇게 나왔다.
        #
        # 정렬을 대신 하는 것이 아니라 **볼 축을 고르는 것**이다(ADR 0008).
        # 어느 축으로 그렸는지는 응답에 그대로 실린다.
        attempted: list[str] = []
        for x, y in services.axis_candidates(db, group):
            curve, curve_notes = services.curve_table(db, group, x=x, y=y)
            if curve is not None:
                # **성공한 곡선의 근거도 남긴다.** 전에는 실패했을 때만 이유를
                # 실었는데, 그러면 "이 곡선이 무엇인가"(시편 1개의 것인지,
                # 공통 구간이 어디까지인지)가 통째로 사라진다.
                notes.extend(curve_notes)
                break
            attempted.extend(curve_notes)
        if curve is None:
            notes.extend(attempted)
    if group.skipped_unadopted:
        notes.append(
            f"채택되지 않은 시험 {group.skipped_unadopted}건은 빠졌습니다. "
            f"처리한 뒤 결과 탭에서 채택하면 여기에 들어옵니다."
        )
    if len(group.members) == 0:
        # **왜 비었는지 말한다.** 채택이 무엇인지 모르는 사람에게는 빈 화면이
        # 고장으로 보인다.
        notes.append(
            "채택된 시험이 없습니다. 시험 상세의 '처리' 탭에서 돌려 보고 저장한 뒤 "
            "'채택' 을 누르면 그 값이 이 재료의 물성이 됩니다."
        )
    elif len(group.members) == 1:
        # 값은 위에 나온다(시편 1개의 값). 여기서는 **무엇이 아직 없는지**를 적는다.
        notes.append(
            "시험 1건이라 아래는 그 시편의 값이고 흩어짐이 없습니다 — "
            "재료의 물성이라고 하려면 여러 번 재야 합니다. "
            "곡선은 그 시편의 곡선을 그대로 씁니다. "
            "2건부터 평균이, 3건부터 변동계수와 이상치가 나옵니다."
        )
    elif len(group.members) < statistics.MIN_FOR_SPREAD:
        # **화면에 뜨는 것과 안내가 어긋나면 안 된다.** 전에는 "변동계수를 내지
        # 않았습니다" 라고 적어 놓고 CV 열에는 값이 떠 있었다 — 커널은 2건부터
        # CV 를 내고, 막는 것은 이상치뿐이다.
        notes.append(
            f"시험이 {len(group.members)}건이라 이상치는 가려내지 않았습니다 "
            f"— {statistics.MIN_FOR_SPREAD}건부터 뜻이 생깁니다. "
            f"변동계수도 두 점 사이의 차이일 뿐이라 크게 흔들립니다."
        )

    # **1건이어도 값은 낸다.** 전에는 2건 미만이면 표를 통째로 비웠는데, 그러면
    # 처리하고 채택까지 한 사람이 빈 카드를 본다.
    scalars = services.scalar_table(group, threshold=threshold) if group.members else []
    return GroupOut(
        test_type_key=group.test_type.key,
        test_type_label=group.test_type.label,
        orientation=group.orientation,
        sample_count=len(group.members),
        skipped_unadopted=group.skipped_unadopted,
        test_run_ids=[member.run.id for member in group.members],
        record_names=[member.run.record_name for member in group.members],
        scalars=[
            ScalarStatsOut(
                **{key: value for key, value in row.items() if key != "outliers"},
                outliers=[OutlierOut(**item) for item in row["outliers"]],
            )
            for row in scalars
        ],
        curve=(
            CurveStatsOut(
                **curve,
                # **대표만 그리면 그것이 적절한지 알 수 없다.** 축은 대표 곡선의
                # 것을 그대로 쓴다 — 다른 축을 겹쳐 놓으면 그림이 거짓말을 한다.
                members=[
                    MemberCurveOut(
                        test_run_id=run.id, record_name=run.record_name, points=points
                    )
                    for run, points in services.member_curves(
                        db, group, x=curve["x"], y=curve["y"]
                    )
                ],
            )
            if curve
            else None
        ),
        notes=notes,
    )


@router.get("/materials/{material_id}", response_model=MaterialStatisticsOut)
def material_statistics(
    material_id: uuid.UUID,
    threshold: float = Query(default=statistics.DEFAULT_OUTLIER_THRESHOLD, gt=0, le=20),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MaterialStatisticsOut:
    """이 재료의 물성. **묶음은 시험종류 + 방향이다.**

    인장은 압연 방향에 따라 물성이 다르다 — MD 와 TD 를 한 통계로 묶으면 CV 가
    크게 나오는데 그것은 산포가 아니라 다른 것을 섞은 것이다.
    """
    material, groups = services.groups_for_material(db, user, material_id)
    return MaterialStatisticsOut(
        material_id=material.id,
        material_name=material.record_name,
        groups=[_group_out(db, group, threshold=threshold) for group in groups],
    )


@router.post("/ensembles", response_model=EnsembleResultOut, status_code=201)
def save_ensemble(
    payload: EnsembleSaveRequest,
    threshold: float = Query(default=statistics.DEFAULT_OUTLIER_THRESHOLD, gt=0, le=20),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EnsembleResultOut:
    """이 묶음의 통계를 남긴다. **불변이다** — 다시 저장하면 새 행이 생긴다.

    쓴 시험과 그때 채택돼 있던 결과를 함께 박아 둔다. 나중에 시험이 늘거나 채택이
    바뀌어도 이 값은 그대로다 — 그러지 않으면 "이 평균이 어디서 나왔나" 를 답할 수
    없고, 그 숫자는 근거가 없다.
    """
    material, groups = services.groups_for_material(db, user, payload.material_id)
    group = next(
        (
            item
            for item in groups
            if item.test_type.key == payload.test_type_key
            and item.orientation == payload.orientation
        ),
        None,
    )
    if group is None:
        raise NotFound("MNX-STATISTICS-0001", "그 묶음을 찾을 수 없습니다.")
    if len(group.members) < statistics.MIN_SAMPLES:
        raise AppError(
            "MNX-STATISTICS-0002",
            f"채택된 시험이 {len(group.members)}건입니다. "
            f"{statistics.MIN_SAMPLES}건 이상이어야 통계를 남길 수 있습니다.",
            status=422,
        )

    out = _group_out(db, group, threshold=threshold)
    item = EnsembleResult(
        material_id=material.id,
        test_type_id=group.test_type.id,
        orientation=group.orientation,
        sample_count=len(group.members),
        test_run_ids=[str(member.run.id) for member in group.members],
        result_ids=[str(member.result.id) for member in group.members],
        scalars=[row.model_dump(mode="json") for row in out.scalars],
        curve=out.curve.model_dump(mode="json") if out.curve else {},
        notes=out.notes,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return EnsembleResultOut(
        id=item.id,
        material_id=item.material_id,
        test_type_key=group.test_type.key,
        orientation=item.orientation,
        sample_count=item.sample_count,
        test_run_ids=[uuid.UUID(value) for value in item.test_run_ids],
        created_at=item.created_at,
    )


@router.get("/ensembles", response_model=list[EnsembleResultOut])
def list_ensembles(
    material_id: uuid.UUID = Query(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[EnsembleResultOut]:
    services.groups_for_material(db, user, material_id)  # 가시성 판정
    items = db.scalars(
        select(EnsembleResult)
        .where(EnsembleResult.material_id == material_id)
        .order_by(EnsembleResult.created_at.desc())
    )
    types = {item.id: item for item in db.scalars(select(TestType))}
    return [
        EnsembleResultOut(
            id=item.id,
            material_id=item.material_id,
            test_type_key=types[item.test_type_id].key if item.test_type_id in types else "?",
            orientation=item.orientation,
            sample_count=item.sample_count,
            test_run_ids=[uuid.UUID(value) for value in item.test_run_ids],
            created_at=item.created_at,
        )
        for item in items
    ]


# --- 분포 ------------------------------------------------------------------
#
# **흩어짐이 얼마나 큰지와 어떤 모양인지는 다른 물음이다.** 위쪽이 평균·SD·CV 를
# 내고 여기가 모양을 묻는다. 설계가 실제로 알고 싶은 것은 대개 "하위 5% 가
# 얼마인가" 인데, 그 답은 같은 평균·같은 SD 에서도 모양에 따라 달라진다.


def _find_group(
    db: Session, user: User, material_id: uuid.UUID, test_type_key: str, orientation: str
) -> tuple[object, services.Group]:
    material, groups = services.groups_for_material(db, user, material_id)
    group = next(
        (
            item
            for item in groups
            if item.test_type.key == test_type_key and item.orientation == orientation
        ),
        None,
    )
    if group is None:
        raise NotFound("MNX-STATISTICS-0001", "그 묶음을 찾을 수 없습니다.")
    return material, group


@router.get("/materials/{material_id}/distributable", response_model=list[DistributableKeyOut])
def distributable(
    material_id: uuid.UUID,
    test_type_key: str = Query(...),
    orientation: str = Query(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[DistributableKeyOut]:
    """분포를 물어볼 수 있는 항목 목록.

    **값이 몇 개인지 함께 준다.** 화면이 미리 "이 항목은 5개뿐입니다" 를 말할 수
    있어야 한다 — 눌러 보고 나서 "모자랍니다" 를 받으면 무엇이 문제인지 알기
    어렵다(잠그는 이유를 함께 보이는 것, 시험 종류 편집과 같은 태도다).
    """
    _material, group = _find_group(db, user, material_id, test_type_key, orientation)
    out: list[DistributableKeyOut] = []
    for key in services.distributable_keys(group):
        values, _labels, label, unit = services.scalar_values(group, key)
        out.append(
            DistributableKeyOut(
                key=key,
                label=label,
                si_unit=unit,
                count=sum(1 for value in values if value is not None),
            )
        )
    return out


@router.get("/materials/{material_id}/distributions", response_model=DistributionReportOut)
def distribution_report(
    material_id: uuid.UUID,
    test_type_key: str = Query(...),
    orientation: str = Query(...),
    scalar_key: str = Query(...),
    bootstrap: int = Query(default=distributions.BOOTSTRAP, ge=0, le=2000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DistributionReportOut:
    """정규·로그정규·와이블을 나란히 맞춘다. **고르지 않고 견줘 준다.**

    경화식과 같은 태도다(ADR 0009) — 1등만 돌려주면 2등과 얼마나 갈렸는지가
    사라지고, 그 차이가 작을 때는 데이터가 정한 것이 아니라 우리가 정한 것이 된다.

    `bootstrap` 을 낮추면 빨라지는 대신 p 값이 거칠어진다. 0 이면 p 를 안 낸다 —
    **화면을 넘기며 훑을 때** 쓰라고 열어 둔다. 기본값은 999 다.
    """
    _material, group = _find_group(db, user, material_id, test_type_key, orientation)
    values, labels, label, unit = services.scalar_values(group, scalar_key)
    if not any(value is not None for value in values):
        raise NotFound(
            "MNX-STATISTICS-0003",
            f"'{scalar_key}' 값을 가진 시험이 이 묶음에 없습니다.",
        )

    try:
        report = distributions.fit_all(values, bootstrap=bootstrap)
    except distributions.DistributionError as caught:
        raise AppError("MNX-STATISTICS-0004", str(caught), status=422) from caught

    return DistributionReportOut(
        material_id=material_id,
        test_type_key=test_type_key,
        orientation=orientation,
        scalar_key=scalar_key,
        scalar_label=label,
        si_unit=unit,
        count=report.count,
        observations=[
            ObservationOut(
                specimen_label=labels[item.index], status=item.status, value=item.value
            )
            for item in report.observations
        ],
        candidates=[
            DistributionCandidateOut(
                key=item.key,
                label=item.label,
                status=item.status,
                reason=item.reason,
                parameters=list(item.parameters),
                parameter_names=list(item.parameter_names),
                parameter_labels=list(item.parameter_labels),
                log_likelihood=item.log_likelihood,
                aicc=item.aicc,
                delta_aicc=item.delta_aicc,
                anderson_darling=item.anderson_darling,
                p_value=item.p_value,
                quantiles=item.quantiles,
            )
            for item in report.candidates
        ],
        best=report.best,
        notes=list(report.notes),
    )


# --- 요약 ------------------------------------------------------------------
#
# **세는 일을 서버가 한다.** 목록 엔드포인트만 있으면 화면이 재료 94개를 세려고
# 94행을 받게 된다. 홈은 매일 열리는 화면이라 그 비용이 매일 든다.


def _tally(rows: Sequence[Any]) -> list[TallyOut]:
    return [TallyOut(key=str(key), label=str(key), count=int(count)) for key, count in rows]


@router.get("/divisions", response_model=DivisionOverviewOut)
def divisions(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DivisionOverviewOut:
    """사업부별 현황 — 시험 수와, 그 시험이 걸친 재료·시료·시편 수.

    범위는 시험의 가시성 그대로(`visible_runs`) — 홈의 다른 숫자와 같은 규칙이다.
    사업부는 시험에만 붙으므로 재료·시편은 **그 사업부 시험이 걸친 것**을 센다 —
    사업부끼리 합치면 전체보다 클 수 있다(같은 재료를 두 사업부가 시험한다).
    """
    runs = permissions.visible_runs(db, user).subquery()
    rows = db.execute(
        select(
            TestRun.division,
            func.count(TestRun.id),
            func.count(func.distinct(TestRun.specimen_id)),
            func.count(func.distinct(Specimen.sample_id)),
            func.count(func.distinct(Sample.material_id)),
        )
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(TestRun.id.in_(select(runs.c.id)))
        .group_by(TestRun.division)
    ).all()
    tallies = sorted(
        (
            DivisionTallyOut(
                division=division or divisions_order.UNSET,
                run_count=int(run_count),
                specimen_count=int(specimen_count),
                sample_count=int(sample_count),
                material_count=int(material_count),
            )
            for division, run_count, specimen_count, sample_count, material_count in rows
        ),
        key=lambda one: divisions_order.rank(one.division),
    )

    # 연간 — 해는 시험일. 옛 시험을 오늘 올리는 일이 흔해서(이관) 등록일로 세면
    # 이관한 해에 다 몰린다. 시험일이 빈 것만 등록일로 본다.
    year = func.extract("year", func.coalesce(TestRun.tested_at, TestRun.created_at))
    yearly_rows = db.execute(
        select(year, TestRun.division, func.count(TestRun.id))
        .where(TestRun.id.in_(select(runs.c.id)))
        .group_by(year, TestRun.division)
    ).all()
    yearly = sorted(
        (
            YearTallyOut(
                year=int(y), division=division or divisions_order.UNSET, run_count=int(count)
            )
            for y, division, count in yearly_rows
        ),
        key=lambda one: (one.year, divisions_order.rank(one.division)),
    )
    return DivisionOverviewOut(divisions=tallies, yearly=yearly)


@router.get("/overview", response_model=OverviewOut)
def overview(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OverviewOut:
    """홈에 뿌리는 요약 한 벌.

    **부서 범위는 각 항목이 원래 따르는 규칙 그대로다.** 재료·시험은
    `permissions` 의 가시성을 쓰고, 카드는 재료를 따라간다. 여기서 규칙을 새로
    만들면 홈의 숫자와 목록 화면의 숫자가 갈리고, 그때 어느 쪽이 맞는지 알 방법이
    없다.
    """
    materials = permissions.visible_material_ids(db, user).subquery()
    material_ids = select(materials.c[0])

    families = _tally(
        db.execute(
            select(Material.family, func.count())
            .where(Material.id.in_(material_ids))
            .group_by(Material.family)
            .order_by(func.count().desc())
        ).all()
    )

    runs = permissions.visible_runs(db, user).subquery()
    run_ids = select(runs.c.id)
    test_types = _tally(
        db.execute(
            select(TestType.label, func.count())
            .join(TestRun, TestRun.test_type_id == TestType.id)
            .where(TestRun.id.in_(run_ids))
            .group_by(TestType.label)
            .order_by(func.count().desc())
        ).all()
    )

    cards = (
        select(PropertyCard.status, func.count())
        .where(PropertyCard.material_id.in_(material_ids))
        .group_by(PropertyCard.status)
    )
    by_status = {str(status): int(count) for status, count in db.execute(cards).all()}

    def count(query: Select[Any]) -> int:
        return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)

    return OverviewOut(
        material_count=count(select(materials.c[0])),
        families=families,
        sample_count=count(
            select(Sample.id).where(
                Sample.material_id.in_(material_ids), Sample.deleted_at.is_(None)
            )
        ),
        specimen_count=count(
            select(Specimen.id)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Sample.material_id.in_(material_ids), Specimen.deleted_at.is_(None))
        ),
        run_count=count(select(runs.c.id)),
        test_types=test_types,
        card_total=sum(by_status.values()),
        card_published=by_status.get("published", 0),
        card_draft=by_status.get("draft", 0),
        card_deprecated=by_status.get("deprecated", 0),
        materials_with_card=count(
            select(PropertyCard.material_id)
            .where(PropertyCard.material_id.in_(material_ids))
            .group_by(PropertyCard.material_id)
        ),
        # **읽혔는데 아직 채택이 없는 것.** 이것이 2단계에 남은 일이다.
        waiting_to_process=count(
            select(runs.c.id).where(
                runs.c.status == "parsed", runs.c.adopted_result_id.is_(None)
            )
        ),
        parse_failed=count(select(runs.c.id).where(runs.c.status == "failed")),
    )
