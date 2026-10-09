"""가공경화지수 n — 진응력-진변형률의 로그-로그 기울기(ASTM E646 · ISO 10275).

    σ = K · ε^n   →   ln σ = ln K + n · ln ε

판재 성형성의 첫 지표다(n 이 클수록 국부 넥킹 전에 고르게 늘어난다). 카탈로그 키는
`mechanical.monotonic_strain_hardening_exponent`(단조 변형경화지수) — 피로의 순환
경화지수(n′)와 다른 값이다.

## 무엇으로 재나

공칭 곡선(`strain_engineering` · `stress_engineering`)을 받아 여기서 진값으로 바꾼다 —
ε = ln(1+e), σ = S(1+e). 진소성 단계(order 90)의 열을 기다리지 않는 이유: 그 단계는 네킹
경계와 항복 정의를 사람이 정하고, n 은 그것과 상관없이 규격이 정한 구간에서 잰다.

**구간**은 공칭 변형률 10~20%가 기본이다. 균일 연신율(최대하중 변형률)이 상한보다 작으면
거기까지만 쓴다 — 그 뒤는 넥킹이라 σ = S(1+e) 가 성립하지 않는다(두 규격이 같은 규칙이다).

**변형률의 기준**은 고른다 — 전체 진변형률(ASTM E646 의 기본)과 탄성분 σ/E 를 뺀 진소성
변형률. 둘은 n 이 몇 % 다르고, 어느 쪽인지 값 옆에 남는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from matcore.processing import Frame, Scalar, StepResult
from matcore.processing.tensile import STRAIN, STRESS

#: 회귀에 쓸 최소 점 수 — 이보다 적으면 기울기가 잡음에 끌려간다.
MIN_POINTS = 5
DEFAULT_LOWER = 0.10
DEFAULT_UPPER = 0.20
BASES = ("total", "plastic")


@dataclass(frozen=True)
class Fitted:
    n: float | None
    strength_coefficient: float | None
    r_squared: float | None
    points: int
    lower: float
    upper: float
    capped: bool
    """균일 연신율에서 상한을 줄였나."""
    why: str | None = None


def fit(
    strain: np.ndarray,
    stress: np.ndarray,
    *,
    lower: float = DEFAULT_LOWER,
    upper: float = DEFAULT_UPPER,
    uniform: float | None = None,
    basis: str = "total",
    youngs_modulus: float | None = None,
) -> Fitted:
    """공칭 곡선 → n · K. **못 믿을 값은 안 낸다** — `why` 가 까닭이다."""
    capped = uniform is not None and math.isfinite(uniform) and uniform < upper
    top = float(uniform) if capped and uniform is not None else upper

    def nothing(why: str, points: int = 0) -> Fitted:
        return Fitted(None, None, None, points, lower, top, capped, why)

    if not 0.0 < lower < top:
        return nothing(
            f"구간이 비었습니다 — 하한 {lower:.3g} 이 상한 {top:.3g} 보다 작아야 합니다"
            + (" (균일 연신율이 하한보다 작습니다)." if capped else ".")
        )
    if basis == "plastic" and (youngs_modulus is None or youngs_modulus <= 0.0):
        return nothing("진소성변형률로 재려면 탄성계수가 있어야 합니다.")
    e = np.asarray(strain, dtype=float)
    s = np.asarray(stress, dtype=float)
    keep = np.isfinite(e) & np.isfinite(s) & (e >= lower) & (e <= top) & (s > 0.0)
    e, s = e[keep], s[keep]
    true_strain = np.log1p(e)
    true_stress = s * (1.0 + e)
    if basis == "plastic":
        assert youngs_modulus is not None
        true_strain = true_strain - true_stress / youngs_modulus
    usable = true_strain > 0.0
    true_strain, true_stress = true_strain[usable], true_stress[usable]
    points = len(true_strain)
    if points < MIN_POINTS:
        return nothing(
            f"구간 안의 점이 {points}개입니다 — {MIN_POINTS}개 이상이어야 합니다.", points
        )
    x, y = np.log(true_strain), np.log(true_stress)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    spread = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - float(np.sum((y - predicted) ** 2)) / spread if spread > 0 else 0.0
    return Fitted(
        float(slope), float(math.exp(intercept)), r_squared, points, lower, top, capped
    )


def n_value(frame: Frame, options: dict[str, Any]) -> StepResult:
    """구간에서 n 을 잰다. **곡선은 안 바뀐다.** 못 믿을 값은 안 내고 까닭을 남긴다."""
    strain = frame.require(str(options.get("strain") or STRAIN), what="변형률")
    stress = frame.require(str(options.get("stress") or STRESS), what="응력")
    basis = str(options.get("basis") or "total")
    uniform = options.get("uniform_elongation")
    youngs = options.get("youngs_modulus")
    fitted = fit(
        strain,
        stress,
        lower=float(options.get("lower_strain", DEFAULT_LOWER)),
        upper=float(options.get("upper_strain", DEFAULT_UPPER)),
        uniform=float(uniform) if isinstance(uniform, int | float) else None,
        basis=basis,
        youngs_modulus=float(youngs) if isinstance(youngs, int | float) else None,
    )
    notes = [
        f"공칭 변형률 {fitted.lower:.3g}~{fitted.upper:.3g} 구간의 점 {fitted.points}개로 "
        f"ln σ - ln ε 에 직선을 맞췄습니다("
        + ("전체 진변형률, ASTM E646)." if basis == "total" else "진소성변형률 — σ/E 를 뺌).")
    ]
    if fitted.capped:
        notes.append(
            f"균일 연신율(최대하중 변형률) {fitted.upper:.3g} 이 상한보다 작아 거기까지만 "
            "썼습니다 — 그 뒤는 넥킹이라 진응력 변환이 성립하지 않습니다."
        )
    scalars = [Scalar("n_point_count", "n 구간 점 수", float(fitted.points), "1")]
    if fitted.n is None:
        notes.append(f"**n 을 내지 않았습니다** — {fitted.why}")
    else:
        assert fitted.strength_coefficient is not None and fitted.r_squared is not None
        scalars[:0] = [
            Scalar("n_value", "가공경화지수 n", fitted.n, "1"),
            Scalar("n_strength_coefficient", "강도계수 K", fitted.strength_coefficient, "Pa"),
            Scalar("n_r_squared", "n 구간 R²", fitted.r_squared, "1"),
        ]
    return StepResult(frame=frame, notes=tuple(notes), scalars=tuple(scalars))
