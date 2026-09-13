"""S-N 곡선 — 시편마다 점 하나(응력 진폭, 파단 수명)를 Basquin 으로 잇는다.

Basquin    S = A · N^b        로그-로그에서 직선: log S = log A + b·log N

런아웃(안 부러진 채 멈춘 시편)은 **적합에서 뺀다** — 그 점은 수명이 아니라 하한이다.
넣으면 곡선이 위로 휘어 안전하지 않은 쪽으로 틀린다. 뺐다는 사실과 몇 건인지는
결과에 남고, 점은 표에 런아웃 표시로 남는다.

같은 응력 진폭에서 여러 시편이면 **점을 그대로 둔다**(평균하지 않는다) — 피로의
흩어짐이 곧 정보다. 값에는 R(응력비)이 섞여 있는지도 적는다: R 이 다른 점을 한
곡선으로 잇는 것은 다른 물음의 답을 섞는 것이다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member

STRESS_AMPLITUDE = "stress_amplitude"
STRESS_RATIO = "stress_ratio"
FREQUENCY = "frequency"
CYCLES = "cycles_to_failure"
RUNOUT = "runout"

#: 피로 강도를 읽어 줄 수명. 강은 1e6~1e7 에서 무한 수명 문턱을 말한다.
DEFAULT_LIFE_LEVELS = "1e5, 1e6, 1e7"
MIN_POINTS = 3
CURVE_POINTS = 60


def sn_curve(
    members: list[Member],
    *,
    exclude_runouts: bool = True,
    life_levels: str = DEFAULT_LIFE_LEVELS,
) -> GroupOutcome:
    """레지스트리가 옵션을 **키워드로** 넘긴다 — 시그니처가 곧 받는 칸이다."""
    exclude = bool(exclude_runouts)
    levels = _levels(str(life_levels or DEFAULT_LIFE_LEVELS))
    warnings: list[str] = []

    points = [_point_of(member) for member in members]
    ratios = {round(p["stress_ratio"], 3) for p in points if p["stress_ratio"] is not None}
    if len(ratios) > 1:
        warnings.append(
            f"응력비 R 이 {', '.join(f'{r:g}' for r in sorted(ratios))} 로 섞여 있습니다 — "
            f"한 S-N 곡선은 R 하나의 것입니다. 이 곡선은 그 차이를 그대로 품고 있습니다."
        )
    runouts = [p for p in points if p["runout"]]
    fitted = [p for p in points if not (exclude and p["runout"])]
    if exclude and runouts:
        warnings.append(
            f"런아웃 {len(runouts)}건은 적합에서 뺐습니다 — 그 점은 수명이 아니라 하한입니다: "
            + ", ".join(p["label"] for p in runouts)
            + "."
        )
    if len(fitted) < MIN_POINTS:
        raise GroupError(
            f"Basquin 에는 파단한 시편이 {MIN_POINTS}건 이상 필요합니다(지금 {len(fitted)}건)."
        )
    stress = np.asarray([p["stress"] for p in fitted], dtype=np.float64)
    cycles = np.asarray([p["cycles"] for p in fitted], dtype=np.float64)
    if float(np.ptp(np.log10(cycles))) < 0.3:
        raise GroupError(
            "파단 수명이 한 자릿수 안에 몰려 있습니다 — 기울기를 정할 수 없습니다. "
            "다른 응력 진폭의 시험을 더하세요."
        )

    log_n = np.log10(cycles)
    log_s = np.log10(stress)
    b, log_a = np.polyfit(log_n, log_s, 1)
    predicted = log_a + b * log_n
    residual = log_s - predicted
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((log_s - log_s.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    a = float(10.0**log_a)
    if b >= 0:
        warnings.append(
            "수명이 길수록 응력이 오르는 모양입니다(b ≥ 0) — 데이터를 확인하세요. "
            "런아웃이 파단으로 적혀 있지 않은지 보세요."
        )

    values: dict[str, float] = {
        "basquin_a": a,
        "basquin_b": float(b),
        "sn_r_squared": float(r_squared),
        "point_count": float(len(fitted)),
        "runout_count": float(len(runouts)),
        "cycles_min": float(np.min(cycles)),
        "cycles_max": float(np.max(cycles)),
    }
    for level in levels:
        values[f"strength_at_{_level_key(level)}"] = float(a * level**b)
    # 로그 잔차의 표준편차 — 흩어짐. 같은 응력에서 수명이 열 배 갈리는 것이 피로다.
    if len(fitted) > 2:
        values["log_scatter"] = float(np.sqrt(ss_res / (len(fitted) - 2)))

    grid = np.logspace(
        math.log10(float(np.min(cycles))), math.log10(float(np.max(cycles))), CURVE_POINTS
    )
    detail: dict[str, Any] = {
        "model": "basquin",
        "life_levels": list(levels),
        "exclude_runouts": exclude,
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
            CYCLES: [float(v) for v in grid],
            STRESS_AMPLITUDE: [float(a * v**b) for v in grid],
        },
    }
    return GroupOutcome(
        values=values,
        columns={CYCLES: grid, STRESS_AMPLITUDE: a * grid**b},
        detail=detail,
        warnings=warnings,
        used=[p["label"] for p in fitted],
    )


def _point_of(member: Member) -> dict[str, Any]:
    stress = member.values.get(STRESS_AMPLITUDE)
    cycles = member.values.get(CYCLES)
    if stress is None or not math.isfinite(float(stress)) or float(stress) <= 0:
        raise GroupError(
            f"'{member.label}' 에 응력 진폭이 없습니다. "
            "시험 조건의 응력 진폭(Pa)으로 잇습니다."
        )
    if cycles is None or not math.isfinite(float(cycles)) or float(cycles) <= 0:
        raise GroupError(
            f"'{member.label}' 에 파단 수명(cycles_to_failure)이 없습니다 — 표로 넣을 때 "
            f"그 열이 있어야 합니다. 런아웃이면 수명은 멈춘 수명, runout 은 예로 적습니다."
        )
    runout_raw = member.values.get(RUNOUT)
    ratio = member.values.get(STRESS_RATIO)
    return {
        "label": member.label,
        "stress": float(stress),
        "cycles": float(cycles),
        "runout": bool(runout_raw) if runout_raw is not None else False,
        "stress_ratio": float(ratio) if ratio is not None else None,
    }


def _levels(raw: str) -> tuple[float, ...]:
    found: list[float] = []
    for token in raw.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError as exc:
            raise GroupError(
                f"피로 강도를 읽을 수명을 숫자로 못 읽었습니다: '{token}'"
            ) from exc
        if value <= 0:
            raise GroupError(f"수명은 0 보다 커야 합니다: {value}")
        found.append(value)
    return tuple(sorted(set(found)))


def _level_key(level: float) -> str:
    """1e6 → `1e6`, 500000 → `5e5`. 값 이름에 든 수명."""
    exponent = math.floor(math.log10(level))
    mantissa = level / 10**exponent
    head = f"{mantissa:g}".replace(".", "p")
    return f"{head}e{exponent}"


# ── 카드 ────────────────────────────────────────────────────────────────────


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 결과 → `sn_curve` 블록. 점(런아웃 표시 포함)이 행이고 Basquin 계수가 값이다."""
    points = list(detail.get("points") or [])
    if not points:
        raise ValueError("이 묶음에 S-N 점이 없습니다.")
    keep = {
        "basquin_a",
        "basquin_b",
        "sn_r_squared",
        "point_count",
        "runout_count",
        "log_scatter",
    }
    summary = {key: float(value) for key, value in values.items() if key in keep}
    for key, value in values.items():
        if key.startswith("strength_at_"):
            summary[key] = float(value)
    return {
        "sn_curve": {
            "values": {"source": "sn_curve", "model": "basquin", **summary},
            "rows": [
                {
                    "stress_amplitude": float(p["stress_amplitude"]),
                    "cycles_to_failure": float(p["cycles_to_failure"]),
                    "runout": 1.0 if p.get("runout") else 0.0,
                }
                for p in points
            ],
            "notes": list(warnings),
        }
    }
