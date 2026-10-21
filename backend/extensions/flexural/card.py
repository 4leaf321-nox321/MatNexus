"""구조 강성 블록 — 카드 부품용(2026-10-20). **중심 코드는 이 확장의 이름을 모른다.**

    블록   `structural_stiffness` — 굽힘 시험의 하중/처짐 기울기(N/m)와 **그 배치**(지지 ·
           하중 스팬, 시편 폭 · 두께). 칩 · 모듈 · 적층처럼 균질한 보가 아닌 부품은 등가 E 보다
           잰 강성이 정직하다 — 다만 그 숫자는 그 배치에서만 뜻이 있어 배치를 함께 든다.

덱으로 가는 형식은 아직 없다(부품 강성을 받는 자리 — 스프링 · 보 단면 — 는 모델마다 다르다).
카드에 실려 근거와 함께 남고, JSON 내보내기로 옮긴다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

STRUCTURAL_STIFFNESS = register_block(
    BlockSpec(
        key="structural_stiffness",
        label="구조 강성",
        help=(
            "굽힘 시험의 하중/처짐 기울기와 그 배치. **재료 값이 아니라 그 부품 · 그 배치의 "
            "값이다** — 스팬이 두 배면 3점 강성은 1/8 이 된다. 시편 여럿의 평균(같은 배치일 "
            "때만)."
        ),
        produces=(
            Produced(key="stiffness", label="강성 (하중/처짐)", si_unit="N/m"),
            Produced(key="stiffness_cv", label="강성 변동계수", si_unit="1"),
            Produced(key="loading", label="하중 방식", si_unit="1", help="3점 · 4점 굽힘."),
            Produced(key="support_span", label="지지 스팬", si_unit="m"),
            Produced(
                key="load_span", label="하중 스팬", si_unit="m", help="4점일 때. 3점이면 0."
            ),
            Produced(key="width", label="시편 폭", si_unit="m"),
            Produced(key="thickness", label="시편 두께", si_unit="m"),
            Produced(key="sample_count", label="시편 수", si_unit="1"),
        ),
        from_tests=("flexural",),
        from_values=False,
        # 카드의 종류가 된다(확장 블록의 규칙, `test_block_units`) — 굽힘 묶음 카드가 「구조
        # 강성」 으로 보인다. 칩 · 모듈의 카드에는 그 이름이 맞다.
        order=48,
    )
)
