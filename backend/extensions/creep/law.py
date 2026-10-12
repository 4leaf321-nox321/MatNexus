"""크리프 시험 → 최소 크리프 속도(처리), 여러 시험 → Norton · Garofalo(묶음). 2026-10-12.

## 시험 하나 — 최소 크리프 속도

    크리프 변형률   εc(t) = ε(t) - ε(t₀)      t₀ 는 첫 점(하중을 다 건 때)
    최소 속도       시간 길이의 20% 창을 5% 씩 밀며 εc - t 에 직선을 맞추고, R² ≥ 0.9 인 창의
                   **가장 작은 양의 기울기**. 1차(감속) · 3차(가속) 크리프 사이의 정상상태가
                   그 자리다. 맞는 창이 없으면 가장 작은 양의 기울기를 쓰고 그렇다고 말한다.

## 여러 시험 — 식 맞추기

점 하나가 (가한 응력 σ, 온도 T, 최소 속도 ε̇) 다. 로그를 취하면 둘 다 선형 문제가 된다:

    Norton         ln ε̇ = ln A + n·ln σ - (Q/R)/T          온도가 하나면 Q 없이(그 온도의 A)
    Garofalo       ln ε̇ = ln C1 + C3·ln sinh(C2·σ) - C4/T  C2 를 고르면 나머지가 선형이다 —
                   C2 를 로그 격자로 훑어 잔차가 가장 작은 것을 고른다(비선형 최적화가 출발점에
                   따라 갈리는 일을 피한다). 온도가 하나면 C4 = 0(그 온도의 C1).

**Garofalo 는 멱법칙이 깨지는 높은 응력이 있어야 C2 가 선다.** 데이터가 멱법칙(log-log
직선)이면
C2 가 격자 끝에 붙는다 — 그때는 Norton 과 같은 식이라 그렇게 말하고 Norton 을 권한다.

응력은 Pa, 시간은 s, 온도는 K — 레지스트리의 값은 SI 다. Norton A 의 단위는 1/(s·Pa^n) 이라
덱 단위계로 옮길 때 응력 단위가 n 제곱으로 들어간다(`deck.norton`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member
from matcore.processing import Frame, ProcessingError, Scalar, StepResult

TIME = "time"
STRAIN = "strain"
CREEP_STRAIN = "creep_strain"
STRESS = "applied_stress"
TEMPERATURE = "temperature"
RATE = "min_creep_rate"

#: 최소 속도를 찾는 창 — 시간 길이의 비율과 밀어 가는 폭.
WINDOW = 0.2
STRIDE = 0.05
MIN_WINDOW_POINTS = 5
LINEAR = 0.9

#: 기체 상수(J/(mol·K)) — Norton Q 를 J/mol 로 낸다.
GAS_CONSTANT = 8.314462618

#: 같은 온도로 보는 폭(K).
SAME_TEMPERATURE = 1.0

#: Garofalo C2 격자 — 1/σ 의 이 배수 범위를 로그로 훑는다.
C2_SPAN = (1e-3, 1e2)
C2_POINTS = 400


# ── 시험 하나 ─────────────────────────────────────────────────────────────


def _line(t: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """(기울기, 절편, R²)."""
    slope, intercept = (float(one) for one in np.polyfit(t, y, 1))
    residual = y - (slope * t + intercept)
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum(residual**2)) / total if total > 0 else 1.0
    return slope, intercept, r2


def min_rate(time: np.ndarray, creep: np.ndarray) -> tuple[float, float, float, bool]:
    """`(최소 속도, 창 시작, 창 끝, 직선 창이었나)`. 못 찾으면 멈춘다."""
    span = float(time[-1] - time[0])
    if span <= 0:
        raise ProcessingError("시간이 늘지 않습니다 — 크리프 속도를 잴 수 없습니다.")
    best: tuple[float, float, float, bool] | None = None
    start = float(time[0])
    while start + WINDOW * span <= float(time[-1]) + 1e-12 * span:
        end = start + WINDOW * span
        inside = (time >= start) & (time <= end)
        if int(inside.sum()) >= MIN_WINDOW_POINTS:
            slope, _, r2 = _line(time[inside], creep[inside])
            if slope > 0:
                linear = r2 >= LINEAR
                candidate = (slope, start, end, linear)
                if best is None or (linear, -slope) > (best[3], -best[0]):
                    best = candidate
        start += STRIDE * span
    if best is None:
        raise ProcessingError(
            f"크리프 변형률이 느는 구간을 못 찾았습니다 — 창마다 점이 {MIN_WINDOW_POINTS}개 "
            "이상이고 변형률이 늘어야 합니다."
        )
    return best


def creep_rate(frame: Frame, options: dict[str, Any]) -> StepResult:
    """처리 단계 — 크리프 변형률 열과 최소 크리프 속도."""
    time = np.asarray(frame.require(str(options.get("time") or TIME), what="시간"), float)
    strain = np.asarray(
        frame.require(str(options.get("strain") or STRAIN), what="변형률"), float
    )
    order = np.argsort(time, kind="stable")
    time, strain = time[order], strain[order]
    creep = strain - strain[0]
    rate, start, end, linear = min_rate(time, creep)
    notes = [
        f"크리프 변형률은 첫 점(t = {time[0]:.4g} s, ε₀ = {strain[0]:.4g})을 뺀 값입니다 — "
        "하중을 "
        "다 건 순간의 변형률(탄성 + 순간 소성)이 ε₀ 입니다.",
        f"최소 크리프 속도는 {start:.4g}~{end:.4g} s 창(시간 길이의 {WINDOW:.0%})의 "
        "기울기입니다.",
    ]
    if not linear:
        notes.append(
            f"R² ≥ {LINEAR} 인 직선 창이 없어 가장 완만한 창을 썼습니다 — 정상상태가 짧거나 "
            "곡선이 거칩니다."
        )
    sorted_frame = Frame(
        {key: np.asarray(value)[order] for key, value in frame.columns.items()},
        dict(frame.units),
    )
    return StepResult(
        frame=sorted_frame.with_columns({CREEP_STRAIN: creep}, {CREEP_STRAIN: "1"}),
        notes=tuple(notes),
        scalars=(
            Scalar(RATE, "최소 크리프 속도", rate, "1/s", "strain_rate"),
            Scalar(
                "creep_initial_strain", "하중 직후 변형률", float(strain[0]), "1", "strain"
            ),
            Scalar(
                "creep_strain_final", "마지막 크리프 변형률", float(creep[-1]), "1", "strain"
            ),
            Scalar("creep_duration", "시험 시간", float(time[-1] - time[0]), "s", "time"),
            Scalar("creep_window_start", "속도 창 시작", start, "s", "time"),
            Scalar("creep_window_end", "속도 창 끝", end, "s", "time"),
        ),
    )


# ── 여러 시험 ─────────────────────────────────────────────────────────────


def _points(members: Sequence[Member]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for member in members:
        sigma = member.values.get(STRESS)
        temperature = member.values.get(TEMPERATURE)
        rate = member.values.get(RATE)
        missing = [
            name
            for name, value in (
                ("가한 응력", sigma),
                ("시험 온도", temperature),
                ("최소 속도", rate),
            )
            if not isinstance(value, int | float)
        ]
        if missing:
            raise GroupError(f"{member.label}: {' · '.join(missing)} 이(가) 없습니다.")
        assert sigma is not None and temperature is not None and rate is not None
        if sigma <= 0 or rate <= 0 or temperature <= 0:
            raise GroupError(
                f"{member.label}: 응력 · 온도 · 최소 속도는 0 보다 커야 합니다 "
                f"(σ {sigma:g} Pa, T {temperature:g} K, ε̇ {rate:g} 1/s)."
            )
        points.append(
            {"label": member.label, "stress": sigma, "temperature": temperature, "rate": rate}
        )
    return points


def _temperatures(points: Sequence[Mapping[str, Any]]) -> list[float]:
    """서로 다른 온도(1 K 안은 같게 본다)."""
    levels: list[float] = []
    for point in sorted(points, key=lambda one: one["temperature"]):
        if not levels or point["temperature"] - levels[-1] > SAME_TEMPERATURE:
            levels.append(float(point["temperature"]))
    return levels


def _solve(design: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, float]:
    """최소제곱 — (계수, ln 잔차의 제곱합)."""
    solution, *_ = np.linalg.lstsq(design, target, rcond=None)
    residual = target - design @ solution
    return solution, float(np.sum(residual**2))


def _r2(target: np.ndarray, ss_res: float) -> float:
    total = float(np.sum((target - target.mean()) ** 2))
    return 1.0 - ss_res / total if total > 0 else 1.0


def creep_law(members: list[Member]) -> GroupOutcome:
    """Norton(± Arrhenius)과 Garofalo 를 함께 맞춘다."""
    points = _points(members)
    if len(points) < 2:
        raise GroupError(f"크리프 식에는 시험이 2건 이상 필요합니다(지금 {len(points)}건).")
    sigma = np.asarray([p["stress"] for p in points])
    temperature = np.asarray([p["temperature"] for p in points])
    rate = np.asarray([p["rate"] for p in points])
    ln_rate, ln_sigma = np.log(rate), np.log(sigma)
    if float(np.ptp(ln_sigma)) < 1e-6:
        raise GroupError("가한 응력이 모두 같습니다 — 응력 지수를 정할 수 없습니다.")
    levels = _temperatures(points)
    many = len(levels) > 1
    warnings: list[str] = []
    if many and len(points) < 3:
        raise GroupError("온도가 둘 이상이면 시험이 3건 이상 있어야 Q 까지 정해집니다.")

    columns = [np.ones_like(ln_sigma), ln_sigma] + ([-1.0 / temperature] if many else [])
    design = np.column_stack(columns)
    solution, ss_res = _solve(design, ln_rate)
    norton_a = float(math.exp(solution[0]))
    norton_n = float(solution[1])
    q_over_r = float(solution[2]) if many else 0.0
    values: dict[str, float] = {
        "norton_a": norton_a,
        "norton_n": norton_n,
        "norton_r_squared": _r2(ln_rate, ss_res),
        "point_count": float(len(points)),
        "temperature_count": float(len(levels)),
        "stress_min": float(sigma.min()),
        "stress_max": float(sigma.max()),
        "temperature_min": float(temperature.min()),
        "temperature_max": float(temperature.max()),
    }
    if many:
        values["activation_energy"] = q_over_r * GAS_CONSTANT
        if q_over_r <= 0:
            warnings.append(
                "온도가 오를수록 크리프가 느려지는 모양입니다(Q ≤ 0) — 조건을 확인하세요."
            )
    else:
        warnings.append(
            f"온도가 하나({levels[0]:.5g} K)라 Q 를 정하지 않았습니다 — A 는 그 온도의 값이고 "
            "다른 온도에서는 쓸 수 없습니다."
        )
    if norton_n <= 0:
        warnings.append(
            "응력이 클수록 크리프가 느려지는 모양입니다(n ≤ 0) — 데이터를 확인하세요."
        )

    garofalo = _garofalo(sigma, temperature, ln_rate, many) if len(points) >= 4 else None
    if garofalo is None:
        warnings.append("Garofalo 는 시험이 4건 이상일 때만 맞춥니다.")
    else:
        c1, c2, c3, c4, ss, at_edge = garofalo
        values.update(
            {
                "garofalo_c1": c1,
                "garofalo_c2": c2,
                "garofalo_c3": c3,
                "garofalo_c4": c4,
                "garofalo_r_squared": _r2(ln_rate, ss),
            }
        )
        if at_edge:
            warnings.append(
                "Garofalo 의 C2 가 훑은 범위 끝에 붙었습니다 — 데이터가 멱법칙(log-log "
                "직선)이라 "
                "Garofalo 가 Norton 과 같은 식이 됩니다. 덱은 Norton 을 쓰세요."
            )
    return GroupOutcome(
        values=values,
        detail={"points": points, "garofalo_at_edge": bool(garofalo and garofalo[5])},
        warnings=warnings,
        used=[p["label"] for p in points],
    )


def _garofalo(
    sigma: np.ndarray, temperature: np.ndarray, ln_rate: np.ndarray, many: bool
) -> tuple[float, float, float, float, float, bool] | None:
    """C2 를 훑으며 (ln C1, C3, C4) 를 선형으로 푼다 — `(C1, C2, C3, C4, 잔차, 끝에
    붙었나)`."""
    scale = 1.0 / float(np.median(sigma))
    grid = np.logspace(
        math.log10(C2_SPAN[0] * scale), math.log10(C2_SPAN[1] * scale), C2_POINTS
    )
    best: tuple[float, int, np.ndarray] | None = None
    for index, c2 in enumerate(grid):
        argument = c2 * sigma
        if float(np.max(argument)) > 700:  # sinh 가 넘친다
            break
        columns = [np.ones_like(sigma), np.log(np.sinh(argument))]
        if many:
            columns.append(-1.0 / temperature)
        solution, ss = _solve(np.column_stack(columns), ln_rate)
        if best is None or ss < best[0]:
            best = (ss, index, solution)
    if best is None:
        return None
    ss, index, solution = best
    at_edge = index in (0, len(grid) - 1)
    c4 = float(solution[2]) if many else 0.0
    return (
        float(math.exp(solution[0])),
        float(grid[index]),
        float(solution[1]),
        c4,
        ss,
        at_edge,
    )


# ── 카드 ──────────────────────────────────────────────────────────────────

#: 카드의 모델 파라미터 벌 이름 — 덱(`deck.garofalo` · `deck.norton`)이 이 이름의 벌을 읽는다.
NORTON_SET = "norton (creep.law)"
GAROFALO_SET = "garofalo (creep.law)"


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 결과 → 모델 파라미터 블록. Norton 벌은 늘, Garofalo 벌은 맞췄고 멱법칙이 아닐
    때만 — 끝에 붙은 Garofalo 를 덱이 고르면 Norton 과 같은 식을 더 나쁜 조건으로 낸다."""
    if "norton_a" not in values:
        raise ValueError("이 묶음에 크리프 식이 없습니다.")
    rows: list[dict[str, Any]] = [
        {"set": NORTON_SET, "group": NORTON_SET, "name": "A", "value": values["norton_a"],
         "unit": "1/(s.Pa^n)"},
        {"set": NORTON_SET, "group": NORTON_SET, "name": "n", "value": values["norton_n"],
         "unit": "1"},
    ]  # fmt: skip
    if "activation_energy" in values:
        rows.append(
            {
                "set": NORTON_SET,
                "group": NORTON_SET,
                "name": "Q",
                "value": values["activation_energy"],
                "unit": "J/mol",
            }
        )
    garofalo = "garofalo_c1" in values and not detail.get("garofalo_at_edge")
    if garofalo:
        for name, key, unit in (
            ("C1", "garofalo_c1", "1/s"),
            ("C2", "garofalo_c2", "1/Pa"),
            ("C3", "garofalo_c3", "1"),
            ("C4", "garofalo_c4", "K"),
        ):
            rows.append(
                {
                    "set": GAROFALO_SET,
                    "group": GAROFALO_SET,
                    "name": name,
                    "value": values[key],
                    "unit": unit,
                }
            )
    return {
        "model_params": {
            "values": {
                "sets": 2 if garofalo else 1,
                "models": "norton, garofalo" if garofalo else "norton",
            },
            "rows": rows,
            "notes": list(warnings),
        }
    }
