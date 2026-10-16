"""굽힘 시험(3점 · 4점) — 굽힘 응력 · 변형률 · 탄성률(등가 E) · 강도, 그리고 등가 E
카드(2026-10-16).

    처리   flexural.engineering   하중 · 처짐 → 굽힘 응력 · 변형률(3점 · 4점,
                                  처짐계 · 크로스헤드,
                                  장비 컴플라이언스, D790 큰 처짐 보정)
           flexural.modulus       굽힘 탄성률(등가 E) — 현 · 회귀 · 할선 · 접선 · 응력 띠
           flexural.strength      굽힘 강도 · 파단 · ISO 178 규정 처짐 응력 σfC
    묶음   flexural.equivalent    시편 여럿의 굽힘 탄성률 → 등가 E 카드(탄성 블록) + 참고 물성

**규격마다 다른 것은 고를 수 있게 둔다** — 처리 단계는 시편이 어느 규격인지 모른다(숫자 치수만
받는다). 3점 · 4점은 하중 스팬으로, 처짐 측정은 처짐 열로, 탄성률 정의는 방법 · 구간으로
가른다.
규격별로 무엇을 고르는지는 가이드에 있다. 시험 종류 · 시편 분류 · 규격 카탈로그는 중심이 든다
(확장은 DB 를 모른다). 계산은 `bending.py`.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import bending

_METHOD_LABELS = {
    "chord": "현 (두 변형률 사이)",
    "regression": "회귀 (구간 최소제곱)",
    "secant": "할선 (원점에서 구간 끝)",
    "tangent": "접선 (가장 가파른 처음 직선)",
    "stress_window": "응력 띠 (최대 응력의 비율)",
}
_METHOD_HELP = {
    "chord": "ISO 178 · ISO 14125: 변형률 0.05% · 0.25% 두 점의 응력을 잇는 기울기.",
    "regression": "구간 안 점들의 최소제곱 — 잡음이 많은 곡선.",
    "secant": "원점에서 구간 끝까지 — 규격이 「몇 % 에서의 할선」 을 정할 때.",
    "tangent": "ASTM D790 · D6272 · D7264: 처음 직선 구간의 가장 가파른 접선"
    "(토우를 건너뛴다).",
    "stress_window": "칩 · 모듈 · 세라믹처럼 변형률이 아주 작을 때 — "
    "최대 응력의 10~40% 사이 회귀.",
}

register(
    id="flexural.engineering",
    kind="processing",
    label="굽힘 응력-변형률",
    # **키로만 거른다** — 하중 · 변위는 인장도 같아서, 채널로 거르면 인장 시험의 단계 목록에
    # 굽힘이 뜬다(`tests/architecture/test_applies_to.py` 의 `SAME_SHAPE_AS_TENSILE`).
    applies_to=("flexural",),
    params=(
        ParamSpec(
            name="support_span",
            label="지지 스팬 L",
            type="float",
            unit="m",
            dimension="length",
            default="@specimen_span",
            required=True,
            help="받침 사이 거리. 시편 기록(규격)에서 옵니다 — ISO 178 · D790 은 두께의 16배.",
        ),
        ParamSpec(
            name="load_span",
            label="하중 스팬 Lᵢ (4점)",
            type="float",
            unit="m",
            dimension="length",
            # **있으면 쓴다**(`@?`) — 시편에 하중 스팬이 있으면 4점, 없으면 3점. `@` 로 두면
            # 3점 시편이 멈추고, 비워 두면 4점 시편이 3점 식으로 조용히 계산된다.
            default="@?specimen_load_span",
            help=(
                "누르는 두 노즈 사이 거리. 기본은 시편 기록에 **있으면** 그 값(4점), 없으면 "
                "비움(3점)입니다. 4점 규격(D6272 · C1161)은 반드시 있어야 하므로 "
                "「@specimen_load_span」 으로 둡니다 — 없으면 멈춥니다."
            ),
        ),
        ParamSpec(
            name="width",
            label="폭 b",
            type="float",
            unit="m",
            dimension="length",
            default="@specimen_width",
            required=True,
        ),
        ParamSpec(
            name="thickness",
            label="두께 h",
            type="float",
            unit="m",
            dimension="length",
            default="@specimen_thickness",
            required=True,
            help="칩 · 모듈은 전체 두께 — 그 두께의 균질한 보로 본 등가 E 가 나옵니다.",
        ),
        ParamSpec(
            name="deflection_source",
            label="처짐을 무엇으로",
            type="choice",
            default="auto",
            choices=("auto", "deflection", "displacement"),
            choice_labels={
                "auto": "자동 (처짐계가 있으면 그것)",
                "deflection": "처짐계 (LVDT · 비디오)",
                "displacement": "크로스헤드 변위",
            },
            help="크로스헤드에는 장비 자신의 처짐이 섞입니다 — 컴플라이언스로 뺍니다.",
        ),
        ParamSpec(
            name="deflection_point",
            label="처짐을 잰 자리",
            type="choice",
            default="auto",
            choices=("auto", "midspan", "load_point"),
            choice_labels={
                "auto": "자동 (4점 크로스헤드면 하중점, 아니면 가운데)",
                "midspan": "스팬 가운데",
                "load_point": "하중점 (누르는 노즈)",
            },
            help="3점은 둘이 같습니다. 4점에서 크로스헤드는 하중점의 처짐입니다.",
        ),
        ParamSpec(
            name="machine_compliance",
            label="장비 컴플라이언스 C",
            type="float",
            unit="m/N",
            default=0.0,
            help=(
                "크로스헤드 처짐에서 뺄 장비 처짐 비율(처짐 = 측정 - C·하중). 받침끼리 맞대고 "
                "누른 하중-변위 기울기의 역수. 처짐계로 재면 0."
            ),
        ),
        ParamSpec(
            name="large_deflection",
            label="큰 처짐 보정 (D790)",
            type="bool",
            default=False,
            help=(
                "처짐이 스팬의 10% 를 넘을 때 ASTM D790 의 보정식을 응력에 적용합니다(3점만)."
            ),
        ),
        ParamSpec(
            name="force", label="하중 열", type="str", role="column", default=bending.FORCE
        ),
    ),
    makes_columns=(
        Produced(
            key=bending.STRAIN,
            label="굽힘 변형률",
            si_unit="1",
            help="바깥 면의 변형률 — 3점이면 6hδ/L².",
        ),
        Produced(
            key=bending.STRESS,
            label="굽힘 응력",
            si_unit="Pa",
            help="바깥 면의 응력 — 3점이면 3FL/(2bh²).",
        ),
        Produced(
            key=bending.USED, label="쓴 처짐", si_unit="m", help="영점 · 컴플라이언스 보정 뒤."
        ),
    ),
    makes_values=(Produced(key="span_to_depth_ratio", label="스팬/두께", si_unit="1"),),
    order=10,
    version="1",
)(bending.engineering)

register(
    id="flexural.modulus",
    kind="processing",
    label="굽힘 탄성률 (등가 E)",
    applies_to=("flexural",),
    params=(
        ParamSpec(
            name="method",
            label="방법",
            type="choice",
            default="chord",
            choices=tuple(_METHOD_LABELS),
            choice_labels=_METHOD_LABELS,
            choice_help=_METHOD_HELP,
            help="어느 방법이 옳은지는 규격이 정합니다 — 같은 곡선에서도 몇 % 갈립니다.",
        ),
        ParamSpec(
            name="minimum_strain",
            label="구간 시작",
            type="float",
            unit="1",
            dimension="strain",
            default=0.0005,
            when={"method": ("chord", "regression")},
        ),
        ParamSpec(
            name="maximum_strain",
            label="구간 끝",
            type="float",
            unit="1",
            dimension="strain",
            default=0.0025,
            when={"method": ("chord", "regression", "secant")},
        ),
        ParamSpec(
            name="band_low",
            label="응력 띠 아래끝",
            type="float",
            unit="1",
            default=0.1,
            when={"method": ("stress_window",)},
            help="최대 응력에 대한 비율.",
        ),
        ParamSpec(
            name="band_high",
            label="응력 띠 위끝",
            type="float",
            unit="1",
            default=0.4,
            when={"method": ("stress_window",)},
        ),
        ParamSpec(
            name="tangent_width",
            label="접선 창 너비",
            type="float",
            unit="1",
            dimension="strain",
            default=0.001,
            when={"method": ("tangent",)},
            help="이 변형률 너비의 창을 밀며 가장 가파른 회귀 기울기를 고릅니다.",
        ),
        ParamSpec(
            name="strain", label="변형률 열", type="str", role="column", default=bending.STRAIN
        ),
        ParamSpec(
            name="stress", label="응력 열", type="str", role="column", default=bending.STRESS
        ),
    ),
    makes_values=(
        Produced(
            key="flexural_modulus",
            label="굽힘 탄성률(등가 E)",
            si_unit="Pa",
            property_key="mechanical.flexural_modulus",
        ),
        Produced(key="flexural_modulus_r2", label="굽힘 탄성률 회귀 R²", si_unit="1"),
        Produced(key="flexural_stiffness", label="굽힘 강성(하중/처짐)", si_unit="N/m"),
    ),
    order=20,
    version="1",
)(bending.modulus)

register(
    id="flexural.strength",
    kind="processing",
    label="굽힘 강도",
    applies_to=("flexural",),
    params=(
        ParamSpec(
            name="strain", label="변형률 열", type="str", role="column", default=bending.STRAIN
        ),
        ParamSpec(
            name="stress", label="응력 열", type="str", role="column", default=bending.STRESS
        ),
    ),
    makes_values=(
        Produced(
            key="flexural_strength",
            label="굽힘 강도",
            si_unit="Pa",
            property_key="mechanical.flexural_strength",
        ),
        Produced(
            key="flexural_strain_at_strength", label="굽힘 강도에서의 변형률", si_unit="1"
        ),
        Produced(
            key="flexural_stress_at_break", label="파단 굽힘 응력(마지막 점)", si_unit="Pa"
        ),
        Produced(
            key="flexural_strain_at_break", label="파단 굽힘 변형률(마지막 점)", si_unit="1"
        ),
        Produced(
            key="flexural_stress_at_3_5pct",
            label="규정 처짐 응력 σfC(변형률 3.5%)",
            si_unit="Pa",
        ),
    ),
    order=30,
    version="1",
)(bending.strength)

register(
    id="flexural.equivalent",
    kind="grouping",
    label="굽힘 등가 탄성률 (칩 · 모듈 · 적층)",
    applies_to=("flexural",),
    makes_values=(
        Produced(
            key="flexural_modulus",
            label="등가 E (평균)",
            si_unit="Pa",
            property_key="mechanical.flexural_modulus",
        ),
        Produced(key="flexural_modulus_sd", label="표준편차", si_unit="Pa"),
        Produced(key="flexural_modulus_cv", label="변동계수", si_unit="1"),
        Produced(key="flexural_modulus_min", label="최솟값", si_unit="Pa"),
        Produced(key="flexural_modulus_max", label="최댓값", si_unit="Pa"),
        Produced(key="sample_count", label="시편 수", si_unit="1"),
        Produced(key="flexural_strength", label="굽힘 강도 (평균)", si_unit="Pa"),
    ),
    # 채택된 결과의 굽힘 탄성률 — 없으면 사람이 표로 적은 요약값에서(보고서만 있는 시험).
    members={
        "from": "measured_or_stated",
        "values": ["flexural_modulus"],
        "optional": ["flexural_strength"],
    },
    card=bending.card_blocks,
    order=40,
    version="1",
)(bending.equivalent_modulus)
