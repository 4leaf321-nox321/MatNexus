"""반복(사이클) 시험의 공용 계산 — 사이클 분리 · 제하 탄성률 · 잔류 변형률 · 히스테리시스
(2026-10-20).

인장 · 압축 · 굽힘의 반복 시험이 **같은 계산**을 쓴다. 다른 것은 응력 · 변형률 열의 이름뿐이라
앞 단계가 만든 열을 고른다(`pair`) — 인장의 공칭 열, 압축의 압축 열(양수), 굽힘의 굽힘 열.

## 사이클을 어떻게 나누나

**응력(하중)이 뒤집히는 곳**(꼭짓점 · 골)으로 나눈다. 변형률로 나누면 안 된다 — 금속의 탄성
제하는 변형률을 0.05 % 쯤만 되돌려, 전체 폭(수 %)에 비하면 잡음과 구별이 안 된다. 응력은
제하하면 크게 떨어진다. 잡음으로 생기는 작은 뒤집힘을 세지 않도록, 전체 응력 폭의
`min_amplitude` 비율보다 크게 돌아가야 뒤집힘으로 본다(히스테리시스 문턱).

**변형률도 함께 줄어야 제하다.** 네킹 · 파단처럼 변형률은 계속 늘며 응력만 떨어지는 것은 제하가
아니라 그 시험의 끝이다 — 그것을 사이클로 세면 단조 시험에서도 사이클이 하나 생긴다.

사이클 k 는 「골(또는 시작) → 꼭짓점 → 다음 골」 이다 — 앞 절반이 하중(loading), 뒤 절반이
제하(unloading).

## 무엇을 재나

    제하 탄성률     제하 가지의 **윗부분**(꼭짓점 응력에서 `unload_fraction` 만큼 내려온
                   데까지)의 직선 기울기 — 손상이 쌓이면 사이클마다 작아진다.
    잔류 변형률     제하 가지가 응력 0 을 지나는 변형률(안 지나면 가지 끝, 그렇다고 말한다).
    히스테리시스    한 사이클의 고리 넓이 ∮σ dε = 하중 가지 ∫σ dε 빼기 제하 가지 ∫σ dε(J/m³).
                   하중 에너지에 대한 비(손실 비)도 낸다.

DB 도 HTTP 도 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

#: 앞 단계가 만드는 응력 · 변형률 열 — 인장(공칭) · 압축(양수) · 굽힘. 앞에 있는 것이 먼저다.
PAIRS: tuple[tuple[str, str], ...] = (
    ("strain_engineering", "stress_engineering"),
    ("compressive_strain", "compressive_stress"),
    ("flexural_strain", "flexural_stress"),
)

#: 만드는 열.
CYCLE = "cycle"
BRANCH = "cycle_branch"

#: 뒤집힘으로 볼 최소 폭 — 전체 응력 폭에 대한 비율(기본).
MIN_AMPLITUDE = 0.05
#: 제하 탄성률을 잴 제하 가지의 윗부분 — 꼭짓점에서 내려온 응력 폭의 비율(기본).
UNLOAD_FRACTION = 0.5
#: 사이클마다의 값을 이만큼까지만 낸다 — 넘으면 앞 · 뒤와 요약만.
MAX_PER_CYCLE = 100
#: 직선 하나를 얹는 최소 점 수.
MIN_POINTS = 3


@dataclass(frozen=True)
class Cycle:
    """사이클 하나 — 하중 가지 `[start, peak]`, 제하 가지 `[peak, end]`(점 차례 · 끝 포함)."""

    number: int
    start: int
    peak: int
    end: int


def pair(frame: Frame, options: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, str, str]:
    """응력 · 변형률 열 한 쌍. 고르지 않았으면 **앞 단계가 만든 것**을 찾는다."""
    strain_key = str(options.get("strain") or "")
    stress_key = str(options.get("stress") or "")
    if not strain_key or not stress_key:
        found = next(
            ((s, p) for s, p in PAIRS if s in frame.columns and p in frame.columns), None
        )
        if found is None:
            raise ProcessingError(
                "변형률 · 응력 열이 없습니다 — 앞에 인장 · 압축 · 굽힘의 응력-변형률 단계를 "
                f"두거나 열을 고르세요. 이 곡선에 있는 열: {', '.join(sorted(frame.columns))}"
            )
        strain_key = strain_key or found[0]
        stress_key = stress_key or found[1]
    strain = np.asarray(frame.require(strain_key, what="변형률"), dtype=np.float64)
    stress = np.asarray(frame.require(stress_key, what="응력"), dtype=np.float64)
    return strain, stress, strain_key, stress_key


def turning_points(
    stress: np.ndarray, strain: np.ndarray, threshold: float
) -> list[tuple[int, str]]:
    """뒤집히는 점 — `(차례, 'peak' | 'valley')`. 응력이 `threshold` 보다 크게 돌아가야 센다.

    꼭짓점은 **변형률도 줄었을 때만** — 응력만 떨어지고 변형률이 계속 늘면(네킹 · 파단) 제하가
    아니다. 그때는 꼭짓점을 세우지 않고 계속 오르는 중으로 둔다.
    """
    points: list[tuple[int, str]] = []
    if len(stress) < 2 or threshold <= 0:
        return points
    rising = True
    extreme = 0
    for index in range(1, len(stress)):
        value = stress[index]
        if not (np.isfinite(value) and np.isfinite(strain[index])):
            continue
        if rising:
            if value >= stress[extreme]:
                extreme = index
            elif stress[extreme] - value >= threshold and strain[index] < strain[extreme]:
                points.append((extreme, "peak"))
                rising, extreme = False, index
        else:
            if value <= stress[extreme]:
                extreme = index
            elif value - stress[extreme] >= threshold:
                points.append((extreme, "valley"))
                rising, extreme = True, index
    # 끝까지 제하한 채 끝났다 — 마지막 골은 끝의 가장 낮은 점이다.
    if not rising and len(points) and points[-1][1] == "peak":
        points.append((extreme, "valley"))
    return points


def split(strain: np.ndarray, stress: np.ndarray, min_amplitude: float) -> list[Cycle]:
    """사이클들 — 「골(또는 시작) → 꼭짓점 → 다음 골」. 제하 없이 끝난 마지막 하중은 뺀다."""
    finite = stress[np.isfinite(stress)]
    if finite.size < 2:
        return []
    span = float(np.max(finite) - np.min(finite))
    turns = turning_points(stress, strain, span * min_amplitude)
    cycles: list[Cycle] = []
    start = 0
    peak: int | None = None
    for index, kind in turns:
        if kind == "peak":
            peak = index
        elif peak is not None:
            cycles.append(Cycle(number=len(cycles) + 1, start=start, peak=peak, end=index))
            start, peak = index, None
    return cycles


def _options(options: dict[str, Any]) -> float:
    amplitude = float(options.get("min_amplitude") or MIN_AMPLITUDE)
    if not 0 < amplitude < 1:
        raise ProcessingError(f"뒤집힘 문턱은 0 과 1 사이여야 합니다: {amplitude}")
    return amplitude


def _cycles(
    frame: Frame, options: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, list[Cycle]]:
    strain, stress, _, stress_key = pair(frame, options)
    found = split(strain, stress, _options(options))
    if not found:
        raise ProcessingError(
            f"'{stress_key}' 에서 사이클(하중 → 제하)을 찾지 못했습니다 — 한 번 당긴 "
            "시험이거나, 뒤집힘 문턱(min_amplitude)이 너무 큽니다. 압축이면 "
            "「압축 응력-변형률」 단계가 하중 구간 하나만 남겼을 수 있습니다 — "
            "「쓸 하중 구간」 을 -1(전부)로."
        )
    return strain, stress, found


def _per_cycle(
    key: str, label: str, unit: str, values: list[tuple[int, float]]
) -> list[Scalar]:
    """사이클마다의 값 — 많으면 앞 · 뒤만(요약은 따로 낸다)."""
    if len(values) > MAX_PER_CYCLE:
        half = MAX_PER_CYCLE // 2
        values = [*values[:half], *values[-half:]]
    return [
        Scalar(
            key=f"{key}_c{number}",
            label=f"{label} (사이클 {number})",
            value=value,
            si_unit=unit,
        )
        for number, value in values
    ]


def _summary(key: str, label: str, unit: str, values: list[tuple[int, float]]) -> list[Scalar]:
    numbers = [value for _, value in values]
    return [
        Scalar(
            key=f"{key}_first", label=f"{label} (첫 사이클)", value=numbers[0], si_unit=unit
        ),
        Scalar(
            key=f"{key}_last",
            label=f"{label} (마지막 사이클)",
            value=numbers[-1],
            si_unit=unit,
        ),
        Scalar(
            key=f"{key}_mean",
            label=f"{label} (평균)",
            value=float(np.mean(numbers)),
            si_unit=unit,
        ),
    ]


# ── 단계 ────────────────────────────────────────────────────────────────────


def cycles(frame: Frame, options: dict[str, Any]) -> StepResult:
    """사이클 분리 — 점마다 사이클 번호(`cycle`)와 가지(`cycle_branch`: +1 하중, -1 제하)."""
    strain, _stress, found = _cycles(frame, options)
    number = np.zeros(len(strain))
    branch = np.zeros(len(strain))
    for one in found:
        number[one.start : one.end + 1] = one.number
        branch[one.start : one.peak + 1] = 1.0
        branch[one.peak + 1 : one.end + 1] = -1.0
    return StepResult(
        frame.with_columns({CYCLE: number, BRANCH: branch}, {CYCLE: "1", BRANCH: "1"}),
        notes=(
            f"사이클 {len(found)}개를 나눴습니다(뒤집힘 문턱: 응력 폭의 "
            f"{_options(options):.0%}). 사이클 밖의 점은 0 입니다.",
        ),
        scalars=(
            Scalar(key="cycle_count", label="사이클 수", value=float(len(found)), si_unit="1"),
        ),
    )


def unloading_modulus(frame: Frame, options: dict[str, Any]) -> StepResult:
    """사이클마다 **제하 가지 윗부분**의 기울기 — 손상이 쌓이면 작아진다."""
    strain, stress, found = _cycles(frame, options)
    fraction = float(options.get("unload_fraction") or UNLOAD_FRACTION)
    if not 0 < fraction <= 1:
        raise ProcessingError(f"제하 구간 비율은 0 과 1 사이여야 합니다: {fraction}")
    values: list[tuple[int, float]] = []
    skipped: list[int] = []
    for one in found:
        x, y = strain[one.peak : one.end + 1], stress[one.peak : one.end + 1]
        top, bottom = float(y[0]), float(np.nanmin(y))
        window = y >= top - fraction * (top - bottom)
        if int(np.sum(window)) < MIN_POINTS or top <= bottom:
            skipped.append(one.number)
            continue
        slope = float(np.polyfit(x[window], y[window], 1)[0])
        if slope > 0:
            values.append((one.number, slope))
        else:
            skipped.append(one.number)
    if not values:
        return StepResult(frame, notes=("제하 탄성률을 잴 수 있는 사이클이 없습니다.",))
    first, last = values[0][1], values[-1][1]
    notes = [
        f"제하 가지 윗부분(꼭짓점에서 응력 폭의 {fraction:.0%})의 기울기 — "
        f"사이클 {len(values)}개."
    ]
    if skipped:
        notes.append(f"점이 모자라 건너뛴 사이클: {', '.join(map(str, skipped))}.")
    return StepResult(
        frame,
        notes=tuple(notes),
        scalars=(
            *_summary("unloading_modulus", "제하 탄성률", "Pa", values),
            Scalar(
                key="unloading_modulus_ratio",
                label="제하 탄성률 비 (마지막/첫)",
                value=last / first,
                si_unit="1",
            ),
            *_per_cycle("unloading_modulus", "제하 탄성률", "Pa", values),
        ),
    )


def residual_strain(frame: Frame, options: dict[str, Any]) -> StepResult:
    """사이클마다 제하가 **응력 0 을 지나는 변형률** — 안 지나면 가지 끝(그렇다고 말한다)."""
    strain, stress, found = _cycles(frame, options)
    values: list[tuple[int, float]] = []
    short: list[int] = []
    for one in found:
        x, y = strain[one.peak : one.end + 1], stress[one.peak : one.end + 1]
        crossing = np.nonzero((y[:-1] > 0) & (y[1:] <= 0))[0]
        if crossing.size:
            at = int(crossing[0])
            # 두 점 사이에서 응력 0 을 지나는 변형률(직선 보간).
            ratio = y[at] / (y[at] - y[at + 1]) if y[at] != y[at + 1] else 0.0
            values.append((one.number, float(x[at] + ratio * (x[at + 1] - x[at]))))
        else:
            values.append((one.number, float(x[-1])))
            short.append(one.number)
    notes = ["제하가 응력 0 을 지나는 변형률 — 사이클이 남긴 변형."]
    if short:
        notes.append(
            f"응력 0 까지 제하하지 않은 사이클({', '.join(map(str, short))})은 제하 끝의 "
            "변형률입니다 — 실제 잔류 변형률보다 큽니다."
        )
    return StepResult(
        frame,
        notes=tuple(notes),
        scalars=(
            *_summary("residual_strain", "잔류 변형률", "1", values),
            Scalar(
                key="residual_strain_max",
                label="잔류 변형률 (최대)",
                value=max(value for _, value in values),
                si_unit="1",
            ),
            *_per_cycle("residual_strain", "잔류 변형률", "1", values),
        ),
    )


def _integral(x: np.ndarray, y: np.ndarray) -> float:
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if x.size < 2:
        return 0.0
    return float(np.sum((y[1:] + y[:-1]) * np.diff(x)) / 2.0)


def hysteresis(frame: Frame, options: dict[str, Any]) -> StepResult:
    """사이클마다 **고리 넓이**(소산 에너지 밀도)와 하중 에너지에 대한 비."""
    strain, stress, found = _cycles(frame, options)
    energy: list[tuple[int, float]] = []
    ratio: list[tuple[int, float]] = []
    for one in found:
        loading = _integral(strain[one.start : one.peak + 1], stress[one.start : one.peak + 1])
        # 제하 가지는 변형률이 줄어드는 방향이라 적분이 음수다 — 고리 = 하중 + 제하.
        unloading = _integral(strain[one.peak : one.end + 1], stress[one.peak : one.end + 1])
        area = loading + unloading
        energy.append((one.number, area))
        if loading > 0:
            ratio.append((one.number, area / loading))
    scalars = [
        *_summary("hysteresis_energy", "히스테리시스 에너지", "J/m3", energy),
        Scalar(
            key="hysteresis_energy_total",
            label="히스테리시스 에너지 (합)",
            value=float(sum(value for _, value in energy)),
            si_unit="J/m3",
        ),
    ]
    if ratio:
        scalars.extend(_summary("energy_loss_ratio", "손실 비 (고리/하중 에너지)", "1", ratio))
    scalars.extend(_per_cycle("hysteresis_energy", "히스테리시스 에너지", "J/m3", energy))
    scalars.extend(_per_cycle("energy_loss_ratio", "손실 비", "1", ratio))
    return StepResult(
        frame,
        notes=(
            "고리 넓이 ∮σ dε(단위 부피당 소산 에너지) — 하중 가지 적분에서 제하 가지 "
            "적분을 뺀 값.",
        ),
        scalars=tuple(scalars),
    )
