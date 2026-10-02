"""광학 물성 블록 — **광학 설계(Zemax · CODE V)와 광 시뮬레이션(Lumerical · COMSOL)이 묻는
것.**

굴절률은 **파장을 탄다**(분산). 589 nm 의 n 하나로는 색수차를 못 보고, 렌즈 설계 프로그램은
파장별 굴절률이나 그것을 맞춘 분산식을 받는다. 선언 물성이 파장별 점을 들면 그 점들이
`rows` 의 표가 된다(`shared/declared_slots`) — 열 이름 `wavelength` 가 표의 축이다. 파장은
SI(m)로 든다. 형식이 µm · nm 를 요구하면 렌더러가 `matcore.units` 로 옮긴다.

소광계수 k 는 복소 굴절률 n + ik 의 허수부다 — 흡수. 투명 재료는 비어 있는 것이 정상이고,
비었다고 0 을 지어 넣지 않는다(형식이 세 열을 요구하면 렌더러가 그 사실을 적고 0 을 쓴다).

방사율은 열복사의 값이라 열해석(Flotherm · ANSYS)이 쓴다. 광학 블록에 두는 이유는 문헌
물성의 갈래가 `optical.emissivity_total` 이어서다 — 칸이 문헌 키를 든다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

OPTICAL = register_block(
    BlockSpec(
        key="optical",
        label="광학 물성",
        help=(
            "굴절률 · 소광계수 · 아베수 · 방사율. 굴절률은 파장마다 값이 달라 파장별로 적으면 "
            "표가 되고, 렌즈 설계 프로그램이 그 표나 그것을 맞춘 분산식을 받는다."
        ),
        produces=(
            Produced(
                key="refractive_index",
                label="굴절률",
                si_unit="1",
                property_key="optical.refractive_index",
                help=(
                    "n. 파장을 탄다 — 어느 파장의 값인지가 함께 간다(d선 587.6 nm 가 흔하다)."
                ),
            ),
            Produced(
                key="extinction_coefficient",
                label="소광계수",
                si_unit="1",
                property_key="optical.extinction_coefficient",
                help="k — 복소 굴절률의 허수부, 흡수. 투명 재료는 비워 둔다.",
            ),
            Produced(
                key="abbe_number",
                label="아베수",
                si_unit="1",
                property_key="optical.abbe_number",
                help="νd = (nd - 1)/(nF - nC). 클수록 분산이 작다.",
            ),
            Produced(
                key="emissivity",
                label="방사율",
                si_unit="1",
                property_key="optical.emissivity_total",
                help=(
                    "전방사율 ε — 열복사 해석에 쓴다. 표면 상태(도장 · 산화)에 따라 크게 "
                    "다르다."
                ),
            ),
        ),
        rows=(
            Produced(key="wavelength", label="파장", si_unit="m", help=None),
            Produced(key="refractive_index", label="굴절률", si_unit="1", help=None),
            Produced(key="extinction_coefficient", label="소광계수", si_unit="1", help=None),
        ),
        order=18,
        kind_priority=5,
    )
)
