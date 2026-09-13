"""S-N 카드 블록 — 점(런아웃 표시 포함)이 행, Basquin 계수·피로 강도가 값."""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

SN_CURVE = register_block(
    BlockSpec(
        key="sn_curve",
        label="S-N 곡선",
        help=(
            "시편마다 (응력 진폭, 파단 수명) 점과 그것을 이은 Basquin 식 S = A·N^b. "
            "**런아웃은 행에 남되 적합에서는 뺀 값이다** — 그 점은 수명이 아니라 하한이다."
        ),
        produces=(
            Produced(key="source", label="표를 만든 방법", si_unit="1"),
            Produced(key="model", label="식", si_unit="1", help="`basquin`."),
            Produced(key="basquin_a", label="Basquin A", si_unit="Pa"),
            Produced(key="basquin_b", label="Basquin b", si_unit="1"),
            Produced(key="sn_r_squared", label="적합의 R²", si_unit="1"),
            Produced(key="point_count", label="적합에 쓴 점 수", si_unit="1"),
            Produced(key="runout_count", label="런아웃 수", si_unit="1"),
            Produced(key="log_scatter", label="흩어짐", si_unit="1"),
            Produced(key="strength_at_1e5", label="피로 강도 @1e5", si_unit="Pa"),
            Produced(key="strength_at_1e6", label="피로 강도 @1e6", si_unit="Pa"),
            Produced(key="strength_at_1e7", label="피로 강도 @1e7", si_unit="Pa"),
        ),
        rows=(
            Produced(key="stress_amplitude", label="응력 진폭", si_unit="Pa"),
            Produced(key="cycles_to_failure", label="파단 수명", si_unit="1"),
            Produced(
                key="runout", label="런아웃", si_unit="1", help="1 이면 안 부러진 채 멈춤."
            ),
        ),
        order=45,
        kind_priority=3,
    )
)
