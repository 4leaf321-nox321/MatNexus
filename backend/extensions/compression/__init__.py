"""압축 시험 — 고무 · 폼 · 플라스틱의 압축 응력-변형률 · 탄성률 · 규격 지표(2026-10-16).

    처리   compression.engineering   하중 · 변위(또는 압축계 변형률) → 압축 응력 ·
                                     변형률(양수),
                                     부호 자동, 접촉점, 사이클(Mullins · ISO 3386 4번째) 선택
           compression.toe_compensation  토우 보정 — 인장과 같은 계산(압축 열로)
           compression.modulus       압축 탄성률 — 현 · 회귀 · 할선 · 접선 · 응력 띠
           compression.indices       10 · 20 · 25 · 40 · 50 · 65% 압축 응력, 압축 강도,
                                     평탄 응력 · 치밀화 변형률 · 흡수 에너지(폼)

    적합   <식>_compression          초탄성 식(Neo-Hookean · Mooney-Rivlin · Yeoh · Ogden)을
                                     단축 압축 데이터로 — 블록 mode 「단축 압축」(2026-10-20)
    묶음   compression.foam          시편 여럿의 공칭 압축 곡선 평균 → 폼 카드
                                     (`foam_curve` 블록, LS-DYNA *MAT_LOW_DENSITY_FOAM)

규격마다 다른 것은 고를 수 있게 둔다 — 처리 단계는 규격 이름을 모른다(숫자 치수만
받는다). 시험 종류 · 시편 분류 · 규격 카탈로그는 중심이 든다.
계산은 `compress.py`.
"""

from __future__ import annotations

from matcore import fitting
from matcore.fitting import hyperelastic
from matcore.processing.tensile import TOE_VALUES, toe_compensation_on, toe_params
from matcore.registry import ParamSpec, Produced, register

from . import card as _card  # noqa: F401  (블록 · 덱 등록)
from . import compress, foam

_METHOD_LABELS = {
    "chord": "현 (두 변형률 사이)",
    "regression": "회귀 (구간 최소제곱)",
    "secant": "할선 (원점에서 구간 끝)",
    "tangent": "접선 (가장 가파른 처음 직선)",
    "stress_window": "응력 띠 (최대 응력의 비율)",
}
_METHOD_HELP = {
    "chord": "ISO 604: 변형률 0.05% · 0.25% 두 점의 응력을 잇는 기울기(플라스틱).",
    "regression": "구간 안 점들의 최소제곱 — 잡음이 많은 곡선.",
    "secant": "고무 · 폼: 원점에서 정한 변형률(예: 10%)까지의 할선 탄성률.",
    "tangent": "ASTM D695 · D1621 · ISO 844: 처음 직선 구간의 가장 가파른 접선.",
    "stress_window": "최대 응력의 비율 사이 회귀 — 변형률 구간을 정하기 어려울 때.",
}

register(
    id="compression.engineering",
    kind="processing",
    label="압축 응력-변형률",
    # **키로만 거른다** — 하중 · 변위는 인장도 같아서, 채널로 거르면 인장 시험의 단계 목록에
    # 압축이 뜬다(`tests/architecture/test_applies_to.py` 의 `SAME_SHAPE_AS_TENSILE`).
    applies_to=("compression",),
    params=(
        ParamSpec(
            name="height",
            label="초기 높이 h₀",
            type="float",
            unit="m",
            dimension="length",
            default="@specimen_height",
            required=True,
            help="누르는 방향의 시편 높이. 변위를 이것으로 나눠 변형률을 만듭니다.",
        ),
        ParamSpec(
            name="area",
            label="하중 면적",
            type="float",
            unit="m2",
            default="@specimen_area",
            required=True,
            help="누르는 면의 넓이 — 원통이면 직경에서, 직육면체면 가로 x 세로.",
        ),
        ParamSpec(
            name="source",
            label="변형을 무엇으로",
            type="choice",
            default="auto",
            choices=("auto", "strain", "displacement"),
            choice_labels={
                "auto": "자동 (압축계 변형률이 있으면 그것)",
                "strain": "압축계 · 신율계 변형률",
                "displacement": "크로스헤드 변위 ÷ 초기 높이",
            },
        ),
        ParamSpec(
            name="sign",
            label="부호",
            type="choice",
            default="auto",
            choices=("auto", "as_is", "flip"),
            choice_labels={
                "auto": "자동 (압축이 음수면 뒤집기)",
                "as_is": "그대로",
                "flip": "뒤집기",
            },
        ),
        ParamSpec(
            name="contact_force",
            label="접촉 문턱 하중",
            type="float",
            unit="N",
            help=(
                "이 하중을 처음 넘는 곳을 접촉점(변형 0)으로 봅니다. 비우면 최대 하중의 0.5%."
            ),
        ),
        ParamSpec(
            name="cycle",
            label="쓸 하중 구간(사이클)",
            type="int",
            default=0,
            help=(
                "0 이면 자동 — 구간이 하나면 그것, 여럿이면 마지막. 규격이 정하면 그 번호 "
                "(ISO 3386 은 4번째, ASTM D3574 C 는 3번째). -1 이면 전부 남깁니다 — 뒤에 "
                "반복 시험 단계(사이클 분리 등)를 둘 때."
            ),
        ),
        ParamSpec(
            name="force", label="하중 열", type="str", role="column", default=compress.FORCE
        ),
    ),
    makes_columns=(
        Produced(key=compress.STRAIN, label="압축 변형률", si_unit="1", help="압축량(양수)."),
        Produced(
            key=compress.STRESS,
            label="압축 응력",
            si_unit="Pa",
            help="하중 ÷ 초기 면적(양수).",
        ),
    ),
    makes_values=(Produced(key="loading_cycle_count", label="하중 구간 수", si_unit="1"),),
    order=10,
    version="1",
)(compress.engineering)

