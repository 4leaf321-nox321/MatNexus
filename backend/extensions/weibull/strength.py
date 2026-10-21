"""와이블 강도 분포 — 시편 여럿의 파단 하중 · 강도 → 형상 m · 척도 x₀(2026-10-20).

사용자 보고: 곡선 없이 파단 하중과 와이블(형상 · 척도)만 있는 외부 자료가 있는데, 통계 분포를
담을 블록이 없었다.

**적합은 중심의 분포 모듈 그대로다**(`matcore.distributions` 의 와이블 — 위치 0 고정 2모수,
최대우도). 여기서 하는 일은 값 하나를 골라 맞추고, 결과를 카드 블록으로 옮기는 것뿐이다.

    P(x) = 1 - exp(-(x/x₀)^m)       하위 5 % = x₀ · (-ln 0.95)^(1/m)

**시편 수가 적으면 형상 계수가 흔들린다** — ASTM C1239 는 30 개 이상을 권한다. 막지는 않고
말한다(10 개 미만이면 경고, 5 개 미만이면 안 맞춘다).

DB 도 HTTP 도 모른다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore import distributions
from matcore.groups import GroupError, GroupOutcome, Member

#: 맞출 수 있는 값 — 처리 결과(또는 표로 적은 요약값)의 이름 → (이름, 저장 단위).
QUANTITIES: dict[str, tuple[str, str]] = {
    "max_force": ("최대 하중 · 파단 하중", "N"),
    "break_force": ("파단 하중", "N"),
    "plateau_force": ("안정 구간 평균 하중", "N"),
    "peel_strength": ("박리 강도", "N/m"),
    "tensile_strength": ("인장강도", "Pa"),
    "flexural_strength": ("굽힘 강도", "Pa"),
    "compressive_strength": ("압축 강도", "Pa"),
}
#: 이보다 적으면 맞추지 않는다 — 두 모수를 넷으로 맞추는 것은 맞춘 척이다.
MIN_SAMPLES = 5
#: 이보다 적으면 경고한다.
WARN_BELOW = 10
#: 최댓값 대비 폭이 이 이하면 「값이 다 같다」 — 흩어짐을 맞출 수 없다.
SAME_VALUES = 1e-9
#: 형상 계수가 이보다 크면 의심한다 — 세라믹 · 금속도 대개 5 ~ 50 이다.
SHAPE_SUSPECT = 100.0


def weibull_fit(members: list[Member], *, quantity: str = "max_force") -> GroupOutcome:
    """고른 값 하나로 와이블 형상 · 척도를 맞춘다."""
    if quantity not in QUANTITIES:
        raise GroupError(
            f"맞출 수 없는 값입니다: {quantity}. 고를 수 있는 것: {', '.join(QUANTITIES)}"
        )
    label, unit = QUANTITIES[quantity]
    found = [
        (one.label, float(one.values[quantity]))
        for one in members
        if isinstance(one.values.get(quantity), int | float)
        and math.isfinite(float(one.values[quantity]))
        and float(one.values[quantity]) > 0
    ]
    if len(found) < MIN_SAMPLES:
        raise GroupError(
            f"'{label}' 이 있는 시편이 {len(found)}개입니다 — 와이블은 "
            f"{MIN_SAMPLES}개 이상이어야 맞춥니다(형상 계수가 시편 수에 크게 흔들린다)."
        )
    values = np.asarray([value for _, value in found], dtype=np.float64)
    if float(np.ptp(values)) <= SAME_VALUES * float(np.max(values)):
        # 값이 다 같으면 흩어짐이 0 이라 m 이 무한대로 간다 — 50 다섯 개에 m = 5e6 이 경고 없이
        # 나왔다(2026-10-20 검토). 표로 적은 값이 반올림된 경우다.
        raise GroupError(
            f"'{label}' 값이 모두 같아({values[0]:g}) 흩어짐을 맞출 수 없습니다 — "
            "표로 적은 값이 반올림됐는지 보세요."
        )
    distributions.load_builtin()
    weibull = distributions.DISTRIBUTIONS["weibull"]
    shape, scale = (float(one) for one in weibull.fit(values))
    p05 = float(weibull.ppf(np.asarray([shape, scale]), 0.05))
    p50 = float(weibull.ppf(np.asarray([shape, scale]), 0.5))
    warnings: list[str] = []
    if shape > SHAPE_SUSPECT:
        warnings.append(
            f"형상 계수 m = {shape:.4g} 은 재료의 흩어짐으로 보기 어렵게 큽니다 — "
            "값이 반올림돼 거의 같은지 보세요."
        )
    if len(found) < WARN_BELOW:
        warnings.append(
            f"시편 {len(found)}개로 맞췄습니다 — 형상 계수 m 이 크게 흔들립니다"
            "(ASTM C1239 는 30개 이상을 권합니다)."
        )
    return GroupOutcome(
        values={
            "weibull_shape": shape,
            "weibull_scale": scale,
            "weibull_p05": p05,
            "weibull_p50": p50,
            "sample_count": float(len(found)),
            "mean": float(np.mean(values)),
        },
        detail={"quantity": quantity, "quantity_label": label, "unit": unit},
        warnings=warnings,
        used=[name for name, _ in found],
    )


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 → `strength_distribution` 블록. 척도 · 분위수는 **행이 자기 단위를
    든다**(N · Pa · N/m) — 경화식 행과 같은 `si_unit` 칸이라 단위계를 바꾸면 함께 옮겨지고
    화면도 그 단위로 적는다. 처음에는 `unit` 칸이라 단위계 환산이 그 값을 SI 로 남겼다
    (2026-10-20 검토)."""
    shape = values.get("weibull_shape")
    scale = values.get("weibull_scale")
    if not isinstance(shape, int | float) or not isinstance(scale, int | float):
        raise ValueError("이 묶음에 와이블 계수가 없습니다.")
    unit = str(detail.get("unit") or "1")
    rows = [
        {"name": "shape", "label": "형상 m", "value": float(shape), "si_unit": "1"},
        {"name": "scale", "label": "척도 x₀ (63.2 %)", "value": float(scale), "si_unit": unit},
    ]
    for key, label in (("weibull_p05", "하위 5 %"), ("weibull_p50", "중앙값")):
        if isinstance(values.get(key), int | float):
            rows.append(
                {
                    "name": key.removeprefix("weibull_"),
                    "label": label,
                    "value": float(values[key]),
                    "si_unit": unit,
                }
            )
    return {
        "strength_distribution": {
            "values": {
                "distribution": "weibull",
                "quantity": str(detail.get("quantity") or ""),
                "quantity_label": str(detail.get("quantity_label") or ""),
                "shape": float(shape),
                "sample_count": float(values.get("sample_count", 0.0)),
            },
            "rows": rows,
            "notes": [
                f"2모수 와이블(위치 0) 최대우도 — {detail.get('quantity_label')} 시편 "
                f"{int(values.get('sample_count', 0))}개. 하위 5 % = x₀ · (-ln 0.95)^(1/m) = "
                f"{float(values.get('weibull_p05', math.nan)):.4g} {unit}.",
                *warnings,
            ],
        }
    }
