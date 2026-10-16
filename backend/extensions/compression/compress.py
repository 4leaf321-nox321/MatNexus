"""압축 시험 — 고무 · 폼 · 플라스틱의 압축 응력-변형률 · 탄성률 · 지표(2026-10-16).

    고무   ISO 7743 · ASTM D575 · JIS K 6254   몇 % 압축에서의 응력, 할선 탄성률, 반복(Mullins)
    폼     ISO 3386 · ASTM D3574(연질)          40% 압축 응력(CV40) · 25/50/65% 하중(CFD),
                                                4번째 사이클
           ISO 844 · ASTM D1621(경질)           10% 압축 응력 또는 그 전의 최대 응력,
                                                압축 탄성률
           ISO 13314(다공질 금속 · 폼 일반)     평탄 응력 · 치밀화 변형률 · 흡수 에너지
    플라스틱 ISO 604 · ASTM D695               압축 탄성률(현 0.05~0.25%) · 압축 강도

## 부호와 열

장비는 압축을 음수로 적기도 하고 양수로 적기도 한다. 여기서는 **압축량을 양수로** 쓴다
(`compressive_strain` · `compressive_stress`) — 대표 곡선 · 통계가 오름차순 변형률을 전제하므로
그대로 쓸 수 있다. 인장과 같은 부호(음수)가 필요한 초탄성 적합은 이 열에서 따로 옮긴다.

## 접촉점 · 사이클

시편에 닿기 전 구간(하중이 거의 0)을 버리고 그 자리를 변위 0 으로 둔다 — 인장의 토우 보정과
같은 일이다. 고무 · 폼은 처음 몇 번 누르면 부드러워진다(Mullins). 규격이 「4번째 사이클」(ISO
3386) · 「세 번째」(D3574 C) 처럼 정하므로 **하중 구간을 골라 쓴다**.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore import slopes
from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_float

FORCE = "force"
DISPLACEMENT = "displacement"
STRAIN_CHANNEL = "strain"

STRAIN = "compressive_strain"
STRESS = "compressive_stress"

#: 고정 변형률에서의 응력 — 규격이 보고하는 자리(키, 변형률, 이름).
STRAIN_POINTS: tuple[tuple[str, float, str], ...] = (
    ("compressive_stress_at_10pct", 0.10, "10% 압축 응력"),
    ("compressive_stress_at_20pct", 0.20, "20% 압축 응력"),
    ("compressive_stress_at_25pct", 0.25, "25% 압축 응력"),
    ("compressive_stress_at_40pct", 0.40, "40% 압축 응력(CV40)"),
    ("compressive_stress_at_50pct", 0.50, "50% 압축 응력"),
    ("compressive_stress_at_65pct", 0.65, "65% 압축 응력"),
)

#: 사이클을 가르는 되돌림의 크기 — 최대 변형의 이 비율 넘게 줄면 내리는 구간으로 본다.
CYCLE_DROP = 0.02


def _flip_needed(force: np.ndarray) -> bool:
    """압축이 음수로 적혀 있나 — 큰 값의 부호로 본다(작은 잡음에 흔들리지 않게)."""
    if len(force) == 0:
        return False
    return abs(float(np.min(force))) > abs(float(np.max(force)))


def loading_segments(strain: np.ndarray) -> list[tuple[int, int]]:
    """변형이 **늘어나는** 구간들 [시작, 끝). 내리는 구간은 뺀다."""
    if len(strain) < 2:
        return [(0, len(strain))]
    span = float(np.max(strain) - np.min(strain)) or 1.0
    segments: list[tuple[int, int]] = []
    start = 0
    peak = low = float(strain[0])
    peak_at = low_at = 0
    falling = False
    for index in range(1, len(strain)):
        value = float(strain[index])
        if not falling:
            if value >= peak:
                peak, peak_at = value, index
            elif peak - value > CYCLE_DROP * span:
                segments.append((start, peak_at + 1))
                falling = True
                low, low_at = value, index
        else:
            if value <= low:
                low, low_at = value, index
            elif value - low > CYCLE_DROP * span:
                start = low_at
                peak, peak_at = value, index
                falling = False
    if not falling:
        segments.append((start, peak_at + 1))
    return [one for one in segments if one[1] - one[0] >= 2]


def engineering(frame: Frame, options: dict[str, Any]) -> StepResult:
    """하중 · 변위(또는 변형률) → 압축 응력 · 변형률(양수). 접촉점 · 사이클 선택."""
    height = option_float(options, "height")
    area = option_float(options, "area")
    if height <= 0:
        raise ProcessingError(f"초기 높이가 0 이하입니다: {height} m")
    if area <= 0:
        raise ProcessingError(f"단면적이 0 이하입니다: {area} m²")

    force_key = str(options.get("force") or FORCE)
    force = np.asarray(frame.require(force_key, what="하중"), dtype=np.float64)
    source = str(options.get("source") or "auto")
    if source == "auto":
        source = "strain" if STRAIN_CHANNEL in frame.columns else "displacement"
    if source == "strain":
        strain = np.asarray(frame.require(STRAIN_CHANNEL, what="변형률"), dtype=np.float64)
        if frame.units.get(STRAIN_CHANNEL) not in (None, "1"):
            raise ProcessingError("변형률 열은 무차원이어야 합니다.")
    else:
        displacement = np.asarray(frame.require(DISPLACEMENT, what="변위"), dtype=np.float64)
        if frame.units.get(DISPLACEMENT) not in (None, "m"):
            raise ProcessingError("변위 열은 m 여야 합니다.")
        strain = displacement / height

    notes: list[str] = []
    sign = str(options.get("sign") or "auto")
    flip = _flip_needed(force) if sign == "auto" else sign == "flip"
    if flip:
        force = -force
        strain = -strain
        notes.append("압축이 음수로 적혀 있어 하중 · 변형의 부호를 뒤집었습니다.")

    # 접촉점 — 하중이 문턱을 처음 넘는 곳. 그 앞은 버리고 그 자리를 변형 0 으로.
    contact = options.get("contact_force")
    threshold = (
        float(contact) if contact not in (None, "") else 0.005 * float(np.max(force) or 0.0)
    )
    above = np.flatnonzero(force >= threshold)
    if len(above) == 0:
        raise ProcessingError("하중이 접촉 문턱을 한 번도 넘지 않습니다 — 압축 시험이 맞나요?")
    # 문턱을 넘은 첫 점이 아니라 **그 직전에 하중이 거의 0 이던 마지막 점**이 닿은 자리다 —
    # 문턱 점을 0 으로 두면 깨끗한 곡선에서도 변형률이 문턱만큼 밀려 할선 탄성률이 커진다.
    quiet = np.flatnonzero(force[: int(above[0])] <= 0.1 * threshold)
    first = int(quiet[-1]) if len(quiet) else int(above[0])
    if first > 0:
        notes.append(
            f"접촉 전 {first}점(하중 {threshold:.4g} N 미만)을 버리고 "
            "그 자리를 변형 0 으로 뒀습니다."
        )
    force = force[first:]
    strain = strain[first:] - strain[first]
    kept = Frame(
        {key: np.asarray(value)[first:] for key, value in frame.columns.items()},
        dict(frame.units),
    )

    segments = loading_segments(strain)
    cycle = int(options.get("cycle") or 0)
    if cycle < 0:
        raise ProcessingError("사이클 번호는 0(자동) 이상이어야 합니다.")
    if cycle > len(segments):
        raise ProcessingError(f"하중 구간이 {len(segments)}개뿐인데 {cycle}번째를 골랐습니다.")
    if len(segments) > 1 or cycle:
        chosen = cycle or len(segments)
        start, end = segments[chosen - 1]
        notes.append(
            f"하중 구간 {len(segments)}개 중 {chosen}번째를 썼습니다"
            + (" (자동: 마지막)." if not cycle else ".")
        )
        force, strain = force[start:end], strain[start:end]
        kept = kept.select(np.arange(start, end))
        if start > 0:
            # 앞 사이클의 영구 변형을 남긴 채 쓴다 — 규격이 그 사이클을 정했으면 그 상태가
            # 뜻이다.
            notes.append(f"그 구간은 변형 {strain[0]:.4g} 에서 시작합니다(앞 사이클의 잔류).")

    used = STRAIN_CHANNEL if source == "strain" else DISPLACEMENT
    notes.insert(
        0,
        f"초기 높이 {height * 1e3:.4g} mm, 단면적 {area * 1e6:.4g} mm² 로 압축 응력 · 변형률"
        f"(양수)을 냈습니다 — 변형은 '{used}' 에서.",
    )
    return StepResult(
        kept.with_columns({STRAIN: strain, STRESS: force / area}, {STRAIN: "1", STRESS: "Pa"}),
        notes=tuple(notes),
        scalars=(
            Scalar(
                key="loading_cycle_count",
                label="하중 구간 수",
                value=float(len(segments)),
                si_unit="1",
                dimension="dimensionless",
            ),
        ),
    )


def modulus(frame: Frame, options: dict[str, Any]) -> StepResult:
    """압축 탄성률 — 고른 방법 · 구간. 못 내면 까닭만 남긴다."""
    strain = frame.require(str(options.get("strain") or STRAIN), what="압축 변형률")
    stress = frame.require(str(options.get("stress") or STRESS), what="압축 응력")
    method = str(options.get("method") or "secant")
    try:
        found = slopes.measure(
            strain,
            stress,
            method=method,
            low=float(options.get("minimum_strain", 0.0005)),
            high=float(options.get("maximum_strain", 0.1)),
            band_low=float(options.get("band_low", 0.1)),
            band_high=float(options.get("band_high", 0.4)),
            tangent_width=float(options.get("tangent_width", 0.001)),
        )
    except slopes.SlopeError as exc:
        return StepResult(frame, notes=(f"압축 탄성률을 내지 않았습니다 — {exc}",))
    if found.value <= 0:
        return StepResult(frame, notes=("기울기가 0 이하라 압축 탄성률을 내지 않았습니다.",))
    scalars = [
        Scalar(
            key="compressive_modulus",
            label="압축 탄성률",
            value=found.value,
            si_unit="Pa",
            dimension="stress",
        )
    ]
    if found.r2 is not None:
        scalars.append(
            Scalar(
                key="compressive_modulus_r2",
                label="압축 탄성률 회귀 R²",
                value=found.r2,
                si_unit="1",
                dimension="dimensionless",
            )
        )
    return StepResult(
        frame,
        notes=(
            f"{method} 방법, 변형률 {found.low:.4g} ~ {found.high:.4g}"
            f"(점 {found.points}개)에서 "
            f"압축 탄성률 {found.value / 1e6:.4g} MPa.",
        ),
        scalars=tuple(scalars),
    )


def indices(frame: Frame, options: dict[str, Any]) -> StepResult:
    """규격이 보고하는 지표 — 고정 변형률의 응력, 압축 강도, 폼의 평탄 응력 · 치밀화 ·
    흡수 에너지.

    **곡선이 닿은 자리만 낸다** — 50% 까지 누른 시험에서 65% 응력을 지어내지 않는다.
    """
    strain = np.asarray(
        frame.require(str(options.get("strain") or STRAIN), what="압축 변형률")
    )
    stress = np.asarray(frame.require(str(options.get("stress") or STRESS), what="압축 응력"))
    if len(strain) < 2:
        raise ProcessingError("압축 곡선의 점이 너무 적습니다.")
    order = np.argsort(strain, kind="stable")
    x, y = strain[order], stress[order]
    reached = float(np.max(x))
    scalars: list[Scalar] = []
    notes: list[str] = []

    for key, at, label in STRAIN_POINTS:
        if reached >= at:
            scalars.append(
                Scalar(
                    key=key,
                    label=label,
                    value=float(np.interp(at, x, y)),
                    si_unit="Pa",
                    dimension="stress",
                )
            )
    missing = [label for key, at, label in STRAIN_POINTS if reached < at]
    if missing:
        notes.append(
            f"최대 압축 변형 {reached:.0%} — {', '.join(missing)} 은 닿지 않아 안 냈습니다."
        )

    # 압축 강도(ISO 844 · D1621 · D695): 10% 전에 최대(항복 봉우리)가 있으면 그 최대, 없으면
    # 10% 응력. **곡선 전체의 최대가 아니다** — 경질 폼은 치밀화 뒤 응력이 항복 봉우리보다
    # 커서, 전체 최대를 보면 늘 10% 응력이 된다.
    if reached >= 0.10:
        at_ten = float(np.interp(0.10, x, y))
        window = x <= 0.10
        top = int(np.argmax(y[window]))
        peak_value, peak_strain = float(y[window][top]), float(x[window][top])
        if peak_value > at_ten and peak_strain < 0.10:
            strength, how = peak_value, f"변형률 {peak_strain:.3g} 의 최대 응력(10% 전)"
        else:
            strength, how = at_ten, "10% 압축 응력(그 전에 최대가 없음)"
    else:
        strength, how = float(np.max(y)), "곡선의 최대 응력(10% 에 닿지 않음)"
    scalars.append(
        Scalar(
            key="compressive_strength",
            label="압축 강도",
            value=strength,
            si_unit="Pa",
            dimension="stress",
        )
    )
    notes.append(f"압축 강도 = {how}.")

    # 폼(ISO 13314): 평탄 응력 = 20~30% 평균, 치밀화 = 30% 뒤 평탄 응력의 1.3배에 닿는 곳,
    # 흡수 에너지 = 0~50% 의 ∫σdε.
    if reached >= 0.30:
        band = (x >= 0.20) & (x <= 0.30)
        if np.count_nonzero(band) >= 2:
            plateau = float(np.mean(y[band]))
            scalars.append(
                Scalar(
                    key="plateau_stress",
                    label="평탄 응력(20~30% 평균)",
                    value=plateau,
                    si_unit="Pa",
                    dimension="stress",
                )
            )
            after = np.flatnonzero((x > 0.30) & (y >= 1.3 * plateau))
            if len(after):
                scalars.append(
                    Scalar(
                        key="densification_strain",
                        label="치밀화 변형률(평탄 응력의 1.3배)",
                        value=float(x[after[0]]),
                        si_unit="1",
                        dimension="strain",
                    )
                )
    if reached >= 0.50:
        upto = x <= 0.50
        xs = np.append(x[upto], 0.50)
        ys = np.append(y[upto], float(np.interp(0.50, x, y)))
        energy = float(np.sum((ys[1:] + ys[:-1]) / 2.0 * np.diff(xs)))
        scalars.append(
            Scalar(
                key="energy_absorption_50pct",
                label="흡수 에너지(0~50%)",
                value=energy,
                si_unit="J/m3",
                dimension="energy_density",
            )
        )
    return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))
