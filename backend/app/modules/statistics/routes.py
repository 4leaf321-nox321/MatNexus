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
    if len(group.members) >= statistics.MIN_SAMPLES:
        x, y = services.default_axes(db, group)
        if x and y:
            curve, curve_notes = services.curve_table(db, group, x=x, y=y)
            notes.extend(curve_notes)
    if group.skipped_unadopted:
        notes.append(
            f"채택되지 않은 시험 {group.skipped_unadopted}건은 빠졌습니다. "
            f"처리한 뒤 결과 탭에서 채택하면 여기에 들어옵니다."
        )
    if len(group.members) < statistics.MIN_FOR_SPREAD:
        notes.append(
            f"시험이 {len(group.members)}건이라 변동계수와 이상치는 내지 않았습니다 "
            f"— {statistics.MIN_FOR_SPREAD}건부터 뜻이 생깁니다."
        )

    scalars = (
        services.scalar_table(group, threshold=threshold)
        if len(group.members) >= statistics.MIN_SAMPLES
        else []
    )
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
