"""이방성 카드 블록 — r값 셋과 거기서 나온 r̄·Δr·Hill48 계수."""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

ANISOTROPY = register_block(
    BlockSpec(
        key="anisotropy",
        label="이방성 (r값)",
        help=(
            "세 방향(MD 0° · DD 45° · TD 90°) 인장에서 나온 소성 변형비와 그 조합. "
            "**방향 하나의 물성이 아니다** — 세 방향을 함께 써서 나온 값이라 카드에 "
            "방향이 없다."
        ),
        produces=(
            Produced(key="r_0", label="r₀ (MD)", si_unit="1"),
            Produced(key="r_45", label="r₄₅ (DD)", si_unit="1"),
            Produced(key="r_90", label="r₉₀ (TD)", si_unit="1"),
            Produced(
                key="r_bar",
                label="평균 이방성 r̄",
                si_unit="1",
                help="(r₀+2r₄₅+r₉₀)/4. 클수록 두께가 안 줄어 깊이 드로잉에 유리하다.",
            ),
            Produced(
                key="delta_r",
                label="면내 이방성 Δr",
                si_unit="1",
                help="(r₀-2r₄₅+r₉₀)/2. 0 에서 멀수록 컵 가장자리에 귀가 생긴다.",
            ),
            Produced(key="hill_f", label="Hill48 F", si_unit="1"),
            Produced(key="hill_g", label="Hill48 G", si_unit="1"),
            Produced(key="hill_h", label="Hill48 H", si_unit="1"),
            Produced(key="hill_n", label="Hill48 N", si_unit="1"),
        ),
        order=55,
        kind_priority=4,
        from_tests=("tensile",),
        meta={
            # **이 블록은 방향을 가로지른다.** 카드 한 장은 방향 하나라는 규칙의
            # 예외이고, 카드를 만드는 쪽이 이 표시를 보고 방향 검사를 면제한다.
            "cross_orientation": True,
            # 값이 시험에서 나온다 — 등급을 표본 수로 매긴다. 사람이 적어 넣은
            # r값이 섞이면 값마다 붙는 `_source` 가 그것을 뒤집는다.
            "measured": True,
        },
    )
)
