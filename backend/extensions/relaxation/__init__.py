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

from . import prony_time

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
        Produced(key="reference_temperature_k", label="기준 온도", si_unit="K"),
    ),
    members={
        "from": "adopted_result",
        "columns": [prony_time.TIME, prony_time.MODULUS],
        "conditions": [prony_time.TEMPERATURE],
    },
    card=prony_time.card_blocks,
    order=40,
    version="1",
)(prony_time.relaxation_prony)
