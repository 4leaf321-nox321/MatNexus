"""곡선을 모아 겹치고 계수를 낸다 — **저장소와 계산 커널 사이.**

`matcore.viscoelastic` 은 스윕 목록만 안다. "한 시험의 어느 곡선이 온도 스윕
인가", "온도는 어느 채널에서 읽는가" 는 여기서 정한다 — `statistics` 가 같은
자리에서 같은 일을 한다.

## 온도를 대푯값 하나로 줄인다

한 스윕 안에서도 온도가 조금씩 흔들린다(실측: -40.00 · -40.05 · -40.13 …
-40.99). 장비가 온도를 잡아 두고 주파수를 훑는 동안 실제 온도가 미세하게
움직인 것이다.

**중앙값을 쓴다.** 평균은 마지막 점(-40.99)에 끌려가고, 첫 점은 아직 안정되기
전일 수 있다. 흔들림이 크면(1 K 넘게) 그 사실을 경고로 남긴다 — 그 스윕은
등온이 아니었다는 뜻이다.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.models import Curve, TestRun
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.shared import curvedata, filestore
from app.shared.errors import AppError, NotFound
from matcore import curves as curvekit
from matcore import prony as pronykit
from matcore import viscoelastic
from matcore.parsers import Channel

#: 한 스윕 안의 온도 흔들림이 이보다 크면 경고한다(K). 장비가 온도를 잡는 동안
#: 0.1 K 안팎으로 흔들리는 것은 정상이고, 1 K 를 넘으면 등온이 아니다.
TEMPERATURE_SPREAD_LIMIT = 1.0

#: 겹친 곡선의 점 수. 원래 스윕이 온도당 8점이라 넉넉히 잡아도 파일이 작다.
MASTER_POINTS = 200


def _channel(columns: dict[str, np.ndarray], *names: str) -> np.ndarray | None:
    for name in names:
        found = columns.get(name)
        if found is not None and len(found) and np.all(np.isfinite(found)):
            return found
    return None


def sweeps_of(
    db: Session, run: TestRun, curve_keys: list[str] | None = None
) -> tuple[list[viscoelastic.Sweep], list[str], list[str]]:
    """시험의 측정 곡선을 스윕으로 바꾼다. `(스윕, 쓴 곡선 키, 경고)`.

    **장비가 계산한 곡선(`derived`)은 안 쓴다.** 마스터커브에 또 마스터커브를
    씌우게 된다 — 그것을 막으려고 취입 때 갈라 둔 것이다.
    """
    available = curvedata.curves_of(db, run.id)
    if not available:
        raise NotFound(
            "MNX-VISCOELASTIC-0001",
            "정규화된 곡선이 아직 없습니다. 파일이 읽히기를 기다리세요.",
        )
    measured = [item for item in available if item.kind == "measured"]
    if curve_keys:
        wanted = set(curve_keys)
        measured = [item for item in measured if item.key in wanted]
        missing = wanted - {item.key for item in measured}
        if missing:
            raise NotFound(
                "MNX-VISCOELASTIC-0002",
                f"측정 곡선에 없는 것을 골랐습니다: {', '.join(sorted(missing))}",
            )

    sweeps: list[viscoelastic.Sweep] = []
    used: list[str] = []
    warnings: list[str] = []
    for curve in measured:
        frame, _ = curvedata.load_frame(db, run, curve.key)
        columns = frame.columns
        temperature = _channel(columns, "temperature")
        storage = _channel(columns, "storage_modulus")
        if temperature is None or storage is None:
            warnings.append(
                f"'{curve.label or curve.key}' 에 온도나 저장 탄성률이 없어 뺐습니다."
            )
            continue

        frequency = _channel(columns, "frequency")
        if frequency is None:
            angular = _channel(columns, "angular_frequency")
            if angular is None:
                warnings.append(f"'{curve.label or curve.key}' 에 주파수가 없어 뺐습니다.")
                continue
            # **각주파수만 있는 표가 실제로 있다.** 실측 파일의 첫 스윕에만
            # `Frequency` 열이 있고 나머지 여섯에는 없었다.
            frequency = angular / (2.0 * np.pi)

        spread = float(np.max(temperature) - np.min(temperature))
        if spread > TEMPERATURE_SPREAD_LIMIT:
            warnings.append(
                f"'{curve.label or curve.key}' 의 온도가 {spread:.2f} K 흔들렸습니다 — "
                f"등온 스윕이 아닐 수 있습니다. 중앙값을 썼습니다."
            )

        order = np.argsort(frequency)
        loss = _channel(columns, "loss_modulus")
        sweeps.append(
            viscoelastic.Sweep(
                temperature_k=float(np.median(temperature)),
                frequency_hz=frequency[order],
                storage_pa=storage[order],
                loss_pa=loss[order] if loss is not None else None,
            )
        )
        used.append(curve.key)

    if len(sweeps) < 2:
        raise AppError(
            "MNX-VISCOELASTIC-0003",
            f"겹칠 수 있는 온도 스윕이 {len(sweeps)}개뿐입니다. 최소 2개가 필요합니다.",
            status=422,
        )
    return sweeps, used, warnings


def build_master_curve(
    db: Session,
    run: TestRun,
    *,
    reference_temperature_k: float,
    method: str = "wlf",
    manual_shifts: dict[float, float] | None = None,
    curve_keys: list[str] | None = None,
    created_by_id: uuid.UUID | None = None,
) -> MasterCurve:
    """겹쳐서 저장한다. **커밋은 호출부가 한다.**"""
    sweeps, used, warnings = sweeps_of(db, run, curve_keys)
    try:
        curve = viscoelastic.master_curve(
            sweeps,
            reference_temperature_k=reference_temperature_k,
            method=method,
            manual_shifts=manual_shifts,
            points=MASTER_POINTS,
        )
    except viscoelastic.ViscoelasticError as exc:
        raise AppError("MNX-VISCOELASTIC-0004", str(exc), status=422) from exc

    channels = [
        Channel(
            key="frequency", label="주파수", si_unit="Hz", values=tuple(curve.frequency_hz)
        ),
        Channel(
            key="storage_modulus",
            label="저장 탄성률",
            si_unit="Pa",
            values=tuple(curve.storage_pa),
        ),
    ]
    if curve.loss_pa is not None:
        channels.append(
            Channel(
                key="loss_modulus",
                label="손실 탄성률",
                si_unit="Pa",
                values=tuple(curve.loss_pa),
            )
        )
    stored = filestore.write_bytes(
        curvekit.to_parquet(channels),
        relative_dir=f"master-curves/{run.id}",
        filename=f"{uuid.uuid4().hex}.parquet",
    )

    row = MasterCurve(
        test_run_id=run.id,
        source_curve_keys=used,
        reference_temperature_k=curve.reference_temperature_k,
        method=curve.method,
        parameters=dict(curve.parameters),
        shifts=[
            {
                "temperature_k": item.temperature_k,
                "log10_a_t": item.log10_a_t,
                "source": item.source,
                "observed_log10_a_t": item.observed_log10_a_t,
                "residual": item.residual,
                "overlap_rmse": item.overlap_rmse,
            }
            for item in curve.shifts
        ],
        notes=warnings + list(curve.notes),
        storage_path=stored.relative_path,
        point_count=len(curve.frequency_hz),
        minimum_frequency_hz=float(curve.frequency_hz[0]),
        maximum_frequency_hz=float(curve.frequency_hz[-1]),
        created_by_id=created_by_id,
    )
    db.add(row)
    db.flush()
    return row


def read_master_curve(row: MasterCurve) -> dict[str, np.ndarray]:
    raw = curvekit.read_columns(filestore.read_bytes(row.storage_path))
    return {
        name: np.asarray(
            [np.nan if value is None else float(value) for value in values], dtype=np.float64
        )
        for name, values in raw.items()
    }


def _as_dict(series: pronykit.PronySeries) -> dict[str, Any]:
    return {
        "term_count": len(series.terms),
        "equilibrium_pa": series.equilibrium_pa,
        "instantaneous_pa": series.instantaneous_pa,
        "normalized_rmse": series.normalized_rmse,
        "bic": series.bic,
        "terms": [
            {"modulus_pa": term.modulus_pa, "relaxation_time_s": term.relaxation_time_s}
            for term in series.terms
        ],
        "at_bound": list(series.at_bound),
    }


def fit_prony(
    db: Session,
    master: MasterCurve,
    *,
    terms: int | None = None,
    candidates: tuple[int, ...] = pronykit.DEFAULT_CANDIDATES,
    created_by_id: uuid.UUID | None = None,
) -> PronyFit:
    """계수를 맞춰 저장한다.

    `terms` 를 주면 그 항 수로 한 벌만, 안 주면 후보를 재고 BIC 로 고른다.
    **어느 쪽이든 재 본 것을 전부 남긴다** — 사람이 다시 고를 수 있어야 한다.
    """
    columns = read_master_curve(master)
    frequency = columns.get("frequency")
    storage = columns.get("storage_modulus")
    loss = columns.get("loss_modulus")
    if frequency is None or storage is None or loss is None:
        raise AppError(
            "MNX-VISCOELASTIC-0005",
            "마스터커브에 주파수·저장·손실이 다 있어야 Prony 를 맞출 수 있습니다. "
            "손실 탄성률이 없으면 감쇠를 정할 수 없습니다.",
            status=422,
        )

    try:
        everything: tuple[pronykit.PronySeries, ...]
        if terms is not None:
            best = pronykit.fit_prony(frequency, storage, loss, terms=terms)
            everything = (best,)
        else:
            best, everything = pronykit.choose_prony(
                frequency, storage, loss, candidates=candidates
            )
    except pronykit.PronyError as exc:
        raise AppError("MNX-VISCOELASTIC-0006", str(exc), status=422) from exc

    row = PronyFit(
        master_curve_id=master.id,
        equilibrium_pa=best.equilibrium_pa,
        terms=[
            {"modulus_pa": term.modulus_pa, "relaxation_time_s": term.relaxation_time_s}
            for term in best.terms
        ],
        normalized_rmse=best.normalized_rmse,
        bic=best.bic,
        at_bound=list(best.at_bound),
        candidates=[_as_dict(item) for item in everything],
        created_by_id=created_by_id,
    )
    db.add(row)
    db.flush()
    return row


def master_curves_of(db: Session, run_id: uuid.UUID) -> list[MasterCurve]:
    return list(
        db.scalars(
            select(MasterCurve)
            .where(MasterCurve.test_run_id == run_id)
            .order_by(MasterCurve.created_at.desc())
        )
    )


def fits_of(db: Session, master_curve_id: uuid.UUID) -> list[PronyFit]:
    return list(
        db.scalars(
            select(PronyFit)
            .where(PronyFit.master_curve_id == master_curve_id)
            .order_by(PronyFit.created_at.desc())
        )
    )


def curve_or_404(db: Session, master_curve_id: uuid.UUID) -> MasterCurve:
    found = db.get(MasterCurve, master_curve_id)
    if found is None:
        raise NotFound("MNX-VISCOELASTIC-0007", "마스터커브를 찾을 수 없습니다.")
    return found


def measured_curves(db: Session, run_id: uuid.UUID) -> list[Curve]:
    """겹칠 후보. 화면이 고를 것을 보여 주는 데 쓴다."""
    return [item for item in curvedata.curves_of(db, run_id) if item.kind == "measured"]
