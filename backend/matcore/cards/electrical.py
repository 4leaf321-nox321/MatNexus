"""전기 · 전자기 물성 블록 — **ECAE(HFSS · CST · Maxwell · Icepak)가 묻는 것.**

인장시험도 열물성 시험도 안 준다. 데이터시트(PCB 적층재 Dk/Df · 동박 전도율)와 문헌에서
온다 — 그래서 값은 대개 선언 물성이고(ADR 0016), 칸마다 문헌 물성 키를 든다.

## 주파수 표

비유전율(Dk) · 유전손실(Df) · 비투자율은 **주파수를 탄다.** 1 MHz 와 10 GHz 의 Dk 는 다른
값이고, 고속 신호 해석은 그 차이(분산)를 본다. 선언 물성이 주파수별 점을 들면 그 점들이
`rows` 의 표가 된다(`shared/declared_slots`) — 열 이름 `frequency` 가 표의 축이다.

`values` 는 그대로 **한 값**이다(가장 낮은 주파수의 것, 표의 첫 줄과 같다). 어느 주파수의
값인지는 `<칸>_frequency_hz` 가 함께 든다 — 숫자만 실리면 덱을 받은 사람이 모른다.

## 전도율과 저항률

둘 다 칸이 있다 — 데이터시트가 어느 쪽으로 적었는지 그대로 둔다. 솔버가 한쪽만 받으면
렌더러가 **σ = 1/ρ** 로 옮기고 그 사실을 적는다(지어내는 값이 아니라 정의다). 저항온도계수
(TCR)는 기준 온도(`<칸>_temperature_k`)와 함께 읽는다 — ρ(T) = ρ₀·[1 + α(T - T₀)].

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

ELECTRICAL = register_block(
    BlockSpec(
        key="electrical",
        label="전기 · 전자기 물성",
        help=(
            "비유전율(Dk) · 유전손실(Df) · 비투자율 · 전기전도율 · 체적저항률. 데이터시트나 "
            "문헌에서 온다 — 유전 물성은 주파수마다 값이 달라 주파수별로 적으면 표가 된다."
        ),
        produces=(
            Produced(
                key="relative_permittivity",
                label="비유전율(Dk)",
                si_unit="1",
                property_key="electrical.dielectric_constant",
                help="εr. 주파수를 탄다 — 어느 주파수의 값인지가 함께 간다.",
            ),
            Produced(
                key="loss_tangent",
                label="유전손실계수(Df)",
                si_unit="1",
                property_key="electrical.dissipation_factor",
                help="tan δ. 신호 손실을 정한다. 주파수를 탄다.",
            ),
            Produced(
                key="relative_permeability",
                label="비투자율",
                si_unit="1",
                property_key="magnetic.relative_permeability",
                help="μr. 비자성 재료는 1 이다 — 모르면 비워 둔다(1 을 지어 넣지 않는다).",
            ),
            Produced(
                key="conductivity",
                label="전기전도율",
                si_unit="S/m",
                property_key="electrical.conductivity",
                help="σ. 도체 손실 · 줄 발열에 쓴다. 저항률만 있으면 렌더러가 1/ρ 로 옮긴다.",
            ),
            Produced(
                key="resistivity",
                label="체적저항률",
                si_unit="ohm.m",
                property_key="electrical.resistivity_volume",
                help="ρ. 절연재는 이쪽으로 적힌다(10¹⁴ Ω·m 같은 값).",
            ),
            Produced(
                key="resistivity_temperature_coefficient",
                label="저항온도계수(TCR)",
                si_unit="1/K",
                property_key="electrical.temperature_coefficient_resistance",
                help="α. ρ(T) = ρ₀·[1 + α(T - T₀)] — 기준 온도 T₀ 와 함께 읽는다.",
            ),
        ),
        rows=(
            Produced(key="frequency", label="주파수", si_unit="Hz", help=None),
            Produced(
                key="relative_permittivity", label="비유전율(Dk)", si_unit="1", help=None
            ),
            Produced(key="loss_tangent", label="유전손실계수(Df)", si_unit="1", help=None),
            Produced(key="relative_permeability", label="비투자율", si_unit="1", help=None),
        ),
        # 열물성 바로 뒤에 서고, **종류로는 열물성보다 앞선다** — 전자 부품 재료의 카드는
        # 열물성을 곁들여 들기 마련이라(선언 카드가 저절로 싣는다) 열물성이 앞서면 유전체
        # 카드가 목록에서 「열물성」 으로 보인다. 같은 값인 광학과는 화면 차례로 갈린다.
        order=17,
        kind_priority=5,
    )
)
