"""응집 영역(cohesive zone) 블록(2026-10-20). **중심 코드는 이 확장의 이름을 모른다.**

    블록   `cohesive_zone` — 해석용 접합부 계수: 파괴 에너지 G_c(J/m² = N/m)와 최대 견인력
           T_max(Pa). 박리 시험은 G_c 만 준다(박리 강도 · (1 - cos θ)) — T_max 는 재료에
           적어 둔 값(`interface.cohesive_strength`)이 채운다.

덱 형식은 아직 없다 — LS-DYNA *MAT_COHESIVE_MIXED_MODE(138) 등은 법선 · 접선 강성과
모드 II 값까지 요구하는데 박리 시험은 그것을 주지 않는다. 카드에 실려 JSON 으로 옮긴다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

COHESIVE_ZONE = register_block(
    BlockSpec(
        key="cohesive_zone",
        label="응집 영역",
        help=(
            "접합부를 응집 요소로 해석할 때의 계수 — 파괴 에너지 G_c 와 최대 견인력 T_max. "
            "박리 시험은 G_c 만 준다(박리 강도 · (1 - cos θ), 탄성 팔 가정). T_max 는 재료에 "
            "적어 둔 값이 채운다."
        ),
        produces=(
            Produced(
                key="fracture_energy",
                label="파괴 에너지 G_c",
                si_unit="N/m",
                help="J/m² 와 같은 차원(N·m/m² = N/m). 박리면 모드 I.",
            ),
            Produced(
                key="peak_traction",
                label="최대 견인력 T_max",
                si_unit="Pa",
                help="박리 시험이 주지 않는다 — 재료에 적어 둔 값.",
                property_key="interface.cohesive_strength",
            ),
            Produced(key="mode", label="파괴 모드", si_unit="1", help="모드 I (박리) 등."),
            Produced(key="sample_count", label="시편 수", si_unit="1"),
        ),
        from_tests=("adhesion",),
        from_values=False,
        order=55,
    )
)
