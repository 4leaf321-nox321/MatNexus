"""응력-변형률 곡선이 **잰 곡선처럼 생겼나** — 덱 카드에서 복원한 곡선을 알아본다(2026-11-17).

실측(HWAX 연결): 해석 덱의 소성 표(*MAT_024 의 LCSS)에서 복원한 곡선이 시험으로 올라와 실측처럼
쓰였다. 시험에는 곡선의 출처를 적는 칸이 없었고, 받는 쪽은 그것을 가를 수 없었다. 출처 칸
(`TestRun.curve_origin`)이 사람이 적는 답이라면, 이 점검은 **곡선 모양이 말하는 것**이다 — 둘이
어긋나면 사람에게 묻는다. **막지 않는다**(사용자 결정: 경고만).

## 무엇을 보나

    첫 점 응력        소성 표는 항복에서 시작한다(변형률 0 에 σy). 잰 공칭 곡선은 원점 근처다
    꺾임               두 직선으로 맞춰 꺾임 앞 · 뒤 기울기를 잰다. 잰 곡선은 탄성 → 소성에서
                       기울기가 크게 꺾인다. 소성 표에는 꺾임이 없다
    초기 기울기/영률   탄성 구간이 곡선에 있으면 영률에 가깝다(크로스헤드 변형률이면 그
                       몇 분의 일)
    꺾임 뒤 기울기/영률 경화 기울기는 영률의 몇 % 다. 영률에 가까우면 그 꺾임은 항복이 아니다
    점 사이 직선성     표에서 다시 만든 곡선은 점 사이가 정확히 직선이다 — 잰 곡선에는
                       잡음이 있다

기준값은 **잠정**이다(아래 상수). 덱 복원 곡선을 운영에서 모아 맞춘다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

#: 받는 열 — 곡선 파일에서 읽은 목록(빈 칸 None)이나 배열.
Values = Sequence[float | None] | npt.NDArray[np.float64]

Verdict = Literal["ok", "info", "warn"]
Shape = Literal["nominal", "plastic_table", "rebuilt", "unclear"]

#: 첫 점 응력이 최대의 이만큼 이상이면 원점에서 시작하지 않는 곡선이다(잠정). 연강처럼 σy/UTS
#: 가 0.3 안팎인 재료의 소성 표도 걸리게 0.2 로 둔다 — 잰 곡선의 예하중은 몇 % 다.
FIRST_POINT_WARN = 0.20
#: 이만큼 이상이면 원점에서 떨어져 있다 — 예하중 · 잘린 앞부분일 수 있다.
FIRST_POINT_INFO = 0.05
#: 꺾임 뒤 기울기 ÷ 앞 기울기가 이만큼 이상이면 꺾임이 없다(잠정).
NO_KNEE_RATIO = 0.5
#: 초기 기울기 ÷ 영률 — 이 아래면 탄성 구간이 곡선에 거의 없다.
INITIAL_LOW = 0.10
#: 이 아래면 크로스헤드 변형률 · 장비 컴플라이언스로 흔한 범위.
INITIAL_SOFT = 0.50
#: 이 위면 변형률 단위(% · 1)를 의심한다.
INITIAL_HIGH = 2.0
#: 꺾임 뒤 기울기 ÷ 영률 — 이 위면 꺾임이 항복이 아니다.
POST_KNEE_HIGH = 0.30
#: 점 셋이 이 상대 오차 안에서 한 직선에 있으면 「정확히 직선」(표에서 다시 만든 곡선).
COLLINEAR_TOLERANCE = 1e-6
#: 이웃 점 셋 중 이만큼이 정확히 직선이면 표에서 다시 만든 곡선일 수 있다.
PIECEWISE_SHARE = 0.80
#: 초기 기울기는 최대 응력의 이 몫 아래 점들로 잰다 — 두 직선 맞춤은 탄성 구간의 점이 몇
#: 개뿐이면 (변형률을 고르게 나눈 곡선) 꺾임을 경화 구간에서 찾는다.
INITIAL_SHARE = 0.30
#: 첫 점이 높을 때 — 첫 점 뒤 몇 점의 기울기 ÷ 원점에서 첫 점까지의 기울기(할선). 이만큼
#: 이상이면 원점을 지나는 탄성 직선이 첫 점 뒤로도 이어진다(앞부분만 잘린 잰 곡선). 그 아래면
#: 첫 점에서 바로 경화로 눕는다 — 탄성 구간이 없는 곡선이다. 개발 DB 실측(2026-11-17): 앞부분이
#: 잘린 SPCC 는 0.35, 항복점에서 시작하는 데모 곡선(SCATTER_DP600) 12건은 0.01 안팎.
CONTINUES_RATIO = 0.10
#: 첫 점 뒤 기울기를 잴 점 — 응력이 (최대 - 첫 점)의 이 몫만큼 오를 때까지(적어도 3점).
START_SHARE = 0.15
#: 꺾임을 찾을 때 쓰는 점의 최대 수 — 넘으면 고르게 솎는다.
KNEE_POINTS = 400
#: 점이 이보다 적으면 모양을 말하지 않는다.
MIN_POINTS = 6


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    verdict: Verdict
    message: str
    value: float | None = None


@dataclass(frozen=True)
class Quality:
    checks: tuple[Check, ...]
    shape: Shape
    """`nominal` 원점에서 시작해 꺾이는 공칭 곡선 · `plastic_table` 항복에서 시작하는 소성 표
    모양 · `rebuilt` 점 사이가 정확히 직선(표에서 다시 만든 곡선) · `unclear` 말할 수 없다."""
    initial_slope: float | None = None
    post_knee_slope: float | None = None
    knee_strain: float | None = None
    knee_stress: float | None = None
    points: int = 0


def _clean(strain: Values, stress: Values) -> tuple[np.ndarray, np.ndarray]:
    pairs = [
        (float(e), float(s))
        for e, s in zip(strain, stress, strict=False)
        if e is not None and s is not None and np.isfinite(e) and np.isfinite(s)
    ]
    if not pairs:
        return np.array([]), np.array([])
    data = np.array(pairs)
    return data[:, 0], data[:, 1]


def _line(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """기울기와 잔차 제곱합."""
    if len(x) < 2 or float(np.ptp(x)) == 0.0:
        return 0.0, float("inf")
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (slope * x + intercept)
    return float(slope), float(residual @ residual)


def _knee(x: np.ndarray, y: np.ndarray) -> tuple[int, float, float] | None:
    """두 직선 맞춤 — (꺾인 자리, 앞 기울기, 뒤 기울기). 잔차 합이 가장 작은 자리."""
    if len(x) > KNEE_POINTS:
        pick = np.linspace(0, len(x) - 1, KNEE_POINTS).astype(int)
        x, y = x[pick], y[pick]
    best: tuple[float, int, float, float] | None = None
    for k in range(2, len(x) - 2):
        s1, r1 = _line(x[: k + 1], y[: k + 1])
        s2, r2 = _line(x[k:], y[k:])
        total = r1 + r2
        if best is None or total < best[0]:
            best = (total, k, s1, s2)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _piecewise_share(x: np.ndarray, y: np.ndarray) -> float:
    """이웃 점 셋이 정확히 한 직선 위에 있는 몫 — 표에서 선형 보간한 곡선이면 1 에 가깝다."""
    if len(x) < 3 or float(np.ptp(x)) == 0.0 or float(np.ptp(y)) == 0.0:
        return 0.0
    # 두 축을 0~1 로 — 원래 단위로 재면 응력 축이 변형률 축보다 10¹¹ 배 길어 모든 선분이 거의
    # 수직이고, 잡음 있는 잰 곡선도 「정확히 직선」 이 된다.
    x = (x - x.min()) / np.ptp(x)
    y = (y - y.min()) / np.ptp(y)
    dx1, dy1 = x[1:-1] - x[:-2], y[1:-1] - y[:-2]
    dx2, dy2 = x[2:] - x[1:-1], y[2:] - y[1:-1]
    cross = np.abs(dx1 * dy2 - dy1 * dx2)
    scale = np.hypot(dx1, dy1) * np.hypot(dx2, dy2)
    usable = scale > 0
    if not usable.any():
        return 0.0
    return float(np.mean(cross[usable] / scale[usable] < COLLINEAR_TOLERANCE))


def assess(
    strain: Values,
    stress: Values,
    *,
    reference_modulus: float | None = None,
) -> Quality:
    """공칭 변형률 · 응력(SI) → 점검. `reference_modulus` 는 재료에 적어 둔 영률(Pa)."""
    x, y = _clean(strain, stress)
    checks: list[Check] = []
    if len(x) < MIN_POINTS:
        checks.append(
            Check(
                "points",
                "점 수",
                "info",
                f"점이 {len(x)}개뿐이라 모양을 말하지 않습니다.",
                len(x),
            )
        )
        return Quality(checks=tuple(checks), shape="unclear", points=len(x))
    top = int(np.argmax(y))
    peak = float(y[top])
    if peak <= 0:
        checks.append(Check("points", "점 수", "info", "응력이 0 이하뿐입니다.", None))
        return Quality(checks=tuple(checks), shape="unclear", points=len(x))

    first = float(y[0]) / peak
    # **첫 점 뒤로 원점을 지나는 탄성 직선이 이어지나** — 앞부분만 잘린 잰 곡선(첫 점이
    # 탄성 구간 중간)과 탄성 구간이 없는 곡선(첫 점이 항복점 · 변형률 0 에 σy)을 가른다.
    # 영률 없이 잰다.
    rise = float(y[0]) + START_SHARE * (peak - float(y[0]))
    head = max(int(np.count_nonzero(y[: top + 1] <= rise)), 3)
    start_slope = _line(x[:head], y[:head])[0]
    secant = float(y[0]) / float(x[0]) if float(x[0]) > 0 else float("inf")
    continues = secant > 0 and start_slope / secant >= CONTINUES_RATIO
    if first >= FIRST_POINT_WARN and not continues:
        checks.append(
            Check(
                "first_point",
                "첫 점 응력",
                "warn",
                f"첫 점 응력이 최대의 {first:.0%} 이고 첫 점에서 바로 경화로 눕습니다 — 탄성 "
                "구간 없이 시작하는 곡선입니다. 소성 표(항복에서 시작)를 공칭 곡선처럼 "
                "올린 것일 "
                "수 있습니다.",
                first,
            )
        )
    elif first >= FIRST_POINT_INFO:
        checks.append(
            Check(
                "first_point",
                "첫 점 응력",
                "info",
                f"첫 점 응력이 최대의 {first:.0%} 입니다 — "
                + (
                    "원점을 지나는 탄성 직선 위에서 시작해 앞부분이 잘렸거나 예하중이 있는 "
                    "것으로 "
                    "보입니다."
                    if continues
                    else "예하중이나 잘린 앞부분일 수 있습니다."
                ),
                first,
            )
        )
    else:
        checks.append(
            Check("first_point", "첫 점 응력", "ok", "원점 근처에서 시작합니다.", first)
        )

    # 꺾임은 최대 응력까지에서 본다 — 그 뒤는 네킹이라 기울기가 음수로 간다.
    upto = max(top + 1, MIN_POINTS)
    knee = _knee(x[:upto], y[:upto])
    s1 = s2 = None
    knee_at: tuple[float, float] | None = None
    ratio: float | None = None
    low = y[:upto] <= INITIAL_SHARE * peak
    measured_start = int(np.count_nonzero(low)) >= 2 and bool(low[0])
    if knee is not None and knee[1] > 0:
        index, s1, s2 = knee
        if measured_start:
            # 탄성 구간이 곡선에 있으면 그 점들의 기울기가 초기 기울기다.
            lead = int(np.argmin(low)) if not low.all() else len(low)
            s1 = _line(x[: max(lead, 2)], y[: max(lead, 2)])[0] or s1
        sampled = (
            np.linspace(0, upto - 1, KNEE_POINTS).astype(int) if upto > KNEE_POINTS else None
        )
        at = int(sampled[index]) if sampled is not None else index
        knee_at = (float(x[at]), float(y[at]))
        ratio = s2 / s1
        if ratio >= NO_KNEE_RATIO:
            checks.append(
                Check(
                    "knee",
                    "꺾임",
                    "warn",
                    f"꺾임 뒤 기울기가 앞 기울기의 {ratio:.0%} 입니다 — "
                    "탄성에서 소성으로 꺾이지 않습니다. "
                    "탄성 구간이 없는 곡선(소성 표 · 덱 복원)이거나 탄성만 있는 곡선입니다.",
                    ratio,
                )
            )
        else:
            checks.append(
                Check(
                    "knee",
                    "꺾임",
                    "ok",
                    f"꺾임 뒤 기울기가 앞 기울기의 {ratio:.1%} 입니다.",
                    ratio,
                )
            )
    else:
        checks.append(
            Check("knee", "꺾임", "info", "앞 기울기가 0 이하라 꺾임을 못 찾았습니다.")
        )

    initial = s1 / reference_modulus if s1 is not None and reference_modulus else None
    if initial is not None:
        if initial < INITIAL_LOW:
            verdict: Verdict = "warn"
            said = (
                f"초기 기울기가 영률의 {initial:.1%} 입니다 — "
                "탄성 구간이 곡선에 거의 없습니다."
            )
        elif initial < INITIAL_SOFT:
            verdict = "info"
            said = (
                f"초기 기울기가 영률의 {initial:.0%} 입니다 — 크로스헤드 변형률 · 장비 "
                "컴플라이언스면 흔한 범위입니다."
            )
        elif initial > INITIAL_HIGH:
            verdict = "warn"
            said = (
                f"초기 기울기가 영률의 {initial:.1f}배입니다 — "
                "변형률 단위(% · 1)를 확인하세요."
            )
        else:
            verdict = "ok"
            said = f"초기 기울기가 영률의 {initial:.0%} 입니다."
        checks.append(Check("initial_slope", "초기 기울기 / 영률", verdict, said, initial))
    post = s2 / reference_modulus if s2 is not None and reference_modulus else None
    if post is not None:
        checks.append(
            Check(
                "post_knee_slope",
                "꺾임 뒤 기울기 / 영률",
                "warn" if post > POST_KNEE_HIGH else "ok",
                (
                    f"꺾임 뒤 기울기가 영률의 {post:.0%} 입니다 — 그 꺾임은 항복이 아닙니다."
                    if post > POST_KNEE_HIGH
                    else f"꺾임 뒤 기울기가 영률의 {post:.1%} 입니다(경화)."
                ),
                post,
            )
        )

    share = _piecewise_share(x, y)
    if share >= PIECEWISE_SHARE:
        checks.append(
            Check(
                "piecewise",
                "점 사이 직선성",
                "info",
                f"이웃 점 셋의 {share:.0%} 가 정확히 한 직선 위에 있습니다 — "
                "표에서 다시 만든 곡선일 수 "
                "있습니다(잰 곡선에는 잡음이 있습니다).",
                share,
            )
        )

    flat = ratio is not None and ratio >= NO_KNEE_RATIO
    soft = initial is not None and initial < INITIAL_LOW
    missing_elastic = first >= FIRST_POINT_WARN and not continues
    if missing_elastic or (first >= FIRST_POINT_WARN and soft):
        shape: Shape = "plastic_table"
    elif share >= PIECEWISE_SHARE:
        shape = "rebuilt"
    elif ratio is not None and not flat and (first < FIRST_POINT_INFO or continues):
        shape = "nominal"
    else:
        shape = "unclear"
    return Quality(
        checks=tuple(checks),
        shape=shape,
        initial_slope=s1,
        post_knee_slope=s2,
        knee_strain=knee_at[0] if knee_at else None,
        knee_stress=knee_at[1] if knee_at else None,
        points=len(x),
    )
