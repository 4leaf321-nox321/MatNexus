"""곡선의 **처음 기울기** — 탄성률을 규격마다 다른 방법으로 잰다(2026-10-16).

굽힘(ISO 178 · ASTM D790 · D6272 · D7264 · ISO 14125)과 압축(ISO 604 · D695 · ISO 7743 ·
ISO 844 · D1621)이 탄성률을 재는 방법이 저마다 다르다. 같은 곡선에서도 방법마다 몇 % 갈린다
— 어느 쪽이 옳은지는 규격이 정하므로 **방법을 고르게 두고, 고른 방법과 구간을 결과에 남긴다.**

    chord          현 — 두 변형률(ε₁ · ε₂)의 응력을 잇는 기울기(ISO 178 · ISO 604: 0.05~0.25%)
    regression     회귀 — 두 변형률 사이 점들의 최소제곱 기울기
    secant         할선 — 원점에서 ε₂ 의 응력까지(고무 · 폼의 「몇 % 에서의 탄성률」)
    tangent        접선 — 처음 직선 구간의 **가장 가파른** 기울기(ASTM D790 · D695)
    stress_window  응력 띠 — 최대 응력의 a~b 비율 사이 회귀(칩 · 세라믹처럼 변형률이 작은 것)

여기는 숫자만 다룬다 — 단위 · 열 이름 · 무엇의 탄성률인지는 부르는 쪽(확장)이 안다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

METHODS = ("chord", "regression", "secant", "tangent", "stress_window")

#: 회귀에 쓰는 최소 점 수 — 둘이면 잔차가 늘 0 이라 맞았는지 알 수 없다.
MIN_POINTS = 3


class SlopeError(ValueError):
    """기울기를 못 냈다. 메시지는 **사람이 읽는다** — 무엇을 고치면 되는지 적는다."""


@dataclass(frozen=True)
class Slope:
    value: float
    """기울기(응력 ÷ 변형률)."""
    low: float
    """쓴 구간의 시작(변형률)."""
    high: float
    """쓴 구간의 끝(변형률)."""
    points: int
    """구간 안의 점 수(현 · 할선은 보간한 두 점)."""
    r2: float | None = None
    """회귀일 때의 결정계수. 현 · 할선은 없다."""
    indices: tuple[int, int] = (0, 0)
    """원래 배열에서 쓴 점의 [시작, 끝) — 같은 구간으로 다른 열(하중-처짐)의 기울기를 낼 때."""


def rising(strain: np.ndarray, stress: np.ndarray) -> int:
    """**최대 응력까지**의 점 수 — 기울기는 오르는 가지에서만 잰다. 파단 뒤 떨어지는 꼬리가
    섞이면 응력 띠 · 접선이 엉뚱한 자리를 고른다."""
    if len(stress) == 0:
        return 0
    return int(np.argmax(stress)) + 1


def _interp(x: np.ndarray, y: np.ndarray, at: float) -> float:
    order = np.argsort(x, kind="stable")
    return float(np.interp(at, x[order], y[order]))


def _fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    total = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - float(np.sum((y - predicted) ** 2)) / total if total > 0 else 1.0
    return float(slope), r2


def measure(
    strain: np.ndarray,
    stress: np.ndarray,
    *,
    method: str,
    low: float = 0.0005,
    high: float = 0.0025,
    band_low: float = 0.1,
    band_high: float = 0.4,
    tangent_width: float = 0.001,
) -> Slope:
    """오르는 가지에서 고른 방법으로 기울기를 잰다. 못 내면 `SlopeError`."""
    if method not in METHODS:
        raise SlopeError(
            f"모르는 방법입니다: {method} — {', '.join(METHODS)} 중에서 고르세요."
        )
    strain = np.asarray(strain, dtype=np.float64)
    stress = np.asarray(stress, dtype=np.float64)
    end = rising(strain, stress)
    x, y = strain[:end], stress[:end]
    if len(x) < MIN_POINTS:
        raise SlopeError(f"최대 응력까지 점이 {len(x)}개뿐입니다 — 기울기를 잴 수 없습니다.")

    if method in ("chord", "secant"):
        if high <= (0.0 if method == "secant" else low):
            raise SlopeError(f"구간이 거꾸로입니다: {low} ~ {high}")
        if float(np.max(x)) < high:
            raise SlopeError(
                f"곡선이 구간 끝 변형률 {high:.4g} 까지 안 갑니다"
                f"(최대 {float(np.max(x)):.4g}) — "
                "구간을 줄이거나 다른 방법을 고르세요."
            )
        start = 0.0 if method == "secant" else low
        y_low = 0.0 if method == "secant" else _interp(x, y, low)
        value = (_interp(x, y, high) - y_low) / (high - start)
        inside = np.flatnonzero((x >= start) & (x <= high))
        span = (int(inside[0]), int(inside[-1]) + 1) if len(inside) else (0, 0)
        return Slope(value=value, low=start, high=high, points=2, indices=span)

    if method == "regression":
        inside = np.flatnonzero((x >= low) & (x <= high))
        if len(inside) < MIN_POINTS:
            raise SlopeError(
                f"변형률 {low:.4g} ~ {high:.4g} 사이에 점이 {len(inside)}개뿐입니다 — "
                f"{MIN_POINTS}개 이상이어야 합니다."
            )
        value, r2 = _fit(x[inside], y[inside])
        return Slope(
            value=value,
            low=float(x[inside[0]]),
            high=float(x[inside[-1]]),
            points=len(inside),
            r2=r2,
            indices=(int(inside[0]), int(inside[-1]) + 1),
        )

    if method == "stress_window":
        if not 0 <= band_low < band_high <= 1:
            raise SlopeError(f"응력 띠는 0~1 사이 비율이어야 합니다: {band_low} ~ {band_high}")
        peak = float(np.max(y))
        inside = np.flatnonzero((y >= band_low * peak) & (y <= band_high * peak))
        if len(inside) < MIN_POINTS:
            raise SlopeError(
                f"최대 응력의 {band_low:.0%}~{band_high:.0%} 사이에 점이 "
                f"{len(inside)}개뿐입니다."
            )
        # 띠 안의 **처음 이어진 구간**만 — 오르내림이 있는 곡선에서 뒤쪽 점이 섞이지 않게.
        breaks = np.flatnonzero(np.diff(inside) > 1)
        if len(breaks):
            inside = inside[: breaks[0] + 1]
        if len(inside) < MIN_POINTS:
            raise SlopeError("응력 띠 안의 처음 이어진 구간에 점이 너무 적습니다.")
        value, r2 = _fit(x[inside], y[inside])
        return Slope(
            value=value,
            low=float(x[inside[0]]),
            high=float(x[inside[-1]]),
            points=len(inside),
            r2=r2,
            indices=(int(inside[0]), int(inside[-1]) + 1),
        )

    # tangent — 너비 w 의 창을 오르는 가지의 처음 절반(최대 응력의 50% 까지)에서 밀며 가장
    # 가파른 회귀 기울기. 토우(처음 눕는 구간)를 건너뛰고 직선 구간을 찾는다(D790 의 「접선」).
    if tangent_width <= 0:
        raise SlopeError("접선 창 너비는 0 보다 커야 합니다.")
    reach = np.flatnonzero(y <= 0.5 * float(np.max(y)))
    limit = int(reach[-1]) + 1 if len(reach) else len(x)
    best: Slope | None = None
    starts = np.linspace(
        float(x[0]), max(float(x[limit - 1]) - tangent_width, float(x[0])), 40
    )
    for start in starts:
        inside = np.flatnonzero((x >= start) & (x <= start + tangent_width))
        inside = inside[inside < limit]
        if len(inside) < MIN_POINTS:
            continue
        value, r2 = _fit(x[inside], y[inside])
        if best is None or value > best.value:
            best = Slope(
                value=value,
                low=float(x[inside[0]]),
                high=float(x[inside[-1]]),
                points=len(inside),
                r2=r2,
                indices=(int(inside[0]), int(inside[-1]) + 1),
            )
    if best is None:
        raise SlopeError(
            f"접선 창(변형률 너비 {tangent_width:.4g}) 안에 점이 {MIN_POINTS}개 이상인 자리가 "
            "없습니다 — 창을 넓히세요."
        )
    return best


__all__ = ["METHODS", "MIN_POINTS", "Slope", "SlopeError", "measure", "rising"]
