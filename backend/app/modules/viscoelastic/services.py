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
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.tests.models import Curve, TestRun
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.shared import curvedata, filestore
from app.shared.errors import AppError, NotFound
from matcore import curves as curvekit
from matcore import processing, viscoelastic
from matcore import prony as pronykit
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
    _first_becomes_primary(db, row)
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


#: 장비가 겹쳐 준 곡선에서 찾을 열. **이름을 넓게 본다** — 장비마다 다르게 적는다.
IMPORT_FREQUENCY = ("frequency", "frequency_hz", "angular_frequency", "omega")
IMPORT_STORAGE = ("storage_modulus", "storage_pa", "e_prime", "g_prime")


def mark_primary(db: Session, curve: MasterCurve) -> MasterCurve:
    """이 곡선을 시험의 대표로 세운다. **같은 시험의 나머지는 내려온다.**

    부분 유니크(`uq_master_curves_primary`)가 DB 에서도 하나만 남게 하지만,
    거기 걸리면 사람에게는 그냥 오류다 — 여기서 먼저 내린다.
    """
    db.execute(
        update(MasterCurve)
        .where(
            MasterCurve.test_run_id == curve.test_run_id,
            MasterCurve.id != curve.id,
            MasterCurve.is_primary.is_(True),
        )
        .values(is_primary=False)
    )
    # **비우는 것이 먼저다.** 세우고 내리면 그 사이에 대표가 둘이라 유니크가 문다.
    db.flush()
    curve.is_primary = True
    db.flush()
    return curve


def _first_becomes_primary(db: Session, curve: MasterCurve) -> None:
    """첫 곡선은 만들면서 대표가 된다.

    고를 것이 하나뿐인데 고르라고 하면 그것은 일이 아니라 절차다. 둘째부터는
    사람이 옮긴다 — 새로 만든 것이 자동으로 대표가 되면 「최근 것이 대표」 라는
    옛 동작이 이름만 바꿔 그대로 남는다.
    """
    exists = db.scalar(
        select(func.count())
        .select_from(MasterCurve)
        .where(
            MasterCurve.test_run_id == curve.test_run_id,
            MasterCurve.id != curve.id,
            MasterCurve.is_primary.is_(True),
        )
    )
    if not exists:
        curve.is_primary = True
        db.flush()


def importable_curves(db: Session, run_id: uuid.UUID) -> list[dict[str, object]]:
    """장비가 계산해 준 곡선 목록. **쓸 수 없는 것도 이유와 함께 돌려준다.**

    `derived` 에는 마스터커브만 있는 것이 아니다 — 이동인자 표(`TTS - shift
    factors`)도 같은 칸에 들어온다. 그것을 목록에서 빼 버리면 「내 파일에 있는
    그 표가 왜 안 보이지」 가 되고, 그냥 두면 골라 놓고 나서야 거절을 본다.
    **둘 다 보이되 왜 못 쓰는지 적는다.**

    채널 이름은 `Curve` 행에 이미 있다 — 이것을 보려고 Parquet 를 열지 않는다.
    """
    found: list[dict[str, object]] = []
    for curve in curvedata.curves_of(db, run_id):
        if curve.kind != "derived":
            continue
        channels = list(curve.channels or [])
        missing = [
            label
            for label, names in (("주파수", IMPORT_FREQUENCY), ("저장 탄성률", IMPORT_STORAGE))
            if not any(name in channels for name in names)
        ]
        present = ", ".join(channels) or "없음"
        found.append(
            {
                "curve_key": curve.key,
                "label": curve.label,
                "row_count": curve.row_count,
                "channels": channels,
                "usable": not missing,
                "note": (
                    None
                    if not missing
                    else f"{' · '.join(missing)} 열이 없습니다. 있는 열: {present}"
                ),
            }
        )
    return found


def import_master_curve(
    db: Session,
    run: TestRun,
    *,
    curve_key: str,
    reference_temperature_k: float,
    created_by_id: uuid.UUID | None = None,
) -> MasterCurve:
    """**장비가 이미 겹쳐 준 곡선**을 마스터커브로 등록한다.

    TA TRIOS 같은 장비는 시간-온도 중첩을 제 소프트웨어에서 하고 마스터커브를
    함께 내보낸다. 그 표는 프로파일이 `derived` 로 읽어 두지만(버리지 않는다),
    **`MasterCurve` 행이 되지는 않았다** — 만드는 길이 「온도별 스윕을 겹친다」
    하나뿐이었기 때문이다. 그래서 그런 파일은 Prony 도 글로벌 피팅도 못 썼다.

    ## 겹치기를 다시 하지 않는다

    장비가 쓴 이동인자를 우리는 모른다. 다시 겹치면 **다른 곡선이 나오는데 둘 다
    그럴듯하다.** 그래서 점을 그대로 받고 `method="imported"` 로 적는다 —
    이동인자 자리는 비어 있고, 그 사실이 화면과 카드에 남는다.

    ## 기준 온도는 사람이 준다

    표 이름에 적혀 있는 일이 많지만(`TTS - master curve (20.0 °C)`) 장비마다 다르고,
    **틀린 온도로 등록하면 그 덱은 조용히 다른 온도의 해석에 쓰인다.** 짐작하지
    않는다.
    """
    frame, curve = curvedata.load_frame(db, run, curve_key)
    frequency = _first_column(frame, IMPORT_FREQUENCY)
    storage = _first_column(frame, IMPORT_STORAGE)
    if frequency is None or storage is None:
        raise AppError(
            "MNX-VISCOELASTIC-0007",
            f"'{curve.label or curve_key}' 에서 주파수와 저장 탄성률 열을 못 찾았습니다. "
            f"있는 열: {', '.join(frame.columns)}. "
            f"장비 파일 정의에서 그 두 열을 매핑해 주세요.",
            status=422,
        )

    order = np.argsort(frequency)
    frequency, storage = frequency[order], storage[order]
    channels = [
        Channel(key="frequency", label="주파수", si_unit="Hz", values=tuple(frequency)),
        Channel(
            key="storage_modulus",
            label="저장 탄성률",
            si_unit="Pa",
            values=tuple(storage),
        ),
    ]
    stored = filestore.write_bytes(
        curvekit.to_parquet(channels),
        relative_dir=f"master-curves/{run.id}",
        filename=f"{uuid.uuid4().hex}.parquet",
    )

    row = MasterCurve(
        test_run_id=run.id,
        source_curve_keys=[curve_key],
        reference_temperature_k=reference_temperature_k,
        method="imported",
        parameters={},
        # **이동인자를 안 지어낸다.** 장비가 무엇으로 겹쳤는지 모른다.
        shifts=[],
        notes=[
            "장비가 겹친 곡선을 그대로 받았습니다 — 이동인자는 이 시스템이 모릅니다.",
            f"기준 온도 {reference_temperature_k - 273.15:.1f} °C 는 사람이 적은 값입니다.",
        ],
        storage_path=stored.relative_path,
        point_count=len(frequency),
        minimum_frequency_hz=float(frequency[0]),
        maximum_frequency_hz=float(frequency[-1]),
        created_by_id=created_by_id,
    )
    db.add(row)
    db.flush()
    _first_becomes_primary(db, row)
    return row


def _first_column(frame: processing.Frame, names: tuple[str, ...]) -> np.ndarray | None:
    """**이름을 넓게 본다** — 장비마다 `storage_modulus`·`e_prime` 으로 다르게 적는다."""
    for name in names:
        if name in frame.columns:
            return np.asarray(frame.columns[name], dtype=float)
    return None
