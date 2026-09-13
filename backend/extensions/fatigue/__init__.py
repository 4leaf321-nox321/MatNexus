"""피로 — 시편마다 점 하나인 S-N 데이터를 Basquin 으로 잇는다. **확장 폴더 하나로.**

피로 시험(`fatigue`)은 곡선 파일이 없다. 「표로 시험 입력」 으로 시편마다 조건(응력
진폭·응력비·주파수)과 요약값(파단 수명 `cycles_to_failure`, 런아웃 `runout`)이 들어오고,
이 묶음이 그 점들을 잇는다. 구성원은 **요약값에서** 선언으로 모은다(`from: summary`) —
곡선 열이 없는 첫 묶음이다. 계산은 `sn.py`, 카드 블록은 `card.py`.

솔버 덱은 아직 안 낸다 — LS-DYNA *MAT_ADD_FATIGUE 의 자리를 검증할 실측이 없다.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import card, sn  # noqa: F401  (card 는 import 만으로 블록을 등록한다)

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
        Produced(
            key="basquin_b", label="Basquin b", si_unit="1", help="로그-로그 기울기. 음수."
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
