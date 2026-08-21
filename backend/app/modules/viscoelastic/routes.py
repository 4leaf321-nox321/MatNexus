"""점탄성 — 마스터커브와 Prony 적합.

## 왜 처리 라우트가 아닌가

처리는 곡선 하나를 받아 곡선 하나를 낸다. 마스터커브는 **온도가 다른 곡선
여섯을 받아 하나를 낸다** — 파이프라인의 규약을 통째로 넓히지 않으려고 따로
둔다(`models.py` 에 적었다).

## 만들고 나면 안 고친다

기준 온도를 바꾸고 싶으면 새로 만든다. 같은 행을 고치면 그 계수로 이미 내보낸
카드가 무엇에서 나왔는지 알 수 없게 된다(ADR 0007 과 같은 판단).
"""

from __future__ import annotations

import uuid

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.viscoelastic import services
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.modules.viscoelastic.schemas import (
    MasterCurveOut,
    MasterCurveRequest,
    PronyFitOut,
    PronyRequest,
    ShiftOut,
    SweepListOut,
    SweepOut,
)
from app.shared.auth import current_user
from app.shared.errors import AppError
from app.shared.permissions import get_run

router = APIRouter(prefix="/viscoelastic", tags=["viscoelastic"])


def _curve_out(row: MasterCurve) -> MasterCurveOut:
    return MasterCurveOut(
        id=row.id,
        test_run_id=row.test_run_id,
        source_curve_keys=list(row.source_curve_keys),
        reference_temperature_k=row.reference_temperature_k,
        method=row.method,
        parameters=dict(row.parameters),
        shifts=[ShiftOut(**item) for item in row.shifts],
        notes=list(row.notes),
        point_count=row.point_count,
        minimum_frequency_hz=row.minimum_frequency_hz,
        maximum_frequency_hz=row.maximum_frequency_hz,
        created_at=row.created_at,
    )


def _fit_out(row: PronyFit) -> PronyFitOut:
    return PronyFitOut(
        id=row.id,
        master_curve_id=row.master_curve_id,
        equilibrium_pa=row.equilibrium_pa,
        instantaneous_pa=row.equilibrium_pa
        + sum(float(term["modulus_pa"]) for term in row.terms),
        terms=[dict(term) for term in row.terms],  # type: ignore[misc]
        normalized_rmse=row.normalized_rmse,
        bic=row.bic,
        at_bound=list(row.at_bound),
        candidates=[dict(item) for item in row.candidates],  # type: ignore[misc]
        created_at=row.created_at,
    )


@router.get("/runs/{test_run_id}/sweeps", response_model=SweepListOut)
def list_sweeps(
    test_run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SweepListOut:
    """겹칠 후보. **화면이 온도를 보고 기준을 고른다.**

    기준 온도는 잰 온도 중에 있어야 하므로, 무엇이 있는지 먼저 보여 준다 —
    입력칸에 숫자를 치게 두면 없는 온도를 적고 나서 오류를 본다.
    """
    run = get_run(db, user, test_run_id)
    sweeps, used, warnings = services.sweeps_of(db, run)
    labels = {item.key: item.label for item in services.measured_curves(db, run.id)}
    return SweepListOut(
        items=[
            SweepOut(
                curve_key=key,
                label=labels.get(key),
                temperature_k=sweep.temperature_k,
                point_count=len(sweep.frequency_hz),
                minimum_frequency_hz=float(sweep.frequency_hz[0]),
                maximum_frequency_hz=float(sweep.frequency_hz[-1]),
            )
            for key, sweep in zip(used, sweeps, strict=True)
        ],
        warnings=warnings,
    )


@router.get("/runs/{test_run_id}/master-curves", response_model=list[MasterCurveOut])
def list_master_curves(
    test_run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[MasterCurveOut]:
    run = get_run(db, user, test_run_id)
    return [_curve_out(item) for item in services.master_curves_of(db, run.id)]


@router.post(
    "/runs/{test_run_id}/master-curves", response_model=MasterCurveOut, status_code=201
)
def create_master_curve(
    test_run_id: uuid.UUID,
    payload: MasterCurveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MasterCurveOut:
    """온도 스윕들을 기준 온도로 겹친다.

    `manual` 은 사람(또는 장비)이 준 이동인자를 그대로 쓴다. `wlf`·`arrhenius`
    는 **실제로 겹쳐 본 값을 목표로** 모델을 맞추고, 관측값도 함께 남긴다 —
    둘이 벌어지면 그 모델이 이 재료에 안 맞는다는 뜻이다.
    """
    run = get_run(db, user, test_run_id)
    shifts: dict[float, float] | None = None
    if payload.manual_shifts is not None:
        try:
            shifts = {float(key): value for key, value in payload.manual_shifts.items()}
        except ValueError as exc:
            raise AppError(
                "MNX-VISCOELASTIC-0008",
                "이동인자의 온도 키가 숫자가 아닙니다.",
                status=422,
            ) from exc

    row = services.build_master_curve(
        db,
        run,
        reference_temperature_k=payload.reference_temperature_k,
        method=payload.method,
        manual_shifts=shifts,
        curve_keys=payload.curve_keys,
        created_by_id=user.id,
    )
    db.commit()
    db.refresh(row)
    return _curve_out(row)


@router.get("/master-curves/{master_curve_id}/points")
def master_curve_points(
    master_curve_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, list[float | None]]:
    """겹친 곡선의 점. 화면이 그린다."""
    row = services.curve_or_404(db, master_curve_id)
    get_run(db, user, row.test_run_id)  # 볼 권한이 있는가
    columns = services.read_master_curve(row)
    return {
        name: [None if not np.isfinite(value) else float(value) for value in values]
        for name, values in columns.items()
    }


@router.get("/master-curves/{master_curve_id}/prony", response_model=list[PronyFitOut])
def list_prony_fits(
    master_curve_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PronyFitOut]:
    row = services.curve_or_404(db, master_curve_id)
    get_run(db, user, row.test_run_id)
    return [_fit_out(item) for item in services.fits_of(db, row.id)]


@router.post(
    "/master-curves/{master_curve_id}/prony", response_model=PronyFitOut, status_code=201
)
def create_prony_fit(
    master_curve_id: uuid.UUID,
    payload: PronyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PronyFitOut:
    """일반화 Maxwell 계수를 맞춘다.

    항 수를 안 주면 후보를 재고 BIC 로 고른다. **재 본 것을 전부 남긴다** —
    "3항이면 충분한데 왜 6항이지" 를 사람이 볼 수 있어야 한다.
    """
    row = services.curve_or_404(db, master_curve_id)
    run = get_run(db, user, row.test_run_id)
    assert run is not None
    fit = services.fit_prony(db, row, terms=payload.terms, created_by_id=user.id)
    db.commit()
    db.refresh(fit)
    return _fit_out(fit)
