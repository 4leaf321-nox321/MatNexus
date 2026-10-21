"""와이블 강도 분포 — 파단 하중 · 강도의 통계 분포 블록(2026-10-20).

    묶음   weibull.strength        시편 여럿의 값 하나(최대 하중 · 인장강도 …)
                                   → 형상 m · 척도 x₀ · 하위 5 % · 중앙값
    블록   strength_distribution   분포 · 고른 값 · 형상 · 시편 수,
                                   행에 척도 · 분위수(단위 포함)

곡선이 없어도 된다 — 시편마다 파단 하중을 「표로 시험 입력」 으로 넣으면 그 요약값으로
맞춘다(`measured_or_stated`). 사용자 보고: 파단 하중과 와이블(형상 · 척도)만 있는 외부
자료를 담을 자리가 없었다. 적합은 `matcore.distributions` 의 와이블 그대로다(`strength.py`).
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import ParamSpec, Produced, register

from . import strength

STRENGTH_DISTRIBUTION = register_block(
    BlockSpec(
        key="strength_distribution",
        label="강도 분포",
        help=(
            "시편 여럿의 파단 하중 · 강도를 맞춘 통계 분포(지금은 2모수 와이블). "
            "형상 m 이 클수록 흩어짐이 작다. 척도 x₀ 는 63.2 % 가 그 아래에서 깨지는 "
            "값, 하위 5 % 는 설계 허용값의 근거다. **행이 자기 단위를 든다** — "
            "무엇을 맞췄는지(하중 N · 강도 Pa)에 따라 다르다."
        ),
        produces=(
            Produced(key="distribution", label="분포", si_unit="1", help="weibull."),
            Produced(key="quantity_label", label="맞춘 값", si_unit="1"),
            Produced(
                key="shape",
                label="형상 m (와이블 계수)",
                si_unit="1",
                property_key="mechanical.weibull_modulus",
            ),
            Produced(key="sample_count", label="시편 수", si_unit="1"),
        ),
        rows=(
            Produced(key="label", label="항목", si_unit="1"),
            Produced(
                key="value", label="값", si_unit="1", help="행이 자기 단위(`si_unit`)를 든다."
            ),
        ),
        from_values=False,
        order=60,
    )
)

register(
    id="weibull.strength",
    kind="grouping",
    label="와이블 강도 분포",
    # 고른 값(최대 하중 · 강도)이 나오는 시험들 — 곡선이 없는 외부 자료(표로 입력)도 받는다.
    applies_to=("adhesion", "tensile", "flexural", "compression"),
    params=(
        ParamSpec(
            name="quantity",
            label="맞출 값",
            type="choice",
            default="max_force",
            choices=tuple(strength.QUANTITIES),
            choice_labels={key: label for key, (label, _) in strength.QUANTITIES.items()},
        ),
    ),
    makes_values=(
        Produced(key="weibull_shape", label="형상 m", si_unit="1"),
        Produced(
            key="weibull_scale",
            label="척도 x₀",
            si_unit="1",
            help="맞춘 값의 단위(N · Pa · N/m) — 카드 블록의 행이 단위를 든다.",
        ),
        Produced(key="weibull_p05", label="하위 5 %", si_unit="1"),
        Produced(key="weibull_p50", label="중앙값", si_unit="1"),
        Produced(key="sample_count", label="시편 수", si_unit="1"),
    ),
    members={
        "from": "measured_or_stated",
        "values": [],
        "optional": list(strength.QUANTITIES),
    },
    card=strength.card_blocks,
    order=90,
    version="1",
)(strength.weibull_fit)
