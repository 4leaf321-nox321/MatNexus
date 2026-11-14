"""곡선의 **처음 기울기** — 탄성률을 규격마다 다른 방법으로 잰다(2026-10-16).

굽힘(ISO 178 · ASTM D790 · D6272 · D7264 · ISO 14125)과 압축(ISO 604 · D695 · ISO 7743 ·
ISO 844 · D1621)이 탄성률을 재는 방법이 저마다 다르다. 같은 곡선에서도 방법마다 몇 % 갈린다
— 어느 쪽이 옳은지는 규격이 정하므로 **방법을 고르게 두고, 고른 방법과 구간을 결과에 남긴다.**

    chord          현 — 두 변형률(ε₁ · ε₂)의 응력을 잇는 기울기(ISO 178 · ISO 604: 0.05~0.25%)
    regression     회귀 — 두 변형률 사이 점들의 최소제곱 기울기
    secant         할선 — 원점에서 ε₂ 의 응력까지(고무 · 폼의 「몇 % 에서의 탄성률」)
    tangent        접선 — **가장 가파른 처음 직선 구간**의 기울기(ASTM D790 · D695)
    stress_window  응력 띠 — 최대 응력의 a~b 비율 사이 회귀(칩 · 세라믹처럼 변형률이 작은 것)

여기는 숫자만 다룬다 — 단위 · 열 이름 · 무엇의 탄성률인지는 부르는 쪽(확장)이 안다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

METHODS = ("chord", "regression", "secant", "tangent", "stress_window")

#: 회귀에 쓰는 최소 점 수 — 인장 탄성률과 같다(2026-11-14, VOC 43). 셋이면 잡음 한 점이
#: 기울기를 좌우하고, R² 도 거의 늘 높게 나와 맞았는지 알 수 없었다.
MIN_POINTS = 5


#: 문턱에 「닿았다」 고 보는 연속 점 수(2026-11-14, VOC 43 후속) — 회귀 최소 점 수와 같다.
REACH_RUN = MIN_POINTS

#: 접선에서 가장 가파른 창과 「구별 안 된다」 고 보는 폭 — 기울기 표준오차의 배수.
PLATEAU_SIGMA = 2.0
#: 접선이 묶는 창의 최소 수 — 못 채우면 가장 가파른 창부터 이만큼을 덮는다.
PLATEAU_MIN_WINDOWS = 3


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
    # **빈 칸(NaN)은 최대가 아니다**(2026-11-14 검토) — `np.argmax` 는 첫 NaN 을 최대로 쳐
    # 곡선을 거기서 잘랐다. 인장 `_peak_index` 와 같은 처리다.
    finite = np.isfinite(stress)
    if not finite.any():
        return 0
    return int(np.argmax(np.where(finite, stress, -np.inf))) + 1


def first_reach(values: np.ndarray, threshold: float, run: int = REACH_RUN) -> int | None:
    """문턱을 **`run` 점 연속으로** 넘은 첫 자리(그 연속의 첫 점). 못 넘으면 `None`.

    한 점만 넘어도 도달로 봤더니, 하중이 한 점 튀어 위 끝 문턱을 일찍 넘으면 구간이 거기서
    끊기고 그 점이 기울기를 끌어올렸다 — +20 % 로 튄 점 하나가 든 500점 곡선의 13~16 % 가
    5 % 넘게 틀렸고 최악은 +45 % 였다(2026-11-14 실측). 다섯 점 연속이면 0~2 %, 잡음 없는
    곡선에서는 값이 비트 단위로 같다(오르는 곡선은 첫 도달이 곧 연속의 시작이다).

    곡선 끝이라 연속이 없으면(문턱이 최대 응력 바로 아래) 한 점 첫 도달로 물러선다. 빈
    칸(NaN)은 「안 넘음」 이다.
    """
    above = np.asarray(values) >= threshold
    hits = np.flatnonzero(above)
    if not len(hits):
        return None
    if len(above) >= run:
        full = np.convolve(above.astype(np.int64), np.ones(run, dtype=np.int64), "valid")
        runs = np.flatnonzero(full == run)
        if len(runs):
            return int(runs[0])
    return int(hits[0])


def _slope_error(x: np.ndarray, y: np.ndarray, slope: float) -> float:
    """회귀 기울기의 표준오차. 점이 둘 이하이거나 x 가 안 퍼지면 0."""
    count = len(x)
    spread = float(np.sum((x - np.mean(x)) ** 2))
    if count <= 2 or not spread > 0:
        return 0.0
    intercept = float(np.mean(y) - slope * np.mean(x))
    residual = y - (slope * x + intercept)
    return float(np.sqrt(np.sum(residual**2) / (count - 2) / spread))


def _interp(x: np.ndarray, y: np.ndarray, at: float) -> float:
    keep = np.isfinite(x) & np.isfinite(y)  # 빈 칸은 보간에서 뺀다(2026-11-14 검토)
    order = np.argsort(x[keep], kind="stable")
    return float(np.interp(at, x[keep][order], y[keep][order]))


def _fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """최소제곱 기울기와 R². **응력이 구간 안에서 안 변하면 못 잰다.**

    전에는 분모(응력의 흩어짐)가 0 이면 R² 를 1.0 으로 돌려줘, 응력이 계단처럼 양자화된
    곡선에서 ≈0 GPa 가 「R² 1.0」 으로 저장됐다(2026-11-14, VOC 43).
    """
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        raise SlopeError(
            "구간 안에 빈 칸(숫자가 아닌 값)이 있습니다 — 그 점을 빼고 다시 재세요."
        )
    total = float(np.sum((y - np.mean(y)) ** 2))
    span = float(np.ptp(x))
    eps = float(np.finfo(np.float64).eps)
    count = int(x.size)
    # **퇴화한 구간은 숫자를 내기 전에 막는다** — 인장 `_fit_line` 과 같은 바닥이다(2026-11-14,
    # VOC 43). 절대값으로는 못 막는다(고무는 MPa · 금속은 GPa) — eps 에 데이터 크기를 곱한다.
    x_scale = max(float(np.max(np.abs(x))), span)
    centered = x - float(np.mean(x))
    if (
        not total > 0
        or span <= 0
        or float(np.dot(centered, centered)) <= eps * count * max(x_scale**2, 1e-300)
    ):
        raise SlopeError(
            "구간 안에서 응력(또는 변형률)이 변하지 않습니다 — 기울기를 잴 수 없습니다. "
            "구간을 넓히거나 다른 방법을 고르세요."
        )
    slope, intercept = np.polyfit(x, y, 1)
    y_scale = max(float(np.max(np.abs(y))), 1.0)
    if not np.isfinite(slope) or abs(float(slope)) <= eps * count * y_scale / span:
        raise SlopeError(
            f"기울기가 사실상 0 입니다({float(slope):.3g}) — 응력이 구간 안에서 거의 안 "
            "오릅니다. 구간을 넓히거나 다른 방법을 고르세요."
        )
    predicted = slope * x + intercept
    r2 = 1.0 - float(np.sum((y - predicted) ** 2)) / total
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
    # **숫자인 점을 센다**(2026-11-14 검토) — 변형률 칸이 통째로 비면(NaN) 현 · 할선이 빈
    # 배열을 보간하다 「예상 못 한 오류(ValueError)」 가 됐다.
    usable = int(np.count_nonzero(np.isfinite(x) & np.isfinite(y)))
    if usable < MIN_POINTS:
        raise SlopeError(
            f"최대 응력까지 숫자인 점이 {usable}개뿐입니다(나머지는 빈 칸) — 기울기를 잴 수 "
            "없습니다."
        )

    if method in ("chord", "secant"):
        if high <= (0.0 if method == "secant" else low):
            raise SlopeError(f"구간이 거꾸로입니다: {low} ~ {high}")
        if float(np.nanmax(x)) < high:
            raise SlopeError(
                f"곡선이 구간 끝 변형률 {high:.4g} 까지 안 갑니다"
                f"(최대 {float(np.nanmax(x)):.4g}) — "
                "구간을 줄이거나 다른 방법을 고르세요."
            )
        start = 0.0 if method == "secant" else low
        y_low = 0.0 if method == "secant" else _interp(x, y, low)
        value = (_interp(x, y, high) - y_low) / (high - start)
        inside = np.flatnonzero((x >= start) & (x <= high))
        span = (int(inside[0]), int(inside[-1]) + 1) if len(inside) else (0, 0)
        return Slope(value=value, low=start, high=high, points=2, indices=span)

    if method == "regression":
        inside = np.flatnonzero((x >= low) & (x <= high) & np.isfinite(y))
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
        peak = float(np.nanmax(y))
        if not peak > 0:
            raise SlopeError("최대 응력이 0 이하라 응력 띠를 정할 수 없습니다.")
        # **띠 아래 끝에 처음 닿은 점 ~ 위 끝에 처음 닿은 점 사이를 전부** 쓴다(2026-11-14,
        # VOC 43). 전에는 띠 안의 점을 골라 **처음 이어진 구간**만 썼다 — 잡음이 띠 경계를
        # 넘나들면 그 구간이 서너 점으로 끊겨, 잡음 σ 0.2 MPa 에서 200번 중 117번 못 쟀다.
        # 첫 도달로 정하면 경계 근처의 오르내림이 구간을 자르지 않는다. 「닿았다」 는 다섯 점
        # 연속이다(`first_reach`) — 튄 점 하나가 구간을 끊지 않게.
        first = first_reach(y, band_low * peak)
        last = first_reach(y, band_high * peak)
        if first is None or last is None:  # 최대 응력은 늘 문턱 이상이라 오지 않는 자리다
            raise SlopeError("응력 띠의 문턱에 닿은 점이 없습니다.")
        inside = np.arange(first, last + 1)
        # **빈 칸(NaN)은 뺀다**(2026-11-14 검토) — 구간을 연속 번호로 잡아 그 사이의 빈 칸이
        # 회귀에 들어가 「예상 못 한 오류(LinAlgError)」 가 됐다. 다른 방법(현 · 회귀)은 비교로
        # 골라 빈 칸이 저절로 빠진다 — 같은 곡선에서 응력 띠만 못 재던 것.
        inside = inside[np.isfinite(x[inside]) & np.isfinite(y[inside])]
        if len(inside) < MIN_POINTS:
            raise SlopeError(
                f"최대 응력의 {band_low:.0%} 에 처음 닿은 점부터 {band_high:.0%} 에 처음 닿은 "
                f"점까지가 {len(inside)}개뿐입니다 — {MIN_POINTS}개 이상이어야 합니다. 띠를 "
                "넓히거나 다른 방법을 고르세요."
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

    # tangent — 너비 w 의 창을 오르는 가지의 처음 절반(최대 응력의 50% 까지)에서 밀어 가장
    # 가파른 창을 찾고, **그것과 잡음 안에서 구별 안 되는 창들을 묶어 그 구간 전체를 한 번
    # 회귀한다**(2026-11-14, VOC 44 후속, ADR 0088). 토우(처음 눕는 구간)를 건너뛰고 직선
    # 구간을 찾는다 — D790 의 「가장 가파른 처음 직선 **부분**」.
    #
    # 전에는 가장 가파른 창 하나의 기울기를 그대로 냈다. 잡음이 있으면 늘 잡음이 위로 튄 창이
    # 뽑혀 — 40번 잰 것 중 최고값 — D790 기본 창(0.001)에서 잡음이 최대 응력의 0.1~0.5 % 일
    # 때 +4~+32 % 높았다(실측). 인장 자동 구간이 같은 함정을 겪었다(`tensile.py` 「가장
    # 가파른 창으로 바꿨더니 잡음이 이겼다」).
    if tangent_width <= 0:
        raise SlopeError("접선 창 너비는 0 보다 커야 합니다.")
    reach = np.flatnonzero(y <= 0.5 * float(np.nanmax(y)))
    limit = int(reach[-1]) + 1 if len(reach) else len(x)
    found: list[tuple[float, float, float, float]] = []  # 기울기 · 표준오차 · 창 시작 · 끝
    best: Slope | None = None
    # **창을 놓을 자리는 숫자인 변형률에서 잡는다**(2026-11-14 검토) — 첫 · 끝 점으로 잡아,
    # 끝 점이 빈 칸이면 격자가 `[처음, NaN, …]` 이 되어 창 하나만 보고 그 값을 냈다.
    reached = x[:limit][np.isfinite(x[:limit])]
    if not len(reached):
        raise SlopeError(
            "최대 응력의 50% 까지 변형률이 모두 빈 칸입니다 — 접선을 잴 수 없습니다."
        )
    lowest = float(reached.min())
    starts = np.linspace(lowest, max(float(reached.max()) - tangent_width, lowest), 40)
    for start in starts:
        inside = np.flatnonzero((x >= start) & (x <= start + tangent_width) & np.isfinite(y))
        inside = inside[inside < limit]
        if len(inside) < MIN_POINTS:
            continue
        try:
            value, r2 = _fit(x[inside], y[inside])
        except SlopeError:
            continue  # 응력이 안 변하는 창 — 다음 창을 본다
        found.append(
            (
                value,
                _slope_error(x[inside], y[inside], value),
                float(x[inside[0]]),
                float(x[inside[-1]]),
            )
        )
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
    # 가장 가파른 창과 구별 안 되는 창 — 문턱은 그 창의 표준오차와 창들의 중앙 표준오차 중 큰
    # 쪽의 두 배 아래. 창 하나의 표준오차만 쓰면 점이 일곱 개뿐인 창에서 추정이 흔들려 옛
    # 값으로 되돌아갔고, 중앙값만 쓰면 튄 점이 든 창을 못 걸렀다(실측).
    steepest = max(found, key=lambda one: one[0])
    noise = max(steepest[1], float(np.median([one[1] for one in found])))
    alike = [one for one in found if one[0] >= steepest[0] - PLATEAU_SIGMA * noise]
    # **묶인 창이 셋이 안 되면 가장 가파른 셋을 덮는다** — 잡음 곡선의 0.1~0.7 % 에서 묶이는
    # 창이 그 하나뿐이라 옛 값(+30~+120 %)이 조용히 나왔다(검증 실측). 본체 분포는 그대로였다.
    if len(alike) < PLATEAU_MIN_WINDOWS:
        alike = sorted(found, key=lambda one: -one[0])[:PLATEAU_MIN_WINDOWS]
    low_x = min(one[2] for one in alike)
    high_x = max(one[3] for one in alike)
    inside = np.flatnonzero((x >= low_x) & (x <= high_x) & np.isfinite(y))
    inside = inside[inside < limit]
    try:
        value, r2 = _fit(x[inside], y[inside])
    except SlopeError:
        return best  # 묶은 구간이 안 맞춰지면 가장 가파른 창 하나로 물러선다
    return Slope(
        value=value,
        low=float(x[inside[0]]),
        high=float(x[inside[-1]]),
        points=len(inside),
        r2=r2,
        indices=(int(inside[0]), int(inside[-1]) + 1),
    )


__all__ = ["METHODS", "MIN_POINTS", "Slope", "SlopeError", "measure", "rising"]
