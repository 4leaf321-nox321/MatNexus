"""인장 덧붙이기 — **처리 단계와 묶음을 확장 폴더에서 등록하는지 재는 자리.**

`ghosh_hardening` 이 적합식(①)을, `johnson_cook_static` 이 카드 블록을 확장 폴더에서
붙였다. 남은 창구가 둘이었다 — **처리 단계**(시험 하나: 곡선 → 스칼라)와 **묶음**(여러
시험 → 하나). 창구는 같은 `registry.register` 인데 확장에서 써 본 적이 없었다
(2026-09-13, [계획] 계산 확장 1단계). 이 폴더가 둘을 실제로 붙인다.

- `yield_ratio` — 항복비(항복강도 ÷ 인장강도). 앞 단계가 낸 값을 `@` 로 받는 단계.
- `temperature_family` — 온도별 인장 곡선을 묶어 **온도별 소성 표**와 온도 연화
  요약(기울기·Johnson-Cook m)을 낸다. 속도 가족과 같은 모양. 구성원은 파이썬
  수집기 없이 **선언**(`meta["members"]`)으로 모으고, 카드는 `card=` 로 선언한
  함수가 블록을 만든다(`/fitting/cards/from-group`). 블록과 Abaqus 덱은 `card.py`.

중심 코드는 한 줄도 안 고쳤다. 계산은 옆 파일에 있다.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import (  # noqa: F401  (card 는 import 만으로 블록·렌더러를 등록한다)
    card,
    ratio,
    temperature,
)

register(
    id="tensile.yield_ratio",
    kind="processing",
    label="항복비",
    applies_to=("tensile",),
    # 키만으로 거르지 않는다 — 변위·하중을 재는 시험이면 강도가 나오고 항복비가 선다.
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="proof_stress",
            label="항복강도",
            type="float",
            unit="Pa",
            default="@proof_stress",
            required=True,
            help="항복강도 단계가 낸 값. 손으로 적으면 항복 정의를 바꿔도 여기는 옛 값이 "
            "남는다.",
        ),
        ParamSpec(
            name="tensile_strength",
            label="인장강도",
            type="float",
            unit="Pa",
            default="@tensile_strength",
            required=True,
            help="인장강도 단계가 낸 값.",
        ),
    ),
    makes_values=(
        Produced(
            key="yield_ratio",
            label="항복비",
            si_unit="1",
            help="항복강도 ÷ 인장강도. 강구조 규격이 상한(예: 0.85)을 둔다.",
        ),
    ),
    # 강도(70)·항복강도(60) 뒤, 소성 곡선(90) 앞 — 재샘플(95)이 맨 끝인 것은 규칙이다.
    order=85,
    version="1",
)(ratio.yield_ratio)

register(
    id="tensile.temperature_family",
    kind="grouping",
    label="온도별 소성 곡선",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="bin_kelvin",
            label="같은 온도로 볼 폭",
            type="float",
            unit="K",
            default=5.0,
            help=(
                "온도가 이 폭 안에서 다르면 같은 온도로 묶음. 5 면 296 과 299 는 한 묶음. "
                "장비가 목표 온도를 정확히 재현하지 못하므로 0 이면 시편마다 따로 섬."
            ),
        ),
        ParamSpec(
            name="levels",
            label="응력비를 읽을 변형률",
            type="str",
            default=temperature.DEFAULT_LEVELS,
            dimension="strain",
            help=(
                "이 진소성변형률들에서 기준 온도 대비 응력비를 읽음. 쉼표로 구분. "
                "첫 값에서 연화 기울기(dσ/dT)도 냄."
            ),
        ),
        ParamSpec(
            name="model",
            label="온도 연화 식",
            type="choice",
            choices=temperature.MODELS,
            default="none",
            choice_labels={"none": "식 없이 표만", "johnson_cook": "Johnson-Cook (m 만)"},
            choice_help={
                "none": "온도별 표만 산출. 솔버가 표를 그대로 받으면 충분.",
                "johnson_cook": (
                    "σ/σ₀ = 1 - T*^m, T* = (T-T₀)/(T_melt-T₀). 기준 온도 T₀ 는 가장 낮은 "
                    "묶음, 녹는점은 아래 칸. 응력이 안 내린 온도는 못 넣음."
                ),
            },
            help="온도별 표에 더해 응력비를 식으로 요약할지 여부.",
        ),
        ParamSpec(
            name="melt_temperature",
            label="녹는점",
            type="float",
            unit="K",
            default=0.0,
            help=(
                "Johnson-Cook 을 고를 때만. 기준 온도보다 커야 함"
                "(강 ≈ 1,800 K, 알루미늄 ≈ 930 K)."
            ),
        ),
    ),
    makes_values=(
        Produced(key="temperature_count", label="온도 묶음 수", si_unit="1"),
        Produced(key="reference_temperature", label="기준 온도", si_unit="K"),
        Produced(key="temperature_min", label="가장 낮은 온도", si_unit="K"),
        Produced(key="temperature_max", label="가장 높은 온도", si_unit="K"),
        Produced(
            key="softening_slope",
            label="온도 연화 기울기",
            si_unit="Pa/K",
            help="첫 변형률에서 읽은 응력의 온도에 대한 기울기(최소제곱). 음수면 연화.",
        ),
        Produced(key="softening_r_squared", label="기울기의 R²", si_unit="1"),
        Produced(key="jc_m", label="Johnson-Cook m", si_unit="1"),
        Produced(key="model_r_squared", label="식의 R²", si_unit="1"),
    ),
    # **구성원을 모으는 법을 선언한다.** 채택된 결과의 두 열과 시험 조건의 온도.
    # 파이썬 수집기가 없어도 grouping 이 이 선언을 읽는다(`app/modules/grouping`).
    # `register` 의 남는 키워드는 `Plugin.meta` 로 간다.
    members={
        "from": "adopted_result",
        "columns": [temperature.PLASTIC_STRAIN, temperature.TRUE_STRESS],
        "conditions": [temperature.TEMPERATURE],
    },
    # **카드를 만드는 법도 선언한다.** 묶음 결과(값·상세·경고)를 블록으로 바꾸는
    # 함수 — 재료·탄성·계보는 중심의 공용 길(`/fitting/cards/from-group`)이 맡는다.
    card=temperature.card_blocks,
    order=25,
    version="2",
)(temperature.temperature_family)
