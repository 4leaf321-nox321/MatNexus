"""참고 물성 블록 — **덱은 안 읽는다.** 카드를 데이터시트로도 볼 때 함께 보이는 값(ADR 0060).

해석 솔버가 받는 입력은 아니지만 재료를 고르고 검토하는 사람이 카드 한 장에서 같이 보고
싶은 값들이다 — Tg · 사용 온도 · 굽힘 · 압축 · 파괴인성 · 경도 · 절연 · 박리 · 점도. 전에는
재료에 적어 두어도 카드로 갈 자리가 없어(2026-10-08 점검: 기본 항목 43 중 27) 카드 화면 ·
중립 JSON · SP 연동 어디에서도 안 보였다.

## 적어 둔 값이 있으면 블록이 스스로 붙는다

다른 블록은 카드에 **있을 때만** 빈 칸이 채워진다(`app/shared/declared_slots` 규칙 ②) —
이방성 카드에 열물성이 따라 붙으면 그 카드가 무엇의 카드인지 흐려진다. 이 블록은 예외다
(`attach_when_stated`): 덱이 안 읽어 카드의 종류(`kind_priority=None`)도 해석도 안 바꾸고,
「이 재료의 값이 카드에 함께 보이는가」 가 이 블록의 목적 전부라서다.

칸마다 물성 키를 든다 — 기준정보 항목이 키에 이어져 있으면 그 값이 온다. 단위는 그 물성
정의(문헌 카탈로그)의 SI 단위와 같다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced


def _slot(key: str, label: str, si_unit: str, property_key: str, help: str) -> Produced:
    return Produced(
        key=key, label=label, si_unit=si_unit, help=help, property_key=property_key
    )


REFERENCE = register_block(
    BlockSpec(
        key="reference",
        label="참고 물성",
        help=(
            "재료에 적어 둔 참고값 — **덱에는 안 실린다.** 카드를 데이터시트로도 볼 때 함께 "
            "보이는 값이고, 적어 둔 값이 있으면 카드를 만들 때 이 블록이 스스로 붙는다."
        ),
        produces=(
            _slot(
                "glass_transition",
                "유리전이온도 Tg",
                "K",
                "thermal.glass_transition",
                "정의(DSC · DMA tan δ 등)에 따라 값이 갈린다 — 적어 둔 근거를 함께 본다.",
            ),
            _slot("melting_point", "융점", "K", "thermal.melting_point", "재료에 적어 둔 값."),
            _slot(
                "max_service_temperature",
                "최대 사용온도",
                "K",
                "thermal.max_service_temp",
                "제조사 기준이 저마다 달라(단기 · 장기) 근거를 함께 본다.",
            ),
            _slot(
                "decomposition_temperature",
                "열분해온도",
                "K",
                "thermal.decomposition_temp",
                "재료에 적어 둔 값.",
            ),
            _slot(
                "flexural_strength",
                "굽힘강도",
                "Pa",
                "mechanical.flexural_strength",
                "3점 · 4점 굽힘 규격에 따라 다르다.",
            ),
            _slot(
                "flexural_modulus",
                "굽힘탄성률",
                "Pa",
                "mechanical.flexural_modulus",
                "인장 탄성계수와 같지 않다 — 덱의 E 로 쓰지 않는다.",
            ),
            _slot(
                "compressive_strength",
                "압축강도",
                "Pa",
                "mechanical.compressive_strength",
                "재료에 적어 둔 값.",
            ),
            _slot(
                "fracture_toughness",
                "파괴인성 K_IC",
                "Pa.m0.5",
                "mechanical.fracture_toughness",
                "평면 변형 파괴인성.",
            ),
            _slot(
                "hardness_vickers",
                "비커스 경도",
                "HV",
                "mechanical.hardness_vickers",
                "눈금 숫자 — 다른 경도와 환산하지 않는다.",
            ),
            _slot(
                "hardness_brinell",
                "브리넬 경도",
                "HBW",
                "mechanical.hardness_brinell",
                "눈금 숫자 — 다른 경도와 환산하지 않는다.",
            ),
            _slot(
                "hardness_rockwell",
                "로크웰 경도",
                "HR",
                "mechanical.hardness_rockwell",
                "눈금(HRC · HRB)은 적어 둔 값의 근거에서 본다.",
            ),
            _slot(
                "dielectric_strength",
                "절연파괴강도",
                "V/m",
                "electrical.dielectric_strength",
                "두께에 따라 달라진다 — 적어 둔 시편 두께를 함께 본다.",
            ),
            _slot(
                "surface_resistivity",
                "표면저항률",
                "ohm",
                "electrical.surface_resistivity",
                "Ω/sq. 습도에 민감하다.",
            ),
            _slot(
                "comparative_tracking_index",
                "비교트래킹지수 CTI",
                "V",
                "electrical.comparative_tracking_index",
                "IEC 60112.",
            ),
            _slot(
                "arc_resistance", "내아크성", "s", "electrical.arc_resistance", "ASTM D495."
            ),
            _slot(
                "peel_strength",
                "박리강도",
                "N/m",
                "interface.peel_strength",
                "폭당 하중. 박리 각도 · 속도에 따라 다르다.",
            ),
            _slot(
                "viscosity",
                "점도",
                "Pa.s",
                "rheological.viscosity",
                "값 하나(뉴턴 점도로 적은 값). 전단 박화 식은 유변 블록이 든다.",
            ),
        ),
        order=95,
        kind_priority=None,
        attach_when_stated=True,
    )
)
