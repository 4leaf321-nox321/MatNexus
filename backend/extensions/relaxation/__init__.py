"""응력완화 — 시간 영역의 완화 탄성률을 Prony 로 맞춰 **점탄성 카드**로(2026-10-12).

    처리   `relaxation.modulus`   응력완화 시험(`stress_relaxation`) 하나 → E(t) = σ/ε₀ · σ/σ₀
    묶음   `relaxation.prony`     여러 시험의 E(t) → 시간 영역 Prony(τ 자릿수 격자 · 비음수
                                  최소제곱)
                                  → 점탄성 블록 + 탄성계수(순간 탄성률)

DMA(주파수 영역)와 같은 점탄성 블록이 서므로 덱은 그쪽 것을 그대로 쓴다 — Abaqus · ANSYS ·
LS-DYNA · Radioss · OptiStruct. 계산은 `prony_time.py`. 시험 종류는 중심의 기본 시험 종류가
든다(확장은 DB 를 모른다).
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import coupling, prony_time

register(
    id="relaxation.modulus",
    kind="processing",
    label="완화 탄성률 E(t)",
    applies_to=("stress_relaxation",),
    requires_channels=(("time",), ("stress",)),
    params=(
        ParamSpec(
            name="held_strain",
            label="유지 변형률",
            type="float",
            unit="1",
            dimension="strain",
            default="@condition_held_strain",
            help="변형률 열이 없을 때 쓴다 — 있으면 그 평균을 쓰고 이 값과 견준다.",
        ),
        ParamSpec(
            name="time", label="시간 열", type="str", role="column", default=prony_time.TIME
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default=prony_time.STRESS,
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=prony_time.STRAIN,
        ),
    ),
    makes_columns=(
        Produced(key=prony_time.MODULUS, label="완화 탄성률", si_unit="Pa", help="σ(t) / ε₀."),
        Produced(key=prony_time.NORMALIZED, label="응력비 σ/σ₀", si_unit="1"),
    ),
    makes_values=(
        Produced(
            key="relaxation_initial_modulus", label="첫 측정의 완화 탄성률", si_unit="Pa"
        ),
        Produced(key="relaxation_final_modulus", label="마지막 완화 탄성률", si_unit="Pa"),
        Produced(key="relaxed_fraction", label="풀린 몫", si_unit="1"),
        Produced(key="hold_time", label="유지 시간", si_unit="s"),
        Produced(key="held_strain_used", label="쓴 유지 변형률", si_unit="1"),
    ),
    order=10,
    version="1",
)(prony_time.relaxation_modulus)

register(
    id="relaxation.prony",
    kind="grouping",
    label="완화 Prony (시간 영역)",
    applies_to=("stress_relaxation",),
    requires_channels=(("time",), ("stress",)),
    makes_values=(
        Produced(
            key="equilibrium_pa",
            label="장기 탄성률 E∞",
            si_unit="Pa",
            property_key="mechanical.prony_long_term_modulus",
        ),
        Produced(key="instantaneous_pa", label="순간 탄성률 E₀", si_unit="Pa"),
        Produced(key="normalized_rmse", label="상대 RMSE", si_unit="1"),
        Produced(key="term_count", label="항 수", si_unit="1"),
        Produced(key="point_count", label="점 수", si_unit="1"),
        Produced(key="time_min", label="가장 이른 측정", si_unit="s"),
        Produced(key="time_max", label="가장 늦은 측정", si_unit="s"),
        Produced(
            key="instantaneous_ratio",
            label="순간 탄성률 외삽 배수",
            si_unit="1",
            help="E₀ / E(첫 측정). 1.5 를 넘으면 순간 탄성률은 대부분 외삽이다.",
        ),
        Produced(key="reference_temperature_k", label="기준 온도", si_unit="K"),
    ),
    members={
        "from": "adopted_result",
        "columns": [prony_time.TIME, prony_time.MODULUS],
        "conditions": [prony_time.TEMPERATURE],
    },
    card=prony_time.card_blocks,
    order=40,
    # 2: 가장 짧은 τ 를 첫 측정 시각으로 묶음 · 외삽 배수를 냄(2026-11-14, VOC 52).
    # 3: 온도가 2 K 넘게 섞이면 묶지 않는다(2026-11-15) — 전에는 경고만.
    version="3",
)(prony_time.relaxation_prony)

# **응력완화 + DMA 마스터커브**(2026-11-15, VOC 52 · ADR 0087 1단계) — 응력완화가 모르는
# 짧은 시간(하중을 거는 동안)을 같은 재료의 DMA 로 메운다. 계산은 `coupling.py`. 두 종류의
# 시험을 받으므로 구성원 규칙을 종류마다 적고(중심 `by_test_type`), 카드는 응력완화 시험의
# 것으로 만든다(`card_test_type`).
register(
    id="relaxation.dma_coupled",
    kind="grouping",
    label="응력완화 + DMA 마스터커브(짧은 시간 메우기)",
    applies_to=(coupling.RELAXATION, "dma_sweep"),
    makes_values=(
        Produced(key="equilibrium_pa", label="장기 탄성률 E∞", si_unit="Pa"),
        Produced(key="instantaneous_pa", label="순간 탄성률 E₀", si_unit="Pa"),
        Produced(key="normalized_rmse", label="상대 RMSE", si_unit="1"),
        Produced(key="normalized_rmse_dma", label="상대 RMSE(DMA 쪽)", si_unit="1"),
        Produced(
            key="normalized_rmse_relaxation", label="상대 RMSE(응력완화 쪽)", si_unit="1"
        ),
        Produced(key="term_count", label="항 수", si_unit="1"),
        Produced(key="point_count", label="점 수", si_unit="1"),
        Produced(key="time_min", label="가장 짧은 시간(DMA)", si_unit="s"),
        Produced(key="time_max", label="가장 늦은 측정(응력완화)", si_unit="s"),
        Produced(key="instantaneous_ratio", label="순간 탄성률 외삽 배수", si_unit="1"),
        Produced(key="reference_temperature_k", label="기준 온도(응력완화 온도)", si_unit="K"),
        Produced(
            key="overlap_ratio",
            label="겹친 구간 비(응력완화 ÷ DMA)",
            si_unit="1",
            help=(
                "두 시험이 함께 덮는 시간대의 비 중앙값. 5 % 넘게 벗어나면 경고, 25 % 면 "
                "막는다."
            ),
        ),
        Produced(key="overlap_points", label="겹친 구간의 응력완화 점 수", si_unit="1"),
        Produced(key="dma_join_time_s", label="DMA 로 메운 시간 끝", si_unit="s"),
        Produced(key="dma_log10_shift", label="DMA 이동 log a_T", si_unit="1"),
        Produced(key="dma_reference_temperature_k", label="마스터커브 기준 온도", si_unit="K"),
        Produced(
            key="relaxation_only_instantaneous_pa",
            label="응력완화만의 순간 탄성률",
            si_unit="Pa",
            help="잇지 않았다면의 E₀ — 잇는 것이 얼마나 바꿨는지 견준다.",
        ),
    ),
    members={
        "by_test_type": {
            coupling.RELAXATION: {
                "from": "adopted_result",
                "columns": [prony_time.TIME, prony_time.MODULUS],
                "conditions": [prony_time.TEMPERATURE],
                "optional": [coupling.HELD_STRAIN],
                "material_scalars": [coupling.LVE_LIMIT],
            },
            "dma_sweep": {"from": "master_curve"},
        }
    },
    card=coupling.card_blocks,
    card_test_type=coupling.RELAXATION,
    order=41,
    version="1",
)(coupling.couple)