# **토우 보정은 인장의 것을 그대로 쓴다**(2026-10-20) — 열 이름만 압축의 것. 사용자 보고: 압축
# 처리에 토우 보정이 없다. 접촉점(`contact_force`)은 하중 문턱으로 0 을 잡고, 토우 보정은 처음
# 직선 구간을 응력 0 까지 늘여 원점을 다시 잡는다 — ASTM D695 · D1621 이 말하는 그것이다.
register(
    id="compression.toe_compensation",
    kind="processing",
    label="토우 보정",
    applies_to=("compression",),
    params=toe_params(compress.STRAIN, compress.STRESS),
    makes_values=TOE_VALUES,
    order=15,
    version="1",
)(toe_compensation_on(compress.STRAIN, compress.STRESS))

register(
    id="compression.modulus",
    kind="processing",
    label="압축 탄성률",
    applies_to=("compression",),
    params=(
        ParamSpec(
            name="method",
            label="방법",
            type="choice",
            default="secant",
            choices=tuple(_METHOD_LABELS),
            choice_labels=_METHOD_LABELS,
            choice_help=_METHOD_HELP,
            help=(
                "어느 방법이 옳은지는 규격이 정합니다. 기본은 고무 · 폼의 할선(10%) — "
                "플라스틱(ISO 604)은 현 · 0.0005 ~ 0.0025, D695 · 경질 폼은 접선."
            ),
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
            default=0.1,
            when={"method": ("chord", "regression", "secant")},
            help="할선이면 정한 변형률(고무 · 폼 10%), 현이면 0.0025(ISO 604).",
        ),
        ParamSpec(
            name="band_low",
            label="응력 띠 아래끝",
            type="float",
            unit="1",
            default=0.1,
            when={"method": ("stress_window",)},
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
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=compress.STRAIN,
        ),
        ParamSpec(
            name="stress", label="응력 열", type="str", role="column", default=compress.STRESS
        ),
    ),
    makes_values=(
        Produced(
            key="compressive_modulus",
            label="압축 탄성률",
            si_unit="Pa",
            property_key="mechanical.compressive_modulus",
        ),
        Produced(key="compressive_modulus_r2", label="압축 탄성률 회귀 R²", si_unit="1"),
    ),
    order=20,
    version="1",
)(compress.modulus)

register(
    id="compression.indices",
    kind="processing",
    label="압축 지표 (규격 보고값)",
    applies_to=("compression",),
    params=(
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=compress.STRAIN,
        ),
        ParamSpec(
            name="stress", label="응력 열", type="str", role="column", default=compress.STRESS
        ),
    ),
    makes_values=(
        *(
            Produced(key=key, label=label, si_unit="Pa")
            for key, _, label in compress.STRAIN_POINTS
        ),
        Produced(
            key="compressive_strength",
            label="압축 강도",
            si_unit="Pa",
            property_key="mechanical.compressive_strength",
        ),
        Produced(key="plateau_stress", label="평탄 응력(20~30% 평균)", si_unit="Pa"),
        Produced(key="densification_strain", label="치밀화 변형률", si_unit="1"),
        Produced(key="energy_absorption_50pct", label="흡수 에너지(0~50%)", si_unit="J/m3"),
    ),
    order=30,
    version="1",
)(compress.indices)


# **초탄성을 압축 데이터로**(2026-10-20) — 사용자 보고: 압축 시험을 초탄성 카드로 내보낼 경로가
# 없었다. 식은 인장의 것 그대로이고, 축만 이 확장이 만드는 압축 열(양수)이다. 카드에는 시험
# 모드 「단축 압축」 이 남고, 덱은 같은 식으로 옮긴다(`hyperelastic.compression`).
for _base in ("neo_hookean", "mooney_rivlin", "yeoh", "ogden_1"):
    _key = f"{_base}_compression"
    if _key not in fitting.FAMILIES:
        fitting.register_family(
            hyperelastic.compression(
                fitting.FAMILIES[_base], x_column=compress.STRAIN, y_column=compress.STRESS
            )
        )


# **폼 카드**(2026-10-20) — 사용자 보고: 폼 소재를 해석 카드로 내보낼 경로가 없었다. 시편
# 여럿의 공칭 압축 곡선을 공통 구간에 평균해 표로 싣는다(공칭 그대로 — 폼은 진응력 환산의
# 체적 보존 가정이 안 맞는다). 카드는 중심의 공용 길(`/fitting/cards/from-group`)이 만든다.
register(
    id="compression.foam",
    kind="grouping",
    label="폼 압축 곡선 (공칭 평균)",
    applies_to=("compression",),
    makes_values=(
        Produced(key="sample_count", label="시편 수", si_unit="1"),
        Produced(key="strain_max", label="공통 구간 끝 변형률", si_unit="1"),
        Produced(key="stress_at_max", label="끝의 압축 응력", si_unit="Pa"),
        Produced(
            key="initial_modulus",
            label="처음 기울기",
            si_unit="Pa",
            help="평균 곡선의 처음 구간을 원점을 지나는 직선으로 — 폼 카드의 E.",
        ),
    ),
    makes_columns=(
        Produced(key=compress.STRAIN, label="압축 변형률 (평균)", si_unit="1"),
        Produced(key=compress.STRESS, label="압축 응력 (평균)", si_unit="Pa"),
    ),
    # 채택된 결과의 압축 곡선 두 열 — 「압축 응력-변형률」 단계를 거친 결과다.
    members={"from": "adopted_result", "columns": [compress.STRAIN, compress.STRESS]},
    card=foam.card_blocks,
    order=40,
    version="1",
)(foam.foam_curve)
