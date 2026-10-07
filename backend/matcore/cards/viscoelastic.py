"""선형 점탄성 카드의 블록 — Prony 급수.

**이 파일이 D7 의 수용 기준을 재는 자리다.** 새 물성 1종을 카드에 더하는 데 든
것이 이 파일 하나인지, 아니면 마이그레이션과 스키마와 화면이 또 딸려 오는지.

## 순간 탄성률은 탄성 블록이 든다

`*ELASTIC` 에 들어갈 E₀ 를 여기서 내지 않는다. **한 자리는 한 블록이 채운다** —
둘이 채우면 어느 값이 실릴지 정해져 있지 않고, Abaqus 는 `*VISCOELASTIC` 이
있을 때 `*ELASTIC` 을 순간 탄성률로 읽으므로 평형 탄성률이 실리면 재료가 통째로
무르게 계산된다. 그런데 덱은 멀쩡히 돌고 결과도 그럴듯하다.

그래서 점탄성 카드를 만들 때 E₀ 를 **탄성 블록에** 출처 `prony` 로 넣는다.
`abaqus_viscoelastic` 렌더러가 `*ELASTIC` 을 탄성 블록에서 읽는다 — 여기서 E₀ 를
내면 두 곳이 같은 값을 들게 되고, 어긋나는 순간 어느 쪽이 덱에 실렸는지 알 수 없다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

VISCOELASTIC = register_block(
    BlockSpec(
        key="viscoelastic",
        label="점탄성",
        help=(
            "마스터커브에 맞춘 일반화 Maxwell 계수. **계수는 기준 온도의 것이다** — 다른 "
            "온도로 쓰려면 온도 이동(WLF C1 · C2 또는 Arrhenius Ea)이 함께 가야 하고, 그 "
            "이동도 맞춘 온도 범위 안에서만 잰 것이다."
        ),
        produces=(
            Produced(
                key="equilibrium_pa",
                label="평형 탄성률",
                si_unit="Pa",
                help="완화가 끝난 뒤(t→∞) 남는 탄성률. E∞ 다.",
                property_key="mechanical.prony_long_term_modulus",
            ),
            Produced(
                key="instantaneous_pa",
                label="순간 탄성률",
                si_unit="Pa",
                help="t=0 의 탄성률. E₀ = E∞ + ΣEᵢ 이고, 덱의 *ELASTIC 이 이 값이다.",
            ),
            Produced(
                key="reference_temperature_k",
                label="기준 온도",
                si_unit="K",
                help="마스터커브를 겹친 온도. **이 카드가 유효한 온도다.**",
            ),
            Produced(
                key="normalized_rmse",
                label="정규화 RMSE",
                si_unit="1",
                help="E'·E'' 를 함께 맞춘 잔차. 작을수록 잘 맞는다.",
            ),
            Produced(
                key="bic",
                label="BIC",
                si_unit="1",
                help="항 수를 고른 근거. 후보를 여럿 맞춰 이 값이 가장 작은 것을 골랐다.",
            ),
            Produced(
                key="shift_method",
                label="이동 방법",
                si_unit="1",
                help="WLF·Arrhenius·수동 중 마스터커브를 겹칠 때 쓴 것.",
            ),
            # **온도 이동 상수**(2026-10-07). 전에는 마스터커브 기록에만 남고 여기 안 실려,
            # 덱이 다른 온도의 이동(`*TRS` · `TB,SHIFT`)을 적을 수 없었다.
            Produced(
                key="shift_c1",
                label="WLF C1",
                si_unit="1",
                help="log10 a_T = -C1·(T - T_ref) / (C2 + T - T_ref). 기준 온도는 위의 것.",
            ),
            Produced(
                key="shift_c2",
                label="WLF C2",
                si_unit="K",
                help="온도 **차**다 — K 와 °C 가 같은 수다.",
            ),
            Produced(
                key="shift_activation_energy",
                label="Arrhenius 활성화 에너지",
                si_unit="J/mol",
                help="log10 a_T = Ea / (2.303 R) · (1/T - 1/T_ref).",
            ),
            Produced(
                key="shift_temperature_min_k",
                label="이동을 맞춘 가장 낮은 온도",
                si_unit="K",
                help="이 아래는 이동 식을 외삽한 것이다.",
            ),
            Produced(
                key="shift_temperature_max_k",
                label="이동을 맞춘 가장 높은 온도",
                si_unit="K",
                help="이 위는 이동 식을 외삽한 것이다.",
            ),
            Produced(
                key="shift_max_residual",
                label="이동인자 최대 어긋남",
                si_unit="1",
                help=(
                    "맞춘 log10 a_T 와 관측값의 가장 큰 차(자릿수). 크면 그 식이 이 재료 · 이 "
                    "온도 범위에 안 맞는다."
                ),
            ),
        ),
        rows=(
            Produced(key="relaxation_time_s", label="완화시간 τᵢ", si_unit="s"),
            Produced(key="modulus_pa", label="탄성률 Eᵢ", si_unit="Pa"),
            Produced(
                key="relative_modulus",
                label="상대 탄성률 gᵢ",
                si_unit="1",
                help="Eᵢ/E₀. Abaqus *VISCOELASTIC 이 그대로 먹는 값이다.",
            ),
        ),
        order=40,
        kind_priority=4,
        from_tests=("dma_sweep",),
    )
)


LVE = register_block(
    BlockSpec(
        key="lve",
        label="선형탄성구간(LVE) 탄성률",
        help=(
            "DMA 변형률 스윕의 **선형 구간**에서 읽은 저장 탄성률과 그 한계. 진동·소변형 "
            "해석의 탄성계수로 쓴다 — 한계 변형률 너머에서는 이 값이 유효하지 않다. "
            "Prony(점탄성 블록)와 달리 시간 의존이 없다: **한 주파수·한 온도의 값**이다."
        ),
        produces=(
            Produced(
                key="youngs_modulus",
                label="저장 탄성률 (선형 구간)",
                si_unit="Pa",
                help="선형 구간 점들의 평균 E′. 여러 시편이면 그 시편 평균들의 평균.",
                # 이름은 youngs_modulus 지만 잰 것은 E′ 다 — 문헌으로는 저장탄성률이다.
                property_key="mechanical.storage_modulus",
            ),
            Produced(
                key="lve_strain_limit",
                label="선형 한계 변형률",
                si_unit="1",
                help="여기까지 E′ 가 평탄하다. **이 카드가 유효한 변형률 범위다.**",
            ),
            Produced(
                key="sample_count",
                label="시편 수",
                si_unit="1",
                help="평균에 들어간 시편 수. 1 이면 평균이 아니라 그 시편의 값이다.",
            ),
            Produced(
                key="coefficient_of_variation",
                label="E′ 변동계수",
                si_unit="1",
                help="시편 간 흩어짐. 시편이 하나면 없다.",
            ),
            Produced(
                key="frequency_hz",
                label="주파수",
                si_unit="Hz",
                help="스윕을 돌린 주파수. **이 주파수에서의 값이다.**",
            ),
            Produced(
                key="temperature_k",
                label="온도",
                si_unit="K",
                help="스윕을 돌린 온도. **이 온도에서의 값이다.**",
            ),
        ),
        order=45,
        kind_priority=5,
        from_tests=("dma_sweep",),
    )
)
