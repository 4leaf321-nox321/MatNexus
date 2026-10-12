"""크리프 — 시험에서 식까지, 식에서 덱까지(2026-10-08 덱 · 2026-10-12 시험).

    처리   `creep.rate`   크리프 시험(`creep`) 하나 → 크리프 변형률 열 · 최소(정상상태)
                          크리프 속도
    묶음   `creep.law`    여러 시험의 (응력, 온도, 최소 속도) → Norton(± Arrhenius) · Garofalo
                          → 카드의 모델 파라미터 블록(`model_params`, ADR 0029)
    덱     `ansys_creep`         TB,CREEP TBOPT 8 — Garofalo
           `ansys_creep_norton`  TB,CREEP TBOPT 10 — Norton

계산은 `law.py`, 덱은 `deck.py`. 시험 종류(채널 · 조건)는 중심의 기본 시험 종류가 든다 — 확장은
DB 를 모른다. 보고서의 최소 크리프 속도만 있으면 시험을 「표로 입력」 해도 묶음에 든다.

Anand(확장 `anand`)와 함께 솔더 신뢰성 해석의 두 축이다 — Anand 는 점소성 하나로, 크리프는
탄소성 위에 정상상태 크리프를 얹는다.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import deck, law  # noqa: F401  (deck 은 import 만으로 렌더러를 등록한다)

register(
    id="creep.rate",
    kind="processing",
    label="최소 크리프 속도",
    applies_to=("creep",),
    requires_channels=(("time",), ("strain",)),
    params=(
        ParamSpec(name="time", label="시간 열", type="str", role="column", default=law.TIME),
        ParamSpec(
            name="strain", label="변형률 열", type="str", role="column", default=law.STRAIN
        ),
    ),
    makes_columns=(
        Produced(
            key=law.CREEP_STRAIN,
            label="크리프 변형률",
            si_unit="1",
            help="변형률에서 첫 점(하중을 다 건 순간)의 값을 뺀 것.",
        ),
    ),
    makes_values=(
        Produced(
            key=law.RATE,
            label="최소 크리프 속도",
            si_unit="1/s",
            help=(
                "정상상태(2차) 크리프의 변형률 속도 — 묶음이 이 값으로 Norton · Garofalo 를 "
                "맞춘다."
            ),
            property_key="mechanical.creep_rate",
        ),
        Produced(key="creep_initial_strain", label="하중 직후 변형률", si_unit="1"),
        Produced(key="creep_strain_final", label="마지막 크리프 변형률", si_unit="1"),
        Produced(key="creep_duration", label="시험 시간", si_unit="s"),
        Produced(key="creep_window_start", label="속도 창 시작", si_unit="s"),
        Produced(key="creep_window_end", label="속도 창 끝", si_unit="s"),
    ),
    order=10,
    version="1",
)(law.creep_rate)

register(
    id="creep.law",
    kind="grouping",
    label="크리프 식 (Norton · Garofalo)",
    applies_to=("creep",),
    makes_values=(
        Produced(
            key="norton_a",
            label="Norton A",
            si_unit="1",
            help="ε̇ = A·σ^n·exp(-Q/RT) 의 A — 단위가 1/(s·Pa^n) 이라 n 에 따라 다르다.",
        ),
        Produced(
            key="norton_n",
            label="응력 지수 n",
            si_unit="1",
            help="log-log 기울기. 금속의 전위 크리프는 대개 3~8.",
            property_key="mechanical.norton_exponent",
        ),
        Produced(
            key="activation_energy",
            label="활성화 에너지 Q",
            si_unit="J/mol",
            help="온도가 둘 이상일 때만 선다.",
        ),
        Produced(key="norton_r_squared", label="Norton R² (ln ε̇)", si_unit="1"),
        Produced(key="garofalo_c1", label="Garofalo C1", si_unit="1/s"),
        Produced(key="garofalo_c2", label="Garofalo C2", si_unit="1/Pa"),
        Produced(key="garofalo_c3", label="Garofalo C3", si_unit="1"),
        Produced(key="garofalo_c4", label="Garofalo C4 (Q/R)", si_unit="K"),
        Produced(key="garofalo_r_squared", label="Garofalo R² (ln ε̇)", si_unit="1"),
        Produced(key="point_count", label="점 수", si_unit="1"),
        Produced(key="temperature_count", label="온도 수", si_unit="1"),
        Produced(key="stress_min", label="가장 낮은 응력", si_unit="Pa"),
        Produced(key="stress_max", label="가장 높은 응력", si_unit="Pa"),
        Produced(key="temperature_min", label="가장 낮은 온도", si_unit="K"),
        Produced(key="temperature_max", label="가장 높은 온도", si_unit="K"),
    ),
    # **구성원 — 잰 값이 있으면 그것, 없으면 표로 적은 값.** 처리가 낸 최소 속도가 없으면
    # 보고서의 값을 적어도 든다(어느 쪽인지 구성원에 남는다).
    members={
        "from": "measured_or_stated",
        "conditions": [law.STRESS, law.TEMPERATURE],
        "values": [law.RATE],
    },
    card=law.card_blocks,
    order=40,
    version="1",
)(law.creep_law)
