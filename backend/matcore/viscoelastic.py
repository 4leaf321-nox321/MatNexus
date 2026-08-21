"""시간-온도 중첩 — 여러 온도에서 잰 스윕을 한 곡선으로 겹친다.

DMA 는 한 온도에서 좁은 주파수 창(실측 0.1~20 Hz)만 훑는다. 해석이 필요한
범위는 그보다 훨씬 넓다. **온도를 바꿔 여러 번 재고 그것을 주파수 축으로 밀어
겹치면** 한 온도에서 잰 것보다 여러 자릿수 넓은 곡선이 나온다 — 그게 마스터커브다.

## 장비도 해 주는데 왜 우리가 하나

TA TRIOS 가 TTS 를 계산해 준다(`TTS - master curve (20.0 °C)`). 그것을 읽어
`derived` 곡선으로 보관하고 있다. 그런데 **그 곡선은 장비가 고른 기준 온도에
묶여 있다.** 해석을 60 °C 로 하고 싶으면 시험을 다시 하거나 우리가 겹쳐야 한다.

실제로 실파일 하나에 기준 온도를 바꿔 만든 마스터커브가 두 벌(20 °C·30 °C)
들어 있었다 — 사람이 그때그때 장비로 다시 만들고 있었다는 뜻이다.

## 부호 규약 — 65 와 반대다

65 의 구현(`viscoelastic_master_curve.py`)은 **시간영역** 전단완화 G(t) 용이라
`log10(t_r) = log10(t) - log10(a_T)` 로 민다. 여기는 **주파수영역**이라 반대다.

    log10(ω_r) = log10(ω) + log10(a_T)

같은 물리를 반대 축에서 보는 것뿐인데, **부호를 틀리면 곡선이 겹치는 대신
벌어진다.** 그런데 벌어진 것도 그럴듯한 곡선이라 그림만 봐서는 모른다. 그래서
시험이 아는 답(WLF 계수)으로 검산한다.

## 추정하지 않는다

* **겹치는 구간이 없으면 실패한다.** 억지로 늘여 붙이지 않는다 — 근거 없는
  구간을 만들어 내는 것이 이 도메인에서 가장 비싼 결함이다
* **기준 온도는 잰 온도 중에 있어야 한다.** 없으면 그 온도의 곡선을 지어내야 한다
* 맞춘 이동인자와 **관측한 이동인자를 함께 남긴다.** 둘이 벌어지면 WLF 가 이
  재료에 안 맞는다는 뜻이고, 그건 사람이 판단할 일이다
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares, minimize_scalar

#: 기체 상수 J/(mol·K). Arrhenius 활성화 에너지를 낼 때 쓴다.
GAS_CONSTANT = 8.31446261815324

#: 이동인자를 찾을 범위(log10). 이보다 넓게 밀어야 겹친다면 그건 같은 재료의
#: 같은 물성이 아니다.
SHIFT_BOUND = 12.0

#: 두 곡선이 겹쳤다고 인정할 최소 구간. 짧은 쪽 폭의 이 비율은 겹쳐야 한다 —
#: 끝점 하나가 스치는 것을 "겹쳤다" 로 보면 이동인자가 아무 값이나 나온다.
MIN_OVERLAP_RATIO = 0.1

#: 겹침 구간을 비교할 점 수.
OVERLAP_SAMPLES = 64

#: 이동인자를 맞추려면 최소 몇 개 온도가 필요한가. WLF 는 계수가 둘이라
#: 세 점은 있어야 맞춘 것이 뜻을 갖는다.
MIN_TEMPERATURES = 3


class ViscoelasticError(Exception):
    """이 계산을 이 입력에 적용할 수 없다. 메시지는 **사용자가 읽는다.**"""


@dataclass(frozen=True)
class Sweep:
    """한 온도에서 잰 주파수 스윕.

    `frequency_hz` 는 **증가 순**이어야 한다. 보간이 전부 그것을 전제한다.
    """

    temperature_k: float
    frequency_hz: np.ndarray
    storage_pa: np.ndarray
    loss_pa: np.ndarray | None = None

    def log_frequency(self) -> np.ndarray:
        return np.log10(self.frequency_hz)


@dataclass(frozen=True)
class ShiftFactor:
    """한 온도의 이동인자와 **그것을 어떻게 얻었는지.**"""

    temperature_k: float
    log10_a_t: float
    source: str
    """`reference` | `fitted` | `manual`."""
    observed_log10_a_t: float | None = None
    """겹쳐 보고 직접 잰 값. 맞춘 값과 벌어지면 그 모델이 이 재료에 안 맞는다."""
    residual: float | None = None
    """맞춘 값에서 관측값을 뺀 것."""
    overlap_rmse: float | None = None
    """겹침 구간의 정규화 잔차. 클수록 두 곡선 모양이 다르다는 뜻이다."""


@dataclass(frozen=True)
class MasterCurve:
    reference_temperature_k: float
    method: str
    frequency_hz: np.ndarray
    """환산 주파수. 잰 범위보다 훨씬 넓다 — 그게 겹치는 이유다."""
    storage_pa: np.ndarray
    loss_pa: np.ndarray | None
    shifts: tuple[ShiftFactor, ...]
    parameters: dict[str, float] = field(default_factory=dict)
    """`wlf` 면 `c1`·`c2`, `arrhenius` 면 `activation_energy_j_per_mol`."""
    notes: tuple[str, ...] = ()


def _require_sweeps(sweeps: list[Sweep], reference_temperature_k: float) -> list[Sweep]:
    if len(sweeps) < 2:
        raise ViscoelasticError(
            f"온도가 {len(sweeps)}개뿐입니다. 겹치려면 최소 2개 온도가 필요합니다."
        )
    for sweep in sweeps:
        if len(sweep.frequency_hz) < 2:
            raise ViscoelasticError(
                f"{sweep.temperature_k:g} K 스윕에 점이 {len(sweep.frequency_hz)}개뿐입니다."
            )
        if np.any(sweep.frequency_hz <= 0):
            raise ViscoelasticError(
                f"{sweep.temperature_k:g} K 스윕에 0 이하 주파수가 있습니다."
            )
        if np.any(np.diff(sweep.frequency_hz) <= 0):
            raise ViscoelasticError(
                f"{sweep.temperature_k:g} K 스윕의 주파수가 증가 순이 아닙니다. "
                f"보간이 정렬을 전제합니다."
            )
        if np.any(sweep.storage_pa <= 0):
            raise ViscoelasticError(
                f"{sweep.temperature_k:g} K 스윕에 0 이하 저장 탄성률이 있습니다."
            )
    ordered = sorted(sweeps, key=lambda item: item.temperature_k)
    if not any(
        math.isclose(item.temperature_k, reference_temperature_k, rel_tol=0, abs_tol=1e-6)
        for item in ordered
    ):
        measured = ", ".join(f"{item.temperature_k:g}" for item in ordered)
        raise ViscoelasticError(
            f"기준 온도 {reference_temperature_k:g} K 가 잰 온도에 없습니다({measured} K). "
            f"없는 온도의 곡선을 지어내지 않습니다 — 잰 온도 중에서 고르세요."
        )
    return ordered


def observed_shift(reference: Sweep, source: Sweep) -> tuple[float, float]:
    """두 스윕을 실제로 겹쳐 보고 이동인자를 잰다. `(log10 a_T, 정규화 잔차)`.

    **모델을 가정하지 않는다.** WLF 도 Arrhenius 도 이 값을 목표로 맞춘다.

    겹침이 짧으면 큰 벌점을 준다. 끝점 하나가 스치는 것을 "겹쳤다" 로 보면
    이동인자가 아무 값이나 나오고, 그 값으로 만든 마스터커브는 그럴듯하다.
    """
    ref_x = reference.log_frequency()
    ref_y = np.log10(reference.storage_pa)
    src_x = source.log_frequency()
    src_y = np.log10(source.storage_pa)
    span = min(float(np.ptp(ref_x)), float(np.ptp(src_x)))

    def objective(log10_a_t: float) -> float:
        # 주파수영역: 환산 주파수는 ω·a_T 이므로 로그 축에서 **더한다**.
        moved_lower = float(src_x[0] + log10_a_t)
        moved_upper = float(src_x[-1] + log10_a_t)
        lower = max(float(ref_x[0]), moved_lower)
        upper = min(float(ref_x[-1]), moved_upper)
        if upper - lower < MIN_OVERLAP_RATIO * span:
            return 1e6 + abs(upper - lower)
        grid = np.linspace(lower, upper, OVERLAP_SAMPLES)
        expected = np.interp(grid, ref_x, ref_y)
        actual = np.interp(grid - log10_a_t, src_x, src_y)
        return float(np.mean((actual - expected) ** 2))

    outcome = minimize_scalar(objective, bounds=(-SHIFT_BOUND, SHIFT_BOUND), method="bounded")
    shift = float(outcome.x)
    if not outcome.success or not math.isfinite(shift):
        raise ViscoelasticError(
            f"{source.temperature_k:g} K 를 {reference.temperature_k:g} K 에 겹치지 "
            f"못했습니다. 두 온도의 주파수 창이 겹치는지 확인하세요."
        )
    residual = float(outcome.fun)
    if residual >= 1e6:
        raise ViscoelasticError(
            f"{source.temperature_k:g} K 와 {reference.temperature_k:g} K 가 겹치는 "
            f"구간이 너무 짧습니다(짧은 쪽 폭의 {MIN_OVERLAP_RATIO:.0%} 미만). "
            f"온도 간격을 좁히거나 주파수 창을 넓혀야 합니다."
        )
    return shift, math.sqrt(max(0.0, residual))


def _observed_all(
    sweeps: list[Sweep], reference_temperature_k: float
) -> dict[float, tuple[float, float]]:
    """온도마다 관측 이동인자. **이웃끼리 이어 붙여 쌓는다.**

    65 는 각 온도를 기준 온도에 **직접** 겹친다. 실측 DMA 에서는 그게 성립하지
    않는다 — 한 온도의 창이 0.1~20 Hz(2.3 자릿수)인데 -40 °C 에서 20 °C 까지의
    총 이동이 11 자릿수다. 양 끝은 애초에 겹치는 구간이 없다.

    실제로 사람이 하는 방법이 이것이다: 옆 온도에 겹치고, 그 결과에 또 옆 온도를
    겹치고, 기준 온도에서부터 누적한다. 장비도 같은 일을 한다(실측 파일의
    마스터커브가 1.18e-11 Hz 까지 내려간다 — 창 하나로는 못 만드는 범위다).

    대가는 **오차가 누적된다**는 것이다. 그래서 각 단계의 겹침 잔차를 그대로
    들고 다닌다 — 어느 단계에서 벌어졌는지가 보여야 한다.
    """
    index = next(
        position
        for position, item in enumerate(sweeps)
        if math.isclose(item.temperature_k, reference_temperature_k, abs_tol=1e-6)
    )
    found = {sweeps[index].temperature_k: (0.0, 0.0)}

    running = 0.0
    for position in range(index + 1, len(sweeps)):
        step, rmse = observed_shift(sweeps[position - 1], sweeps[position])
        running += step
        found[sweeps[position].temperature_k] = (running, rmse)

    running = 0.0
    for position in range(index - 1, -1, -1):
        step, rmse = observed_shift(sweeps[position + 1], sweeps[position])
        running += step
        found[sweeps[position].temperature_k] = (running, rmse)
    return found


def fit_wlf(
    sweeps: list[Sweep], reference_temperature_k: float
) -> tuple[tuple[ShiftFactor, ...], float, float]:
    """WLF 로 이동인자를 맞춘다. `log10 a_T = -c1·ΔT / (c2 + ΔT)`.

    관측값을 목표로 두 계수를 맞춘다. **관측값도 함께 남긴다** — 맞춘 것과
    벌어지면 WLF 가 이 재료·이 온도 범위에 안 맞는다는 뜻이고, 그 판단은
    사람이 한다.
    """
    ordered = _require_sweeps(sweeps, reference_temperature_k)
    if len(ordered) < MIN_TEMPERATURES:
        raise ViscoelasticError(
            f"WLF 는 계수가 둘이라 최소 {MIN_TEMPERATURES}개 온도가 필요합니다"
            f"(지금 {len(ordered)}개). 온도 둘로 맞춘 계수는 언제나 정확히 맞고,"
            f" 그건 맞았다는 뜻이 아닙니다."
        )
    observed = _observed_all(ordered, reference_temperature_k)
    temperatures = np.asarray(sorted(observed), dtype=float)
    deltas = temperatures - reference_temperature_k
    targets = np.asarray([observed[float(value)][0] for value in temperatures])

    # `c2 + ΔT` 가 0 이 되면 발산한다. 가장 낮은 온도에서도 양수이게 아래를 막는다.
    lower_c2 = max(1e-3, -float(np.min(deltas)) + 1e-3)

    def residual(parameters: np.ndarray) -> np.ndarray:
        c1, c2 = float(parameters[0]), float(parameters[1])
        return np.asarray(-c1 * deltas / (c2 + deltas) - targets, dtype=float)

    outcome = least_squares(
        residual,
        # 고분자의 흔한 보편값에서 출발한다(c1≈17.44, c2≈51.6).
        x0=np.asarray([17.44, max(51.6, lower_c2 + 1.0)]),
        bounds=(np.asarray([1e-8, lower_c2]), np.asarray([1000.0, 5000.0])),
        method="trf",
        max_nfev=5000,
    )
    if not outcome.success or not np.all(np.isfinite(outcome.x)):
        raise ViscoelasticError("WLF 계수를 맞추지 못했습니다. 관측 이동인자를 확인하세요.")
    c1, c2 = float(outcome.x[0]), float(outcome.x[1])

    shifts = tuple(
        ShiftFactor(
            temperature_k=float(temperature),
            log10_a_t=float(-c1 * delta / (c2 + delta)),
            source="reference" if delta == 0 else "fitted",
            observed_log10_a_t=observed[float(temperature)][0],
            residual=float(-c1 * delta / (c2 + delta)) - observed[float(temperature)][0],
            overlap_rmse=observed[float(temperature)][1],
        )
        for temperature, delta in zip(temperatures, deltas, strict=True)
    )
    return shifts, c1, c2


def fit_arrhenius(
    sweeps: list[Sweep], reference_temperature_k: float
) -> tuple[tuple[ShiftFactor, ...], float]:
    """Arrhenius 로 맞춘다. `log10 a_T = Ea/(2.303 R)*(1/T - 1/T_ref)`.

    유리 전이 아래처럼 WLF 가 안 맞는 구간에서 쓴다. 원점을 지나는 직선이라
    닫힌 꼴로 풀린다 — 반복이 없으니 수렴 실패도 없다.
    """
    ordered = _require_sweeps(sweeps, reference_temperature_k)
    if len(ordered) < MIN_TEMPERATURES:
        raise ViscoelasticError(
            f"Arrhenius 는 최소 {MIN_TEMPERATURES}개 온도가 필요합니다(지금 {len(ordered)}개)."
        )
    observed = _observed_all(ordered, reference_temperature_k)
    temperatures = np.asarray(sorted(observed), dtype=float)
    inverse_delta = 1.0 / temperatures - 1.0 / reference_temperature_k
    targets = np.asarray([observed[float(value)][0] for value in temperatures])

    denominator = float(np.dot(inverse_delta, inverse_delta))
    if denominator <= np.finfo(float).tiny:
        raise ViscoelasticError("온도 범위가 너무 좁아 Arrhenius 기울기를 낼 수 없습니다.")
    slope = float(np.dot(inverse_delta, targets) / denominator)
    activation_energy = slope * math.log(10.0) * GAS_CONSTANT
    if not math.isfinite(activation_energy) or activation_energy <= 0:
        # **음의 활성화 에너지는 물리가 아니다** — 온도가 올라갈수록 느려진다는
        # 뜻이 된다. 그래도 숫자는 나오고 마스터커브도 그려지므로, 여기서 안
        # 막으면 뒤집힌 곡선 위에서 Prony 를 맞추게 된다.
        raise ViscoelasticError(
            f"활성화 에너지가 양수가 아닙니다({activation_energy / 1000:.4g} kJ/mol). "
            f"온도가 올라갈수록 느려진다는 뜻이라 물리가 아닙니다 — 이동인자의 "
            f"부호나 온도 라벨을 확인하세요."
        )

    predicted = slope * inverse_delta
    shifts = tuple(
        ShiftFactor(
            temperature_k=float(temperature),
            log10_a_t=float(value),
            source=(
                "reference"
                if math.isclose(temperature, reference_temperature_k, abs_tol=1e-6)
                else "fitted"
            ),
            observed_log10_a_t=observed[float(temperature)][0],
            residual=float(value) - observed[float(temperature)][0],
            overlap_rmse=observed[float(temperature)][1],
        )
        for temperature, value in zip(temperatures, predicted, strict=True)
    )
    return shifts, activation_energy


def _manual_shifts(
    sweeps: list[Sweep], reference_temperature_k: float, factors: dict[float, float]
) -> tuple[ShiftFactor, ...]:
    missing = [
        item.temperature_k
        for item in sweeps
        if not any(math.isclose(key, item.temperature_k, abs_tol=1e-6) for key in factors)
    ]
    if missing:
        listed = ", ".join(f"{value:g}" for value in missing)
        raise ViscoelasticError(f"이동인자가 없는 온도가 있습니다: {listed} K.")
    return tuple(
        ShiftFactor(
            temperature_k=item.temperature_k,
            log10_a_t=next(
                value
                for key, value in factors.items()
                if math.isclose(key, item.temperature_k, abs_tol=1e-6)
            ),
            source=(
                "reference"
                if math.isclose(item.temperature_k, reference_temperature_k, abs_tol=1e-6)
                else "manual"
            ),
        )
        for item in sweeps
    )


def master_curve(
    sweeps: list[Sweep],
    *,
    reference_temperature_k: float,
    method: str = "wlf",
    manual_shifts: dict[float, float] | None = None,
    points: int = 200,
) -> MasterCurve:
    """여러 온도의 스윕을 기준 온도로 겹친다.

    `method` 는 `wlf` · `arrhenius` · `manual`. 앞의 둘은 관측 이동인자를 목표로
    모델을 맞추고, `manual` 은 사람이 준 값을 그대로 쓴다(장비가 준 이동인자를
    넣을 때).
    """
    ordered = _require_sweeps(sweeps, reference_temperature_k)
    parameters: dict[str, float] = {}
    notes: list[str] = []

    if method == "wlf":
        shifts, c1, c2 = fit_wlf(ordered, reference_temperature_k)
        parameters = {"c1": c1, "c2": c2}
        notes.append(f"WLF c1={c1:.4g}, c2={c2:.4g} K (기준 {reference_temperature_k:g} K)")
    elif method == "arrhenius":
        shifts, activation_energy = fit_arrhenius(ordered, reference_temperature_k)
        parameters = {"activation_energy_j_per_mol": activation_energy}
        notes.append(
            f"Arrhenius Ea={activation_energy / 1000:.4g} kJ/mol "
            f"(기준 {reference_temperature_k:g} K)"
        )
    elif method == "manual":
        if not manual_shifts:
            raise ViscoelasticError("manual 방법은 온도별 이동인자가 필요합니다.")
        shifts = _manual_shifts(ordered, reference_temperature_k, manual_shifts)
        notes.append(
            f"사람이 준 이동인자 {len(shifts)}개 (기준 {reference_temperature_k:g} K)"
        )
    else:
        raise ViscoelasticError(f"모르는 방법입니다: {method!r} (wlf · arrhenius · manual)")

    # **맞춘 것과 관측한 것이 벌어지면 말한다.** 그래도 계산은 한다 — 어느 쪽이
    # 옳은지는 재료가 정하고, 판단은 사람이 한다.
    drift = [item for item in shifts if item.residual is not None and abs(item.residual) > 0.5]
    if drift:
        listed = ", ".join(f"{item.temperature_k:g} K({item.residual:+.2f})" for item in drift)
        notes.append(
            f"맞춘 이동인자가 관측값과 0.5 자릿수 넘게 벌어진 온도가 있습니다: {listed}. "
            f"이 온도 범위에 {method} 가 안 맞을 수 있습니다."
        )

    by_temperature = {item.temperature_k: item.log10_a_t for item in shifts}
    moved: list[tuple[np.ndarray, np.ndarray, np.ndarray | None]] = []
    for sweep in ordered:
        shift = next(
            value
            for key, value in by_temperature.items()
            if math.isclose(key, sweep.temperature_k, abs_tol=1e-6)
        )
        moved.append((sweep.log_frequency() + shift, sweep.storage_pa, sweep.loss_pa))

    lower = min(float(x[0]) for x, _, _ in moved)
    upper = max(float(x[-1]) for x, _, _ in moved)
    if not lower < upper:
        raise ViscoelasticError("겹친 뒤 쓸 수 있는 주파수 범위가 없습니다.")

    grid = np.linspace(lower, upper, points)
    storage = _blend(grid, [(x, y) for x, y, _ in moved])
    loss = (
        _blend(grid, [(x, z) for x, _, z in moved if z is not None])
        if all(z is not None for _, _, z in moved)
        else None
    )
    window = max(float(np.ptp(ordered[0].log_frequency())), 1e-9)
    widening = (upper - lower) / window
    notes.append(
        f"주파수 {10**lower:.3g}~{10**upper:.3g} Hz 로 겹쳤습니다 (잰 범위보다 {widening:.1f}배 넓음)."
    )
    if widening < 1.5:
        # **겹쳤는데 안 넓어졌으면 겹칠 것이 없었다는 뜻이다.**
        #
        # 실측으로 걸렸다: 강판(SECC) DMA 파일을 넣었더니 여섯 온도의 저장
        # 탄성률이 전부 같아서 이동인자가 0 으로 나왔다. 마스터커브는 그려지고
        # 계수도 나오는데(c1≈0) 아무 뜻이 없다. 이 경고가 없으면 그 곡선 위에서
        # Prony 를 맞추고 그 결과를 해석에 넣게 된다.
        notes.append(
            f"겹쳤는데 범위가 {widening:.1f}배밖에 안 늘었습니다 — 온도에 따라 곡선이 "
            f"거의 안 움직였다는 뜻입니다. 이 온도 범위에서 점탄성 거동이 없거나"
            f"(금속 등), 온도마다 같은 값이 들어왔는지 확인하세요."
        )
    return MasterCurve(
        reference_temperature_k=reference_temperature_k,
        method=method,
        frequency_hz=np.power(10.0, grid),
        storage_pa=storage,
        loss_pa=loss,
        shifts=shifts,
        parameters=parameters,
        notes=tuple(notes),
    )


def _blend(grid: np.ndarray, curves: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """겹친 구간은 평균한다. **없는 구간을 지어내지 않는다.**

    각 곡선은 자기가 실제로 덮는 구간에만 기여한다 — `np.interp` 는 범위 밖을
    끝점 값으로 채우므로, 그대로 쓰면 잰 적 없는 주파수에 평평한 꼬리가 생기고
    그 꼬리가 Prony 적합에 그대로 들어간다.
    """
    total = np.zeros_like(grid)
    count = np.zeros_like(grid)
    for x, y in curves:
        inside = (grid >= x[0]) & (grid <= x[-1])
        if not np.any(inside):
            continue
        total[inside] += np.interp(grid[inside], x, np.log10(y))
        count[inside] += 1
    if np.any(count == 0):
        raise ViscoelasticError(
            "겹친 곡선들 사이에 빈 구간이 있습니다. 온도 간격이 너무 넓습니다."
        )
    blended: np.ndarray = np.power(10.0, total / count)
    return blended
