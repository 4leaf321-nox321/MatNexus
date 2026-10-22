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
from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.modules.materials.models import Sample, Specimen
from app.modules.tests.models import Curve, TestRun
from app.modules.viscoelastic.models import MasterCurve, ModulusTable, PronyFit
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
) -> tuple[list[viscoelastic.Sweep], list[str], list[str], str]:
    """시험의 측정 곡선을 스윕으로 바꾼다. `(스윕, 쓴 곡선 키, 경고, 탄성률 기준 E|G)`.

    **장비가 계산한 곡선(`derived`)은 안 쓴다.** 마스터커브에 또 마스터커브를
    씌우게 된다 — 그것을 막으려고 취입 때 갈라 둔 것이다.

    **저장 탄성률은 E′ 채널이든 G′ 채널이든 받는다**(2026-10-20, `MODULUS_PAIRS`). 한 시험에
    둘이 섞이면 막는다 — E 와 G 를 한 곡선으로 겹치면 어느 쪽도 아니다.
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
    bases: set[str] = set()
    for curve in measured:
        frame, _ = curvedata.load_frame(db, run, curve.key)
        columns = frame.columns
        temperature = _channel(columns, "temperature")
        storage = loss = None
        basis = ""
        for storage_key, loss_key, kind in viscoelastic.MODULUS_PAIRS:
            storage = _channel(columns, storage_key)
            if storage is not None:
                loss = _channel(columns, loss_key)
                basis = kind
                break
        if temperature is None or storage is None:
            warnings.append(
                f"'{curve.label or curve.key}' 에 온도나 저장 탄성률(E′ 또는 G′)이 없어 "
                "뺐습니다."
            )
            continue
        bases.add(basis)

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
        sweeps.append(
            viscoelastic.Sweep(
                temperature_k=float(np.median(temperature)),
                frequency_hz=frequency[order],
                storage_pa=storage[order],
                loss_pa=loss[order] if loss is not None else None,
            )
        )
        used.append(curve.key)

    if len(bases) > 1:
        raise AppError(
            "MNX-VISCOELASTIC-0010",
            "한 시험에 E′(인장 · 굽힘) 곡선과 G′(전단) 곡선이 섞여 있습니다 — 둘을 겹치면 "
            "어느 쪽도 아닙니다. 형식 정의의 열 매핑을 확인하세요.",
            status=422,
        )
    if len(sweeps) < 2:
        # **왜 빠졌는지를 함께 말한다**(2026-10-20) — 전에는 곡선마다 모은 까닭을 버리고
        # 「0개」 만 말해, 채널 이름이 틀린 것인지 온도가 없는 것인지 화면에서 알 수 없었다.
        reasons = " ".join(warnings[:3])
        raise AppError(
            "MNX-VISCOELASTIC-0003",
            f"겹칠 수 있는 온도 스윕이 {len(sweeps)}개뿐입니다. 최소 2개가 필요합니다."
            + (f" {reasons}" if reasons else ""),
            status=422,
        )
    basis = bases.pop() if bases else "E"
    if basis == "G":
        warnings.append(
            "전단 채널(G′ · G″)로 잰 곡선입니다 — 카드에 담을 때 E = 2(1+ν)G 로 옮겨 담고, "
            "덱이 같은 ν 로 G 를 다시 만듭니다(ADR 0057)."
        )
    return sweeps, used, warnings, basis


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
    sweeps, used, warnings, basis = sweeps_of(db, run, curve_keys)
    shear = basis == "G"
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
        # 키는 E/G 와 무관하게 같다 — 마스터커브를 읽는 쪽(Prony · 묶음)이 한 이름으로 읽는다.
        # 무엇을 잰 것인지는 이름표와 기록(`notes`)이 말한다.
        Channel(
            key="storage_modulus",
            label="저장 전단 탄성률 G′" if shear else "저장 탄성률",
            si_unit="Pa",
            values=tuple(curve.storage_pa),
        ),
    ]
    if curve.loss_pa is not None:
        channels.append(
            Channel(
                key="loss_modulus",
                label="손실 전단 탄성률 G″" if shear else "손실 탄성률",
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
IMPORT_FREQUENCY = ("frequency", "frequency_hz")
#: 각주파수(rad/s) 열 — **Hz 가 아니다.** 주파수 열이 없을 때만 쓰고 2π 로 나눈다(2026-10-04).
#: 전에는 위 목록에 섞여 있어 그대로 Hz 로 저장됐고, Prony 완화시간이 2π 배 짧게 나왔다
#: (측정 스윕 쪽 `sweeps_of` 는 이미 나누고 있었다).
IMPORT_ANGULAR = ("angular_frequency", "omega")
#: 전단 채널(`shear_…`)도 받는다(2026-10-20). 무엇을 잰 것인지는 시험 종류의 채널이 말한다 —
#: 카드가 그것으로 E 로 옮긴다(`curvedata.measures_shear_channels`).
IMPORT_STORAGE = (
    "storage_modulus",
    "storage_pa",
    "e_prime",
    "g_prime",
    "shear_storage_modulus",
)
#: 손실 탄성률. **없어도 받지만, 있으면 반드시 함께 담는다.**
#:
#: 묶음 Prony 는 저장·손실을 함께 맞춘다 — 손실이 없는 마스터커브는 글로벌 피팅에서
#: 거절된다(`MNX-GROUPING-0006`). 가져온 곡선이 그 자리에서 막히면 「가져오기는
#: 됐는데 묶이지가 않는다」 가 되고, 원인이 곡선 안에 있어 화면에서 안 보인다
#: (실측 2026-08-31: 자동 등록을 켜자 묶음 시험 여섯이 이 오류로 떨어졌다).
IMPORT_LOSS = (
    "loss_modulus",
    "loss_pa",
    "e_double_prime",
    "g_double_prime",
    "shear_loss_modulus",
)


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

    **그 시험의 첫 곡선일 때만**(2026-10-22). 「다른 대표가 없으면」 으로 두면, 사람이 대표를
    해제해 둔 시험에서 새로 만든 곡선이 저절로 대표가 된다 — 해제가 안 지켜진다.
    """
    exists = db.scalar(
        select(func.count())
        .select_from(MasterCurve)
        .where(
            MasterCurve.test_run_id == curve.test_run_id,
            MasterCurve.id != curve.id,
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
            for label, names in (
                ("주파수", IMPORT_FREQUENCY + IMPORT_ANGULAR),
                ("저장 탄성률", IMPORT_STORAGE),
            )
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
    if frequency is None:
        angular = _first_column(frame, IMPORT_ANGULAR)
        frequency = angular / (2.0 * np.pi) if angular is not None else None
    storage = _first_column(frame, IMPORT_STORAGE)
    loss = _first_column(frame, IMPORT_LOSS)
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
    if loss is not None:
        # **있으면 함께 담는다.** 없다고 지어내지는 않는다 — 손실이 없는 표는
        # 그대로 받고, 그 곡선으로 글로벌 피팅을 하려 할 때 그쪽이 이유를 말한다.
        channels.append(
            Channel(
                key="loss_modulus",
                label="손실 탄성률",
                si_unit="Pa",
                values=tuple(loss[order]),
            )
        )
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


# ── 주파수 하나에서 본 온도별 탄성률 표 (2026-10-22) ──────────────────────────────


def segments_of(
    db: Session, run: TestRun
) -> tuple[list[viscoelastic.Segment], list[str], list[str], str]:
    """측정 곡선 → 구간. `(구간, 쓴 곡선 키, 경고, 탄성률 기준 E|G)`.

    `sweeps_of` 와 같은 채널 규칙(온도 · 주파수 또는 각주파수 · E′ 또는 G′)이지만 **온도를
    중앙값 하나로 줄이지 않는다** — 램프 곡선은 점마다 온도가 다르다. 곡선 하나여도 된다.
    """
    available = curvedata.curves_of(db, run.id)
    if not available:
        raise NotFound(
            "MNX-VISCOELASTIC-0001",
            "정규화된 곡선이 아직 없습니다. 파일이 읽히기를 기다리세요.",
        )
    segments: list[viscoelastic.Segment] = []
    used: list[str] = []
    warnings: list[str] = []
    bases: set[str] = set()
    for curve in (item for item in available if item.kind == "measured"):
        frame, _ = curvedata.load_frame(db, run, curve.key)
        columns = frame.columns
        name = curve.label or curve.key
        temperature = _channel(columns, "temperature")
        storage = loss = None
        basis = ""
        for storage_key, loss_key, kind in viscoelastic.MODULUS_PAIRS:
            storage = _channel(columns, storage_key)
            if storage is not None:
                loss = _channel(columns, loss_key)
                basis = kind
                break
        if temperature is None or storage is None:
            warnings.append(f"'{name}' 에 온도나 저장 탄성률(E′ 또는 G′)이 없어 뺐습니다.")
            continue
        frequency = _channel(columns, "frequency")
        if frequency is None:
            angular = _channel(columns, "angular_frequency")
            if angular is None:
                warnings.append(f"'{name}' 에 주파수가 없어 뺐습니다.")
                continue
            frequency = angular / (2.0 * np.pi)
        bases.add(basis)
        segments.append(
            viscoelastic.Segment(
                label=name,
                temperature_k=temperature,
                frequency_hz=frequency,
                storage_pa=storage,
                loss_pa=loss,
            )
        )
        used.append(curve.key)
    if len(bases) > 1:
        raise AppError(
            "MNX-VISCOELASTIC-0010",
            "한 시험에 E′(인장 · 굽힘) 곡선과 G′(전단) 곡선이 섞여 있습니다 — 한 표로 묶으면 "
            "어느 쪽도 아닙니다. 형식 정의의 열 매핑을 확인하세요.",
            status=422,
        )
    return segments, used, warnings, (bases.pop() if bases else "E")


def build_modulus_table(
    db: Session, run: TestRun, frequency_hz: float, *, created_by_id: uuid.UUID | None
) -> ModulusTable:
    """고른 주파수에서 온도별 E′ · E″ · tan δ 표를 만든다. **줄이 하나도 없으면 까닭을
    댄다.**"""
    segments, used, warnings, basis = segments_of(db, run)
    if not segments:
        raise AppError(
            "MNX-VISCOELASTIC-0015",
            "온도 · 주파수 · 저장 탄성률이 함께 있는 측정 곡선이 없습니다. "
            + " ".join(warnings[:3]),
            status=422,
        )
    try:
        rows, notes = viscoelastic.modulus_table(segments, frequency_hz)
    except viscoelastic.ViscoelasticError as exc:
        raise AppError("MNX-VISCOELASTIC-0015", str(exc), status=422) from exc
    if not rows:
        raise AppError(
            "MNX-VISCOELASTIC-0016",
            f"{frequency_hz:g} Hz 에서 낸 온도가 하나도 없습니다. " + " ".join(notes[:3]),
            status=422,
        )
    table = ModulusTable(
        test_run_id=run.id,
        frequency_hz=float(frequency_hz),
        modulus_basis=basis,
        rows=[
            {
                "temperature_k": one.temperature_k,
                "storage_pa": one.storage_pa,
                "loss_pa": one.loss_pa,
                "tan_delta": one.tan_delta,
            }
            for one in rows
        ],
        source_curve_keys=used,
        notes=[*warnings, *notes],
        created_by_id=created_by_id,
    )
    db.add(table)
    db.flush()
    return table


def modulus_tables_of(db: Session, run_id: uuid.UUID) -> list[ModulusTable]:
    return list(
        db.scalars(
            select(ModulusTable)
            .where(ModulusTable.test_run_id == run_id)
            .order_by(ModulusTable.created_at.desc())
        )
    )


def table_or_404(db: Session, table_id: uuid.UUID) -> ModulusTable:
    row = db.get(ModulusTable, table_id)
    if row is None:
        raise NotFound("MNX-VISCOELASTIC-0017", "온도별 탄성률 표를 찾을 수 없습니다.")
    return row


#: 같이 평균할 표를 몇 개까지 내놓나. 한 재료 · 한 방향의 DMA 가 이보다 많으면 화면에서
#: 고르기 어렵다.
COMPANION_LIMIT = 50


def companion_tables(
    db: Session, table: ModulusTable, visible: Select[tuple[TestRun]]
) -> list[tuple[ModulusTable, TestRun, Specimen]]:
    """**시편 평균에 같이 넣을 수 있는 표** — 같은 재료 · 시험 종류 · 방향 · 잰 것(E/G) ·
    주파수인 **다른 시험**의 표.

    시험마다 가장 최근 표 하나다 — 같은 주파수로 두 번 만든 표를 둘로 세면 평균이 그 시편
    쪽으로 기운다. 카드 만들기(`fitting` 의 온도별 카드)가 같은 조건을 다시 본다.
    """
    run = db.get(TestRun, table.test_run_id)
    specimen = db.get(Specimen, run.specimen_id) if run else None
    sample = db.get(Sample, specimen.sample_id) if specimen else None
    if run is None or specimen is None or sample is None:
        return []
    rows = db.execute(
        select(ModulusTable, TestRun, Specimen)
        .join(TestRun, TestRun.id == ModulusTable.test_run_id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(
            Sample.material_id == sample.material_id,
            TestRun.test_type_id == run.test_type_id,
            Specimen.orientation == specimen.orientation,
            Specimen.deleted_at.is_(None),
            ModulusTable.modulus_basis == table.modulus_basis,
            ModulusTable.frequency_hz.between(
                table.frequency_hz * (1 - 1e-6), table.frequency_hz * (1 + 1e-6)
            ),
            ModulusTable.test_run_id != run.id,
            TestRun.id.in_(visible.with_only_columns(TestRun.id)),
        )
        .order_by(ModulusTable.created_at.desc())
        .limit(COMPANION_LIMIT * 4)
    ).all()
    latest: dict[uuid.UUID, tuple[ModulusTable, TestRun, Specimen]] = {}
    for found, found_run, found_specimen in rows:
        latest.setdefault(found_run.id, (found, found_run, found_specimen))
    return sorted(latest.values(), key=lambda one: one[1].record_name)[:COMPANION_LIMIT]
