"""통계 — 재료 단위 물성과 앙상블 곡선.

**화면은 늘 최신을 본다. 저장은 사람이 명시적으로 한다**(ADR 0007 과 같은 모델).
시험이 하나 더 붙으면 평균이 달라지는데, 어제 보고서에 적은 값은 어제의 표본으로
나온 것이다. 그래서 조회는 매번 계산하고, 남겨야 할 때만 `EnsembleResult` 를 만든다.

**아무것도 버리지 않는다.** 이상치는 후보로 표시하고, 채택되지 않아 빠진 시험은
몇 건인지 말한다 — 조용히 빼면 n 이 왜 그 수인지 알 수 없다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.statistics import services
from app.modules.statistics.models import EnsembleResult
from app.modules.statistics.schemas import (
    CurveStatsOut,
    EnsembleResultOut,
    EnsembleSaveRequest,
    GroupOut,
    MaterialStatisticsOut,
    OutlierOut,
    ScalarStatsOut,
)
from app.modules.tests.models import TestType
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound
from matcore import statistics

router = APIRouter(prefix="/statistics", tags=["statistics"])


def _group_out(db: Session, group: services.Group, *, threshold: float) -> GroupOut:
    notes = services.setting_warnings(group)
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
        curve=CurveStatsOut(**curve) if curve else None,
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
