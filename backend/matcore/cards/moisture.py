"""흡습 블록 — 수분 확산 · 포화 농도 · 흡습 팽창(2026-10-08).

반도체 패키지(EMC · 언더필 · NCA · 기판)의 리플로 · 85/85 신뢰성 해석이 쓰는 셋이다.
ANSYS 는 `MP,DXX` · `MP,CSAT` · `MP,BETX` 로 받는다(`matcore/export/ansys.py`).

## 셋은 한 환경의 값이다

포화 농도는 **온도와 상대습도로 정해진다** — 85 °C/85 %RH 와 30 °C/60 %RH 의 값이 두세 배
다르다. 확산계수도 온도를 크게 탄다. 그래서 블록이 그 환경(`temperature` · `humidity`)을
함께 든다 — 숫자만 실리면 덱만 받은 사람이 그것이 어느 조건의 값인지 모른다.

## 포화 농도는 질량 농도다

ANSYS 의 팽윤 변형은 `BETX·(C - CREF)` 이고 C 는 실제 농도(정규화 농도에 CSAT 을 곱한
값)다. 도움말의 예제가 β 를 m³/kg, CSAT 을 kg/m³ 로 짝지었다. 그래서 이 블록은 kg/m³ 를
든다. 문헌 카탈로그는 mol/m³ 로 적어서(`physical.moisture_saturation`) 물의 몰질량으로
옮긴다(`app/shared/moisture`) — **그래서 이 칸에는 물성 키를 안 단다.** 달면 값 검색이
kg/m³ 숫자를 mol/m³ 문헌값과 나란히 세운다.

확산계수 칸은 `physical.diffusion_coefficient` 를 단다 — 수분의 확산계수도 확산계수다.
다만 그 문헌 키에는 물 말고 다른 것(용융 Sn 속 Cu · O₂ · Li⁺)도 산다. 문헌 덱은 확산 종을
보고 물만 고른다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

MOISTURE = register_block(
    BlockSpec(
        key="moisture",
        label="흡습",
        help=(
            "수분 확산계수 · 포화 수분 농도 · 흡습 팽창 계수(CHE). **한 환경(온도 · 습도)의 "
            "값이다** — 포화 농도는 습도에 따라 두세 배 달라서 그 조건을 함께 든다."
        ),
        produces=(
            Produced(
                key="moisture_diffusivity",
                label="수분 확산계수 D",
                si_unit="m2/s",
                property_key="physical.diffusion_coefficient",
                help="Fick 확산의 D. 온도를 크게 탄다 — 아래 온도의 값이다.",
            ),
            Produced(
                key="moisture_saturation",
                label="포화 수분 농도 Csat",
                si_unit="kg/m3",
                help=(
                    "그 온도 · 습도에서 다 젖었을 때의 농도(질량/부피). 문헌의 mol/m³ 는 물의 "
                    "몰질량(0.018015 kg/mol)으로 옮긴 값이다."
                ),
            ),
            Produced(
                key="hygroscopic_expansion",
                label="흡습 팽창 계수(CHE)",
                si_unit="m3/kg",
                property_key="physical.hygroscopic_expansion",
                help="팽윤 변형 = β · 수분 농도(질량/부피). 마른 상태가 기준이다.",
            ),
            Produced(
                key="temperature",
                label="온도",
                si_unit="K",
                help="값들이 선 환경의 온도. 비면 모른다는 뜻이다.",
            ),
            Produced(
                key="humidity",
                label="상대습도",
                si_unit="1",
                help="포화 농도가 선 상대습도(0~1). 물에 담근 값이면 비어 있다.",
            ),
        ),
        order=19,
        kind_priority=6,
    )
)
