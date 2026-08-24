"""열물성 블록 — **인장시험이 하나도 안 주는 것들.**

탄성계수는 인장시험이 주기도 한다(대표 곡선의 탄성 구간). 열팽창계수·비열·
열전도도는 **아예 안 준다** — 따로 재거나 핸드북·규격에서 온다. 그래서 이
블록의 값은 대개 선언 물성에서 온다(ADR 0016).

## 왜 `elastic` 에 안 넣는가

`elastic` 은 `*ELASTIC` 한 줄이 받는 값들이다 — 탄성계수와 푸아송비가 **한
키워드에 함께** 간다. 열물성은 키워드가 셋으로 갈린다(`*EXPANSION` ·
`*SPECIFIC HEAT` · `*CONDUCTIVITY`) 그리고 **하나만 있어도 그 키워드는 낼 수
있다.**

한 블록에 두면 렌더러가 "탄성계수가 있는데 비열이 없으면?" 을 판단해야 하고,
그 판단이 늘어나는 자리가 곧 조용히 틀리는 자리다.

## 온도

지금은 값 하나에 온도 하나다(선언 물성의 `temperature_k`). 실제로는 E 도
열팽창도 온도를 크게 타므로 언젠가 표가 된다 — 그때 이 블록은 `rows` 를 쓰면
되고, 지금 담은 `values` 는 그대로 남는다(ADR 0012 의 블록이 값과 행을 함께
받는 이유다).
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

THERMAL = register_block(
    BlockSpec(
        key="thermal",
        label="열물성",
        help=(
            "열팽창계수·비열·열전도도. **인장시험이 하나도 안 준다** — "
            "핸드북·규격에서 오거나 따로 잰다. 셋 중 하나만 있어도 그 값에 "
            "해당하는 솔버 키워드는 나간다."
        ),
        produces=(
            Produced(
                key="thermal_expansion",
                label="열팽창계수",
                si_unit="1/K",
                help=(
                    "선팽창계수 α. 열응력 해석에 필요하다. **기준 온도가 함께 "
                    "있어야 뜻이 성립한다** — 솔버가 `α·ΔT` 로 쓰기 때문이다."
                ),
            ),
            Produced(
                key="specific_heat",
                label="비열",
                si_unit="J/(kg.K)",
                help="정압 비열 Cp. 과도 열해석에 필요하다.",
            ),
            Produced(
                key="thermal_conductivity",
                label="열전도도",
                si_unit="W/(m.K)",
                help="열전도도 k. 정상·과도 열해석에 모두 필요하다.",
            ),
            Produced(
                key="reference_temperature",
                label="기준 온도",
                si_unit="K",
                help=(
                    "값들을 잰 온도. 비면 상온으로 본다. 열팽창계수는 이 온도가 "
                    "없으면 `ΔT` 의 기준을 모른다."
                ),
            ),
        ),
        order=15,
    )
)
