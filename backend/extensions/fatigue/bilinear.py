"""2구간 S-N — 로그-로그에서 **꺾이는** 수명선도(VOC 61, 2026-11-14).

    N ≤ Nc1   S = A1 · N^b1
    N > Nc1   S = A1 · Nc1^(b1 - b2) · N^b2       (꺾임점에서 이어진다)

HyperLife 의 「Slope-intercept, 2-segment」 · OptiStruct `MATFAT` · Nastran `MATFTG` 의
`SRI1 · B1 · NC1 · B2` 와 같은 꼴이다(SRI1 = 2·A1, 범위 절편). 한 직선(`sn.py`)은 그대로
둔다.

## 꺾임점은 반복 최적화가 아니라 전수 탐색으로

VOC 를 올린 사람의 걱정은 「플랫폼 안에서 여러 번 계산해 값을 찾을 수 있을까」 였다(로컬에서는
첫 값 근처 ±0.25 자릿수 안에서만 검증). 꺾임을 정해 두면 나머지는 **선형**이다 — 꺾임 x_k 에서

    log N = y_k + c1·max(x - x_k, 0) + c2·min(x - x_k, 0),   x = log S

세 계수의 최소제곱이 한 번에 풀린다(이어짐은 식의 꼴이 보장한다). 그래서 x_k 를 허용 범위
전체에서 촘촘히 훑고(`GRID`), 가장 좋은 칸 둘레를 한 번 더 다듬는다. 초기값이 없어 수렴 문제가
없고 같은 점이면 늘 같은 답이다 — 근처만 보는 국소 탐색의 한계가 없다.

**수명을 응력에 회귀한다**(ASTM E739, `sn.py` 와 같다). 런아웃은 뺀다 — 수명이 아니라
하한이다.

## 2구간이 늘 조금은 낫다 — 그래서 판정을 같이 낸다

계수가 많으니 2구간의 오차는 한 직선보다 같거나 작다. 직선인 시험군에도 흩어짐에 맞춘 가짜
꺾임이 나온다. 그래서 한 직선과 견준 F 검정(자유도 2 · n-4)과 BIC 를 함께 내고, 둘 다 2구간
쪽이 아니면 「2구간 근거 약함 — 한 직선 권장」 을 단다. **막지 않는다** — 고르는 것은
사람이다(사용자 결정 2026-11-14). F 검정은 꺾임을 데이터로 정했으므로 근사다(Davies 문제) —
p 는 눈금으로 읽는다.

고주기 쪽은 시편 대부분이 런아웃이라 둘째 기울기가 파단점 몇 개로 정해지기 쉽다. 구간마다
파단점을 `min_segment_points`(기본 3) 이상 요구하고, 몇 점으로 정했는지를 값으로 남긴다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member

from . import sn

#: 꺾임 후보를 고르게 놓는 수. 허용 범위가 응력 한 자릿수여도 칸 간격이 0.0025 자릿수다.
GRID = 400
#: 한 구간에 필요한 파단점의 기본값 — 둘이면 그 구간의 기울기가 두 점을 잇는 선이 된다.
MIN_SEGMENT_POINTS = 3
#: 2구간을 「근거 있음」 으로 읽는 F 검정 문턱.
SIGNIFICANCE = 0.05


def _solve(x: np.ndarray, y: np.ndarray, knee: float) -> tuple[np.ndarray, float]:
    """꺾임 `knee`(log S)에서 `(y_k, c1, c2)` 와 잔차 제곱합. c1 은 꺾임 위(높은 응력 · 짧은
    수명)."""
    above = np.maximum(x - knee, 0.0)
    below = np.minimum(x - knee, 0.0)
    design = np.column_stack([np.ones_like(x), above, below])
    found, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ found
    return found, float(residual @ residual)


def _valid(found: np.ndarray) -> bool:
    """두 구간 모두 응력이 낮을수록 수명이 늘어야 S-N 이다(log N 의 기울기가 음수)."""
    return bool(found[1] < 0.0 and found[2] < 0.0)


def _search(x: np.ndarray, y: np.ndarray, low: float, high: float) -> tuple[float, np.ndarray]:
    """허용 범위 `[low, high]` 를 고르게 훑고, 가장 좋은 칸 둘레를 한 번 더 촘촘히."""
    best: tuple[float, float, np.ndarray] | None = None

    def visit(knees: np.ndarray) -> None:
        nonlocal best
        for knee in knees:
            found, sse = _solve(x, y, float(knee))
            if _valid(found) and (best is None or sse < best[1] - 1e-15):
                best = (float(knee), sse, found)

    # 점의 자리 자체도 후보다 — 꺾임이 시험 응력 하나에 걸리는 경우가 흔하다.
    visit(np.concatenate([np.linspace(low, high, GRID), x[(x >= low) & (x <= high)]]))
    if best is None:
        raise GroupError(
            "두 구간 모두 응력이 낮을수록 수명이 늘어나는 꺾임을 찾지 못했습니다 — 한 직선"
            "(Basquin)을 쓰거나 데이터를 확인하세요."
        )
    step = (high - low) / (GRID - 1) if high > low else 0.0
    if step > 0.0:
        visit(np.linspace(max(low, best[0] - step), min(high, best[0] + step), 201))
        # 마지막으로 그 칸 안에서만 1차원 최소화 — 칸 간격이 꺾임의 오차가 되지 않게. 구간이
        # 좁고 그 안의 오차는 매끈해 초기값 문제가 없다(어긋나면 칸의 답을 그대로 쓴다).
        from scipy.optimize import minimize_scalar

        fine = step / 100.0
        span = (max(low, best[0] - fine), min(high, best[0] + fine))

        def cost(knee: float) -> float:
            found, sse = _solve(x, y, knee)
            return sse if _valid(found) else math.inf

        if span[0] < span[1]:
            polished = minimize_scalar(
                cost, bounds=span, method="bounded", options={"xatol": 1e-12}
            )
            if polished.success and float(polished.fun) < best[1]:
                visit(np.asarray([float(polished.x)]))
    return best[0], best[2]


def sn_bilinear(
    members: list[Member],
    *,
    exclude_runouts: bool = True,
    life_levels: str = sn.DEFAULT_LIFE_LEVELS,
    min_segment_points: int = MIN_SEGMENT_POINTS,
) -> GroupOutcome:
    """레지스트리가 옵션을 **키워드로** 넘긴다 — 시그니처가 곧 받는 칸이다."""
    from scipy import stats

    exclude = bool(exclude_runouts)
    levels = sn._levels(str(life_levels or sn.DEFAULT_LIFE_LEVELS))
    per_segment = int(min_segment_points or MIN_SEGMENT_POINTS)
    if per_segment < 2:
        raise GroupError("구간마다 파단점이 2개 이상이어야 기울기를 정할 수 있습니다.")
    warnings: list[str] = []

    points = [sn._point_of(member) for member in members]
    ratios = {round(p["stress_ratio"], 3) for p in points if p["stress_ratio"] is not None}
    if len(ratios) > 1:
        warnings.append(
            f"응력비 R 이 {', '.join(f'{r:g}' for r in sorted(ratios))} 로 섞여 있습니다 — "
            "한 S-N 곡선은 R 하나의 것입니다. 이 곡선은 그 차이를 그대로 품고 있습니다."
        )
    runouts = [p for p in points if p["runout"]]
    fitted = [p for p in points if not (exclude and p["runout"])]
    if exclude and runouts:
        warnings.append(
            f"런아웃 {len(runouts)}건은 적합에서 뺐습니다 — 그 점은 수명이 아니라 하한입니다: "
            + ", ".join(p["label"] for p in runouts)
            + "."
        )
    needed = max(2 * per_segment, 5)
    if len(fitted) < needed:
        raise GroupError(
            f"2구간에는 파단한 시편이 {needed}건 이상 필요합니다(구간마다 {per_segment}건 · "
            f"지금 {len(fitted)}건). 한 직선(Basquin)을 쓰거나 시험을 더하세요."
        )
    x = np.log10(np.asarray([p["stress"] for p in fitted], dtype=np.float64))
    y = np.log10(np.asarray([p["cycles"] for p in fitted], dtype=np.float64))
    ordered = np.sort(x)
    # 꺾임 위 · 아래에 파단점이 per_segment 개씩 들어가는 범위.
    # 점 자리에 걸린 꺾임은 그 점이 양쪽에 든다.
    low, high = float(ordered[per_segment - 1]), float(ordered[len(ordered) - per_segment])
    if not low < high:
        raise GroupError(
            f"꺾임 위 · 아래에 파단점을 {per_segment}건씩 둘 응력 범위가 없습니다 — 응력 "
            f"진폭이 몇 개로 몰려 있습니다. 다른 응력의 시험을 더하세요."
        )
    if float(np.ptp(y)) < 0.3:
        raise GroupError(
            "파단 수명이 한 자릿수 안에 몰려 있습니다 — 기울기를 정할 수 없습니다."
        )

    knee_x, (knee_y, c1, c2) = _search(x, y, low, high)
    b1, b2 = 1.0 / float(c1), 1.0 / float(c2)
    knee_stress, knee_cycles = 10.0**knee_x, 10.0 ** float(knee_y)
    a1 = knee_stress * knee_cycles ** (-b1)

    count = len(fitted)
    _, sse2 = _solve(x, y, knee_x)
    single = np.polyfit(x, y, 1)
    sse1 = float(np.sum((y - np.polyval(single, x)) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    dof = count - 4
    floor = 1e-30 * max(sst, 1.0)  # 맞춘 점이 식 위에 그대로 있으면 0 — 로그가 터지지 않게
    f_value = ((sse1 - sse2) / 2.0) / max(sse2 / dof, floor)
    p_value = float(stats.f.sf(max(f_value, 0.0), 2, dof))
    delta_bic = (count * math.log(max(sse2, floor) / count) + 4 * math.log(count)) - (
        count * math.log(max(sse1, floor) / count) + 2 * math.log(count)
    )
    supported = p_value < SIGNIFICANCE and delta_bic < 0.0
    upper = int(np.sum(x >= knee_x))
    lower = int(np.sum(x <= knee_x))

    if not supported:
        warnings.append(
            f"2구간 근거 약함 — 한 직선(Basquin) 권장: 한 직선과 견준 F 검정 p = {p_value:.3g}"
            f"(문턱 {SIGNIFICANCE:g}), ΔBIC = {delta_bic:+.3g}(음수여야 2구간이 낫다). 꺾임이 "
            "흩어짐에 맞춘 것일 수 있습니다."
        )
    if knee_x <= low + 1e-12 or knee_x >= high - 1e-12:
        warnings.append(
            "꺾임점이 탐색 범위 끝에 걸렸습니다 — 그 너머에 구간을 정할 파단점이 모자랍니다."
        )
    if abs(b2) > abs(b1):
        warnings.append(
            f"둘째 구간(고주기)이 첫째보다 가파릅니다(b1 = {b1:.4g}, b2 = {b2:.4g}) — 보통은 "
            "고주기 쪽이 완만합니다. 데이터를 확인하세요."
        )
    below_runouts = [p for p in runouts if p["stress"] < knee_stress]
    if exclude and below_runouts:
        warnings.append(
            f"꺾임 아래 응력에 런아웃 {len(below_runouts)}건 — 둘째 기울기는 파단점 "
            f"{lower}건으로만 정했습니다(런아웃은 하한이라 안 넣었습니다)."
        )

    def stress_at(cycles: np.ndarray | float) -> np.ndarray:
        n = np.asarray(cycles, dtype=np.float64)
        return np.where(
            n <= knee_cycles,
            a1 * n**b1,
            a1 * knee_cycles ** (b1 - b2) * n**b2,
        )

    cycles_all = 10.0**y
    values: dict[str, float] = {
        "sn_a1": float(a1),
        "sn_b1": float(b1),
        "sn_b2": float(b2),
        "knee_cycles": float(knee_cycles),
        "knee_stress": float(knee_stress),
        "sn_r_squared": 1.0 - sse2 / sst if sst > 0 else 1.0,
        # 수명의 흩어짐 — log N 잔차의 표준편차(자릿수). MATFAT · MATFTG 의 SE(log N
        # 표준오차)다.
        "log_scatter": float(math.sqrt(sse2 / dof)),
        "point_count": float(count),
        "runout_count": float(len(runouts)),
        "segment1_points": float(upper),
        "segment2_points": float(lower),
        "bilinear_p_value": p_value,
        "bilinear_delta_bic": float(delta_bic),
        "bilinear_supported": 1.0 if supported else 0.0,
        "cycles_min": float(np.min(cycles_all)),
        "cycles_max": float(np.max(cycles_all)),
    }
    for level in levels:
        values[f"strength_at_{sn._level_key(level)}"] = float(stress_at(level))

    grid = np.logspace(
        math.log10(float(np.min(cycles_all))),
        math.log10(float(np.max(cycles_all))),
        sn.CURVE_POINTS,
    )
    if float(np.min(cycles_all)) < knee_cycles < float(np.max(cycles_all)):
        grid = np.sort(np.append(grid, knee_cycles))  # 꺾임 자리를 그대로 지나게
    curve = stress_at(grid)
    detail: dict[str, Any] = {
        "model": "bilinear",
        "life_levels": list(levels),
        "exclude_runouts": exclude,
        "min_segment_points": per_segment,
        "comparison": {
            "single_b": float(1.0 / single[0]) if single[0] != 0 else None,
            "sse_single": sse1,
            "sse_bilinear": float(sse2),
            "f_value": float(f_value),
            "p_value": p_value,
            "delta_bic": float(delta_bic),
        },
        "points": [
            {
                "member": p["label"],
                "stress_amplitude": p["stress"],
                "cycles_to_failure": p["cycles"],
                "runout": p["runout"],
                "stress_ratio": p["stress_ratio"],
                "used": not (exclude and p["runout"]),
            }
            for p in points
        ],
        "curve": {
            sn.CYCLES: [float(v) for v in grid],
            sn.STRESS_AMPLITUDE: [float(v) for v in curve],
        },
    }
    return GroupOutcome(
        values=values,
        columns={sn.CYCLES: grid, sn.STRESS_AMPLITUDE: curve},
        detail=detail,
        warnings=warnings,
        used=[p["label"] for p in fitted],
    )


#: 카드에 싣는 값 — 2구간 계수와 판정. 덱 · 그래프가 이것만 읽는다.
CARD_VALUES = (
    "sn_a1",
    "sn_b1",
    "sn_b2",
    "knee_cycles",
    "knee_stress",
    "sn_r_squared",
    "log_scatter",
    "point_count",
    "runout_count",
    "segment1_points",
    "segment2_points",
    "bilinear_p_value",
    "bilinear_delta_bic",
    "bilinear_supported",
)


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 결과 → `sn_bilinear` 블록. 점(런아웃 표시 포함)이 행이고 2구간 계수가 값이다."""
    points = list(detail.get("points") or [])
    if not points:
        raise ValueError("이 묶음에 S-N 점이 없습니다.")
    summary = {key: float(values[key]) for key in CARD_VALUES if key in values}
    for key, value in values.items():
        if key.startswith("strength_at_"):
            summary[key] = float(value)
    return {
        "sn_bilinear": {
            "values": {"source": "sn_bilinear", "model": "bilinear", **summary},
            "rows": [
                {
                    "stress_amplitude": float(p["stress_amplitude"]),
                    "cycles_to_failure": float(p["cycles_to_failure"]),
                    "runout": 1.0 if p.get("runout") else 0.0,
                    **(
                        {"stress_ratio": float(p["stress_ratio"])}
                        if isinstance(p.get("stress_ratio"), int | float)
                        else {}
                    ),
                }
                for p in points
            ],
            "notes": list(warnings),
        }
    }
