"""온도별 소성 곡선 — 온도 연화 기울기.

여러 온도에서 찍은 인장 곡선을 받아, 한 변형률에서 읽은 응력이 온도에 따라 어떻게
내려가는지(dσ/dT)를 낸다. Johnson-Cook 의 온도 항(m)을 정하기 전에 보는 값이다.
"""

from __future__ import annotations

import math

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member

PLASTIC_STRAIN = "strain_true_plastic"
TRUE_STRESS = "stress_true"
TEMPERATURE = "temperature"


def _stress_at(member: Member, level: float) -> float | None:
    x = np.asarray(member.columns[PLASTIC_STRAIN], dtype=np.float64)
    y = np.asarray(member.columns[TRUE_STRESS], dtype=np.float64)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if x.size < 2 or level > float(np.max(x)) or level < float(np.min(x)):
        return None
    order = np.argsort(x)
    return float(np.interp(level, x[order], y[order]))


def temperature_family(members: list[Member], *, level: float = 0.02) -> GroupOutcome:
    """레지스트리가 옵션을 **키워드로** 넘긴다 — 시그니처가 곧 받는 칸이다."""
    level = float(level)
    if level <= 0.0:
        raise GroupError(f"연화 기울기를 읽을 변형률은 0 보다 커야 합니다: {level}")

    warnings: list[str] = []
    points: list[tuple[float, float, str]] = []
    for member in members:
        temperature = member.values.get(TEMPERATURE)
        if temperature is None or not math.isfinite(float(temperature)):
            raise GroupError(
                f"'{member.label}' 에 온도 조건이 없습니다. 시험 조건의 온도로 묶습니다."
            )
        stress = _stress_at(member, level)
        if stress is None:
            warnings.append(
                f"'{member.label}' 의 곡선이 변형률 {level:.4g} 까지 안 가 그 온도는 뺐습니다."
            )
            continue
        points.append((float(temperature), stress, member.label))

    if len(points) < 2:
        raise GroupError(
            f"변형률 {level:.4g} 에서 응력을 읽을 수 있는 온도가 둘 미만입니다 — "
            f"묶을 수 없습니다."
        )
    points.sort()
    temperatures = np.asarray([one[0] for one in points])
    stresses = np.asarray([one[1] for one in points])
    if float(np.ptp(temperatures)) == 0.0:
        raise GroupError("온도가 전부 같습니다 — 온도별로 묶을 것이 없습니다.")

    slope, intercept = np.polyfit(temperatures, stresses, 1)
    predicted = slope * temperatures + intercept
    residual = float(np.sum((stresses - predicted) ** 2))
    total = float(np.sum((stresses - float(np.mean(stresses))) ** 2))
    r_squared = 1.0 - residual / total if total > 0 else 1.0

    return GroupOutcome(
        values={
            "temperature_count": float(len(points)),
            "temperature_min": float(temperatures[0]),
            "temperature_max": float(temperatures[-1]),
            "softening_slope": float(slope),
            "softening_r_squared": float(r_squared),
        },
        detail={
            "level": level,
            "temperatures": [
                {"temperature_k": t, "stress_pa": s, "member": label} for t, s, label in points
            ],
        },
        warnings=warnings,
        used=[label for _t, _s, label in points],
    )
