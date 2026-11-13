"""피로 — 시편마다 점 하나인 S-N 데이터를 Basquin 으로 잇는다. **확장 폴더 하나로.**

피로 시험(`fatigue`)은 곡선 파일이 없다. 「표로 시험 입력」 으로 시편마다 조건(응력
진폭·응력비·주파수)과 요약값(파단 수명 `cycles_to_failure`, 런아웃 `runout`)이 들어오고,
이 묶음이 그 점들을 잇는다. 구성원은 **요약값에서** 선언으로 모은다(`from: summary`) —
곡선 열이 없는 첫 묶음이다. 계산은 `sn.py`, 카드 블록은 `card.py`.

솔버 덱은 LS-DYNA *MAT_ADD_FATIGUE 하나다(`card.py`, 2026-09-27 — 칸은 R13·R17 매뉴얼로
맞췄다). 나머지 솔버를 안 내는 이유도 거기 적었다.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import bilinear, card, sn  # noqa: F401  (card 는 import 만으로 블록을 등록한다)

register(
    id="fatigue.sn_curve",
    kind="grouping",
    label="S-N 곡선 (Basquin)",
    applies_to=("fatigue",),
    params=(
        ParamSpec(
            name="exclude_runouts",
            label="런아웃 제외",
            type="bool",
            default=True,
            help=(
                "안 부러진 채 멈춘 시편은 적합에서 뺀다 — 그 점은 수명이 아니라 하한이다. "
                "끄면 멈춘 수명을 파단 수명처럼 넣는다(안전하지 않은 쪽으로 틀린다)."
            ),
        ),
        ParamSpec(
            name="life_levels",
            label="피로 강도를 읽을 수명",
            type="str",
            default=sn.DEFAULT_LIFE_LEVELS,
            help="이 수명들에서 Basquin 곡선의 응력 진폭을 읽어 값으로 낸다. 쉼표로 구분.",
        ),
    ),
    makes_values=(
        Produced(key="basquin_a", label="Basquin A", si_unit="Pa", help="S = A·N^b 의 A."),
        # 문헌 키(2026-10-08). b 는 N 기준이든 2N 기준이든 같은 지수다. A 는 아니다 —
        # 문헌 σf′ 은 2N(역전 수) 기준이라 σf′ = A·2^(-b) 를 따로 내고 그것에 키를 단다.
        Produced(
            key="basquin_b",
            label="Basquin b",
            si_unit="1",
            help="로그-로그 기울기. 음수.",
            property_key="mechanical.fatigue_strength_exponent",
        ),
        Produced(
            key="fatigue_strength_coefficient",
            label="피로강도계수 σf′ (2N 기준)",
            si_unit="Pa",
            help="σa = σf′·(2N)^b 의 σf′ = A·2^(-b). 문헌(ASTM E466)과 같은 기준.",
            property_key="mechanical.fatigue_strength_coefficient",
        ),
        Produced(key="sn_r_squared", label="적합의 R²", si_unit="1"),
        Produced(key="point_count", label="적합에 쓴 점 수", si_unit="1"),
        Produced(key="runout_count", label="런아웃 수", si_unit="1"),
        Produced(key="cycles_min", label="가장 짧은 수명", si_unit="1"),
        Produced(key="cycles_max", label="가장 긴 수명", si_unit="1"),
        Produced(
            key="log_scatter",
            label="흩어짐 (로그 잔차 표준편차)",
            si_unit="1",
            help="같은 응력에서 수명이 얼마나 갈리나. 0.3 이면 수명이 두 배 갈린다.",
        ),
        Produced(key="strength_at_1e5", label="피로 강도 @1e5", si_unit="Pa"),
        Produced(key="strength_at_1e6", label="피로 강도 @1e6", si_unit="Pa"),
        Produced(key="strength_at_1e7", label="피로 강도 @1e7", si_unit="Pa"),
    ),
    # **구성원을 모으는 법 — 요약값에서.** 조건은 시험 조건(SI), 값은 표로 넣은 요약값.
    members={
        "from": "summary",
        "conditions": [sn.STRESS_AMPLITUDE, sn.STRESS_RATIO, sn.FREQUENCY],
        "values": [sn.CYCLES, sn.RUNOUT],
    },
    card=sn.card_blocks,
    order=30,
    version="1",
)(sn.sn_curve)


# **2구간 S-N**(VOC 61, 2026-11-14) — 한 직선은 그대로 두고 따로 선다. 계산은 `bilinear.py`.
register(
    id="fatigue.sn_bilinear",
    kind="grouping",
    label="S-N 곡선 (2구간)",
    applies_to=("fatigue",),
    params=(
        ParamSpec(
            name="exclude_runouts",
            label="런아웃 제외",
            type="bool",
            default=True,
            help=(
                "안 부러진 채 멈춘 시편은 적합에서 뺀다 — 그 점은 수명이 아니라 하한이다. "
                "그래프에는 빈 점으로 남는다."
            ),
        ),
        ParamSpec(
            name="life_levels",
            label="피로 강도를 읽을 수명",
            type="str",
            default=sn.DEFAULT_LIFE_LEVELS,
            help="이 수명들에서 2구간 곡선의 응력 진폭을 읽어 값으로 낸다. 쉼표로 구분.",
        ),
        ParamSpec(
            name="min_segment_points",
            label="구간마다 최소 파단점",
            type="int",
            default=bilinear.MIN_SEGMENT_POINTS,
            help=(
                "꺾임 위 · 아래에 이만큼 파단점이 있어야 그 자리를 꺾임 후보로 본다. 둘이면 "
                "그 구간의 기울기가 두 점을 잇는 선이 된다."
            ),
        ),
    ),
    makes_values=(
        Produced(key="sn_a1", label="1구간 절편 A1 (진폭)", si_unit="Pa", help="S = A1·N^b1."),
        Produced(key="sn_b1", label="1구간 기울기 b1", si_unit="1"),
        Produced(key="knee_cycles", label="꺾임 수명 Nc1", si_unit="1"),
        Produced(key="knee_stress", label="꺾임 응력 (진폭)", si_unit="Pa"),
        Produced(key="sn_b2", label="2구간 기울기 b2", si_unit="1"),
        Produced(key="sn_r_squared", label="적합의 R²", si_unit="1"),
        Produced(
            key="log_scatter",
            label="흩어짐 SE (log N 표준편차)",
            si_unit="1",
            help="자유도 n-4. HyperLife · MATFAT 의 SE 와 같은 뜻.",
        ),
        Produced(key="point_count", label="적합에 쓴 점 수", si_unit="1"),
        Produced(key="runout_count", label="런아웃 수", si_unit="1"),
        Produced(key="segment1_points", label="1구간 파단점 수", si_unit="1"),
        Produced(key="segment2_points", label="2구간 파단점 수", si_unit="1"),
        Produced(
            key="bilinear_p_value",
            label="F 검정 p (한 직선 대비)",
            si_unit="1",
            help="작을수록 2구간이 낫다. 꺾임을 데이터로 정해 근사다.",
        ),
        Produced(
            key="bilinear_delta_bic",
            label="ΔBIC (2구간 - 한 직선)",
            si_unit="1",
            help="음수면 2구간이 낫다.",
        ),
        Produced(
            key="bilinear_supported",
            label="2구간 근거 (1 있음 · 0 약함)",
            si_unit="1",
            help="F 검정과 ΔBIC 가 둘 다 2구간 쪽이면 1. 0 이면 한 직선(Basquin) 권장.",
        ),
        Produced(key="cycles_min", label="가장 짧은 수명", si_unit="1"),
        Produced(key="cycles_max", label="가장 긴 수명", si_unit="1"),
        Produced(key="strength_at_1e5", label="피로 강도 @1e5", si_unit="Pa"),
        Produced(key="strength_at_1e6", label="피로 강도 @1e6", si_unit="Pa"),
        Produced(key="strength_at_1e7", label="피로 강도 @1e7", si_unit="Pa"),
    ),
    members={
        "from": "summary",
        "conditions": [sn.STRESS_AMPLITUDE, sn.STRESS_RATIO, sn.FREQUENCY],
        "values": [sn.CYCLES, sn.RUNOUT],
    },
    card=bilinear.card_blocks,
    order=31,
    version="1",
)(bilinear.sn_bilinear)
