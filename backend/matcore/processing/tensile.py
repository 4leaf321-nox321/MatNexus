"""인장 처리 — 변위·하중에서 물성이 쓸 수 있는 곡선까지.

**장비는 응력-변형률을 주지 않는다.** `Example.tra` 를 열어 확인한 것: Zwick 이
주는 것은 변위(mm)·하중(N)·시편폭(mm)이다. 공칭 변환도, 진응력 변환도, 탄성계수와
항복강도도 전부 여기서 만든다.

계산 자체는 65 의 `processing/domain/common_pipeline.py` 에서 가져왔다. 숫자를
그대로 옮긴 것이 아니라 **태도**를 옮겼다:

- 0.2% 오프셋 선이 관측 구간과 만나지 않으면 **외삽하지 않고 실패한다.**
- 네킹은 **후보만 제시하고 아무것도 자르지 않는다.**
- 탄성계수는 방법과 구간과 점 수와 R² 를 함께 남긴다.

이 태도가 이 도메인의 핵심이다. 틀린 항복강도는 그럴듯해 보이고, 그 값으로
적합한 소성 모델이 그대로 해석에 들어간다 — 나중에 찾아낼 방법이 없다.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore import ParamSpec, Produced, register
from matcore.processing import (
    Frame,
    ProcessingError,
    Scalar,
    StepResult,
    option_float,
    option_int,
    option_text,
    require_increasing,
)

#: 탄성계수를 낼 수 있는 최소 점 수. **이보다 적으면 값을 안 낸다.**
#:
#: 경고만 붙이고 값은 내던 때가 있었다. 그 값이 채택되면 통계·물성 카드·해석 덱까지
#: 그대로 흘러가고, 경고는 처리 화면에만 남아 아무도 다시 안 본다. 실측(2026-08-29):
#: 이관 데이터의 18점짜리 곡선에서 탄성계수 중앙값이 **1.83 GPa** 로 나왔다 —
#: 강판이면 200 GPa 다. 같은 코드가 2000점짜리 곡선에서는 200.2 GPa 를 낸다.
#:
#: 2점을 지나는 직선은 언제나 R²=1 이라 **R² 로는 이것을 못 막는다.** 점 수로 막는다.
MIN_TRUSTWORTHY_POINTS = 5

#: 그 구간이 직선이었다고 할 수 있는 최소 R². **이보다 낮으면 값을 안 낸다.**
#:
#: 점 수만으로는 절반만 막힌다 — 성긴 곡선에서 점을 채우려고 창을 [0, 0.05] 로
#: 넓히면 5점은 들어오지만 그 구간은 **항복 한참 뒤까지** 걸친다. 실측(2026-08-29):
#: 창 [0.001, 0.05] 로 E=1.83 GPa (R²=0.899), 창 [0, 0.05] 로 3.69 GPa (R²=0.473).
#: 같은 데이터의 조밀한 곡선은 좁은 창에서 201 GPa (R²=1.000) 를 낸다.
#:
#: 0.98 로 둔 이유: 관측된 좋은 적합은 0.993~1.000, 나쁜 것은 0.90 이하로 뚜렷이
#: 갈렸다. 진짜로 직선이 아닌 재료는 **「직접 입력」** 으로 빠져나간다.
MIN_TRUSTWORTHY_R_SQUARED = 0.98

#: 이 모듈이 만들어 내는 열 이름. 뒤 단계와 화면이 이 이름으로 찾는다.
STRAIN = "strain_engineering"
STRESS = "stress_engineering"
TRUE_STRAIN = "strain_true"
TRUE_STRESS = "stress_true"
PLASTIC_STRAIN = "strain_true_plastic"


def _pair(frame: Frame, options: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, str, str]:
    """변형률·응력 열 한 쌍. 기본은 이 모듈이 만든 공칭 열이다.

    이름을 옵션으로 여는 이유: 사람이 앞 단계에서 평활하거나 자른 열을 쓰고
    싶어 하고, 그때 **어느 열로 계산했는지가 근거에 남아야** 한다.
    """
    strain_key = str(options.get("strain") or STRAIN)
    stress_key = str(options.get("stress") or STRESS)
    strain = frame.require(strain_key, what="변형률")
    stress = frame.require(stress_key, what="응력")
    _require_dimensionless_strain(frame, strain_key)
    _require_pascal_stress(frame, stress_key)
    return strain, stress, strain_key, stress_key


def _require_dimensionless_strain(frame: Frame, key: str) -> None:
    unit = frame.units.get(key)
    if unit not in (None, "1"):
        raise ProcessingError(
            f"'{key}' 는 무차원 변형률이어야 하는데 단위가 '{unit}' 입니다. "
            f"% 로 들어왔다면 100 으로 나눠 SI 로 만든 뒤 넣으세요."
        )


def _require_pascal_stress(frame: Frame, key: str) -> None:
    unit = frame.units.get(key)
    if unit not in (None, "Pa"):
        raise ProcessingError(
            f"'{key}' 는 Pa 여야 하는데 단위가 '{unit}' 입니다. "
            f"저장 단위는 고를 수 있는 것이 아닙니다 — 값은 언제나 정본 SI 입니다."
        )


@register(
    id="tensile.engineering",
    kind="processing",
    label="공칭 응력-변형률",
    params=(
        ParamSpec(
            name="gauge_length",
            label="게이지 길이",
            type="float",
            unit="m",
            required=True,
            help="시편 정의에서 옵니다. 변위를 이 길이로 나눠 변형률을 만듭니다.",
        ),
        ParamSpec(
            name="area",
            label="초기 단면적",
            type="float",
            unit="m2",
            required=True,
            help="폭 곱하기 두께. 하중을 이 넓이로 나눠 응력을 만듭니다.",
        ),
        ParamSpec(
            name="displacement",
            label="변위 열",
            type="str",
            role="column",
            default="displacement",
        ),
        ParamSpec(name="force", label="하중 열", type="str", role="column", default="force"),
    ),
    applies_to=("tensile",),
    # **여기가 없으면 뒤가 전부 없다.** 장비는 응력-변형률을 주지 않는다.
    makes_columns=(
        Produced(
            key=STRAIN,
            label="공칭 변형률",
            si_unit="1",
            help="변위 ÷ 게이지 길이. 시편이 처음 길이에 견줘 얼마나 늘었는가.",
        ),
        Produced(
            key=STRESS,
            label="공칭 응력",
            si_unit="Pa",
            help=(
                "하중 ÷ 초기 단면적. **줄어드는 단면을 안 본다** — "
                "그래서 네킹 뒤 값이 실제보다 낮게 나옵니다."
            ),
        ),
    ),
    order=10,
    version="1",
)
def engineering(frame: Frame, options: dict[str, Any]) -> StepResult:
    """변위·하중 → 공칭 변형률·응력.

    **치수는 곡선에 없다.** 게이지 길이와 단면적은 시편 기록에서 와야 하고,
    이 함수는 그것을 받아 쓰기만 한다(`matcore` 는 DB 를 모른다). 그래서 값을
    근거에 그대로 남긴다 — 반년 뒤 "이 응력이 왜 이렇지" 는 대개 면적 문제다.
    """
    gauge = option_float(options, "gauge_length")
    area = option_float(options, "area")
    if gauge <= 0:
        raise ProcessingError(f"게이지 길이가 0 이하입니다: {gauge} m")
    if area <= 0:
        raise ProcessingError(f"단면적이 0 이하입니다: {area} m²")

    displacement_key = str(options.get("displacement") or "displacement")
    force_key = str(options.get("force") or "force")
    displacement = frame.require(displacement_key, what="변위")
    force = frame.require(force_key, what="하중")

    for key, expected in ((displacement_key, "m"), (force_key, "N")):
        unit = frame.units.get(key)
        if unit not in (None, expected):
            raise ProcessingError(f"'{key}' 는 {expected} 여야 하는데 '{unit}' 입니다.")

    return StepResult(
        frame.with_columns(
            {STRAIN: displacement / gauge, STRESS: force / area},
            {STRAIN: "1", STRESS: "Pa"},
        ),
        notes=(
            f"게이지 길이 {gauge * 1e3:.4g} mm, 초기 단면적 {area * 1e6:.4g} mm² 로 "
            f"'{displacement_key}'·'{force_key}' 를 공칭으로 바꿨습니다.",
        ),
    )


#: 토우 보정에 필요한 최소 점 수. 직선을 얹는 일이라 적으면 아무 말도 못 한다.
TOE_MIN_POINTS = 5

#: 이보다 낮으면 그 구간은 직선이 아니다. **경고이지 실패가 아니다** — 재료에
#: 따라 진짜로 직선이 아닐 수 있고, 그 판단은 사람이 한다.
TOE_MIN_R_SQUARED = 0.995


@register(
    id="tensile.toe_compensation",
    kind="processing",
    label="토우 보정",
    params=(
        ParamSpec(
            name="minimum_strain",
            dimension="strain",
            label="구간 시작",
            type="float",
            default=0.001,
            unit="1",
            help="토우가 끝난 뒤의 직선 구간을 잡습니다. 곡선을 보고 정하세요.",
        ),
        ParamSpec(
            name="maximum_strain",
            dimension="strain",
            label="구간 끝",
            type="float",
            default=0.004,
            unit="1",
            help="**공칭 변형률**입니다. 토우가 끝난 뒤의 직선 구간을 잡습니다.",
        ),
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    # 열을 새로 만들지 않는다 — **고른 변형률 열을 그 자리에서 민다.**
    makes_values=(
        Produced(
            key="toe_strain_offset",
            label="토우 보정량",
            si_unit="1",
            help=(
                "변형률 축을 왼쪽으로 민 양. "
                "물린 시편이 자리를 잡는 동안 생긴 가짜 변형입니다."
            ),
        ),
        Produced(
            key="toe_r_squared",
            label="토우 구간 R²",
            si_unit="1",
            help=(
                "보정에 쓴 직선이 그 구간에 얼마나 맞는가. 낮으면 구간을 잘못 잡은 것입니다."
            ),
        ),
    ),
    order=30,
    version="1",
)
def toe_compensation(frame: Frame, options: dict[str, Any]) -> StepResult:
    """초기 토우 구간만큼 변형률 원점을 옮긴다. **응력은 안 건드린다.**

    시험 처음에 시편이 그립에 물려 자리를 잡는 동안 하중은 거의 안 오르는데 변위는
    늘어난다. 곡선 앞머리가 눕는 그 구간을 토우라고 한다. 장비가 준 변형률의 0 은
    **시편이 실제로 늘어나기 시작한 지점이 아니다.**

    ## 안 고치면 탄성계수가 반토막 난다

    `tensile.elastic_modulus` 는 명시한 변형률 창에서 기울기를 잰다. 토우가 원점을
    밀어 놓으면 **그 창이 토우 안에 걸린다** — 하중이 안 오르는 구간이 섞여 들어가
    기울기가 낮게 나온다. 합성 곡선으로 재 보니 200 GPa 가 100 GPa 로 나왔다
    (`tests/unit/test_processing_kernel.py`). 두 배 틀렸는데 100 GPa 는 그럴듯해
    보인다 — 알루미늄이라고 하면 넘어갈 숫자다.

    그 탄성계수는 물성 카드에 그대로 들어가고, 경화식 적합의 탄성 분리에도 쓰인다.

    오프셋 항복강도도 틀린 원점에서 출발한 직선으로 구해진다. **다만 그 영향은
    경화 기울기에 달렸다** — 위 합성 곡선(선형 경화 2 GPa)에서는 0.3% 였다. 경화가
    가파른 재료일수록 커진다. 재 보지 않고 "항복강도가 크게 틀린다" 고 말하지
    않는다.

    ## 무엇을 하고 무엇을 안 하나

    명시한 구간에 최소제곱 직선을 얹고, 그 직선이 응력 0 을 만나는 변형률만큼
    전체를 왼쪽으로 민다. 그게 전부다.

    * **구간을 자동으로 찾지 않는다.** 어디까지가 토우인지는 곡선을 본 사람이
      정한다. 자동 탐지는 그럴듯한 답을 내는데, 틀렸다는 것을 알 방법이 없다
    * **응력을 안 건드린다.** 장비 컴플라이언스(장비 자체가 늘어난 몫)를 빼려면
      장비 강성을 알아야 하는데 그 값은 시험 파일에 없다. 추정하지 않는다 —
      그래서 그 칸을 아예 두지 않았다. 고를 것이 하나뿐인 칸은 아무 일도 안 하면서
      뭔가 하는 것처럼 보인다
    * **자르지 않는다.** 보정 뒤 앞쪽 몇 점은 음의 변형률이 된다(시편이 물리기
      전이다). 지우려면 `curve.crop` 을 뒤에 둔다. 한 단계가 두 가지 일을 하면
      무엇 때문에 값이 바뀌었는지 못 가린다
    * **보정량을 결과에 남긴다.** 눌러 넘기는 확인 칸 대신 숫자를 남긴다. 반년 뒤
      "이 항복강도가 왜 이렇지" 에 답하는 것은 체크박스가 아니라 값이다

    ## 열을 덮어쓴다 — `curve.smooth` 와 다른 점

    평활은 `_smoothed` 열을 새로 만들지만 여기서는 원래 열을 덮어쓴다. 새 열로
    만들면 뒤 단계들이 기본값(`strain_engineering`)을 그대로 집어서 **보정 안 된
    변형률로 계산한다.** 사람이 단계마다 열 이름을 다시 지정해야 하고, 한 번
    빠뜨리면 보정을 넣었는데 아무 일도 안 일어난다 — 이 도메인에서 가장 나쁜
    실패다. 전/후 비교는 파이프라인이 단계마다의 `Frame` 을 들고 있어서 그대로 된다.
    """
    strain, stress, strain_key, _stress_key = _pair(frame, options)
    require_increasing(strain, what=f"'{strain_key}'")

    low = option_float(options, "minimum_strain", 0.001)
    high = option_float(options, "maximum_strain", 0.004)
    if low >= high:
        raise ProcessingError(f"구간 시작({low})이 끝({high}) 이상입니다.")

    mask = (strain >= low) & (strain <= high)
    count = int(np.sum(mask))
    if count < TOE_MIN_POINTS:
        raise ProcessingError(
            f"변형률 [{low:.6g}, {high:.6g}] 안에 {count}점만 있습니다 — 토우 보정은 "
            f"최소 {TOE_MIN_POINTS}점이 필요합니다. 관측 범위는 "
            f"[{float(strain.min()):.6g}, {float(strain.max()):.6g}] 입니다."
        )

    selected_x, selected_y = strain[mask], stress[mask]
    slope, intercept = _fit_line(selected_x, selected_y, what="구간의 기울기")

    # 직선이 응력 0 을 만나는 변형률. 토우가 있으면 양수이고, 그만큼 왼쪽으로 민다.
    offset = -intercept / slope
    if not math.isfinite(offset):
        raise ProcessingError("보정량이 유한하지 않습니다. 구간을 다시 잡으세요.")
    r_squared = _r_squared(selected_x, selected_y, slope, intercept)

    scalars = [
        Scalar("toe_strain_offset", "토우 보정량", float(offset), "1", dimension="strain"),
        Scalar("toe_r_squared", "토우 구간 R²", float(r_squared), "1"),
    ]
    notes = [
        f"변형률 [{low:.6g}, {high:.6g}] 구간의 {count}점에 얹은 직선이 응력 0 을 "
        f"만나는 지점({offset:.6g})만큼 '{strain_key}' 를 옮겼습니다 "
        f"(기울기 {slope / 1e9:.4g} GPa, R²={r_squared:.5f}). 응력은 그대로입니다."
    ]
    if r_squared < TOE_MIN_R_SQUARED:
        notes.append(
            f"R² 가 {r_squared:.4f} 로 낮습니다 — 잡은 구간이 직선이 아닙니다. "
            f"토우가 아직 안 끝났거나 항복 뒤까지 걸쳐 있는지 확인하세요."
        )
    if abs(offset) > (high - low):
        # 보정량이 그것을 잰 구간보다 크면 외삽 거리가 근거보다 길다는 뜻이다.
        notes.append(
            f"보정량({offset:.6g})이 구간 폭({high - low:.6g})보다 큽니다 — "
            f"직선을 근거보다 멀리 늘여 원점을 잡았습니다. 구간을 다시 보세요."
        )
    if offset < 0:
        notes.append(
            f"보정량이 음수({offset:.6g})입니다 — 원점을 오른쪽으로 옮깁니다. "
            f"토우 보정이 기대하는 방향이 아니니 구간이 맞는지 확인하세요."
        )
    return StepResult(
        frame.with_columns({strain_key: strain - offset}, {strain_key: "1"}),
        notes=tuple(notes),
        scalars=tuple(scalars),
    )


#: `auto` 가 볼 응력 띠 — **그 곡선 자신의 최대응력에 대한 비율.**
#:
#: 변형률 절대값으로 고정하면 곡선마다 토우 길이와 항복 시점이 달라 맞지 않는다.
#: 응력 비율은 그 곡선을 따라간다: 아래끝이 토우를 지나고, 위끝이 항복 앞에서
#: 끊는다. 규격도 같은 방식으로 구간을 정한다(ISO 6892-1 은 응력 범위로 규정).
#:
#: 10~40% 인 이유: 강의 항복은 보통 인장강도의 60~70% 라 40% 는 안전하게 아래다.
#:
#: **항복이 낮은 재료에서는 이 기본값이 안 맞는다.** 항복이 인장강도의 29% 인
#: 곡선에서 재 보면(2026-08-31) 띠 전체가 항복 뒤에 놓여 **2.2 GPa** 가 나온다 —
#: 참값은 200 GPa 다. 다만 그 구간은 직선이 아니라 R²=0.72 이고, **거절 검사가
#: 잡아 값을 안 낸다.** 조용히 틀린 값이 나가지는 않는다.
#:
#: 그래서 띠를 **사람이 조절할 수 있게** 열어 둔다. 같은 곡선을 5~20% 로 재면
#: 200 GPa 가 정확히 나온다. 어느 띠가 옳은지는 재료와 규격이 정하는 것이라,
#: 여기서 재료를 알아맞히려 하지 않는다.
_AUTO_STRESS_LOW = 0.10
_AUTO_STRESS_HIGH = 0.40


def _auto_window(
    strain: Any,
    stress: Any,
    low_fraction: float = _AUTO_STRESS_LOW,
    high_fraction: float = _AUTO_STRESS_HIGH,
) -> tuple[tuple[float, float] | None, int, int]:
    """탄성 구간을 **응력 띠**로 잡는다. 점이 모자라면 `None`.

    ## 창을 훑지 않는 이유

    처음에는 「R² 기준을 만족하는 가장 긴 창」 으로 짰다가 합성 곡선에서 걸렸다
    (2026-08-31): **소성 구역이 뽑혀 2.25 GPa** 가 나왔다. R² 는 전체 분산 대비
    잔차라, 넓은 구간에서는 완만히 굽은 곡선도 0.98 을 넘는다 — 길이는 직선다움의
    척도가 아니다.

    그래서 「가장 가파른 창」 으로 바꿨더니 이번엔 **잡음이 이겼다.** 짧은 창은
    얼마든지 가팔라질 수 있어서, 400점 직선(200 GPa)에서 11점짜리 223 GPa 가
    뽑혔다. 탄성 구간이 성긴 곡선에서는 **소성 구역을 확신에 차서** 골랐다.

    두 번 다 같은 함정이었다: **창을 자유롭게 고르게 두면 이상한 창이 이긴다.**

    ## 응력 띠는 곡선을 따라간다

    아래끝이 토우를 지나고 위끝이 항복 앞에서 끊는다. 고를 자유가 없으므로
    이상한 창이 이길 수 없고, 띠 안이 직선이 아니면 **아래의 R² 검사가 거절한다** —
    이 함수가 판정까지 하지 않는다.

    ## 못 잡았을 때도 수를 돌려준다

    `(구간, 띠 안의 점 수, 상승 구간 점 수)` 를 낸다. 구간이 `None` 이어도 나머지
    둘은 뜻이 있다 — **왜 못 잡았는지가 그 수에 있다.** 「2점밖에 없었다」 와
    「띠가 항복 뒤였다」 는 고칠 데가 다르고, 수가 없으면 사람이 곡선을 직접
    열어 보는 수밖에 없다(실측 2026-08-31: 18점 발췌본에서 그 일을 했다).
    """
    peak = int(np.argmax(stress))
    x = np.asarray(strain[: peak + 1], dtype=float)
    y = np.asarray(stress[: peak + 1], dtype=float)
    rising = int(y.size)
    top = float(y.max()) if y.size else 0.0
    if not math.isfinite(top) or top <= 0:
        return None, 0, rising

    inside = (y >= low_fraction * top) & (y <= high_fraction * top)
    count = int(np.sum(inside))
    if count < MIN_TRUSTWORTHY_POINTS:
        # **여기서 값을 지어내지 않는다.** 띠 안에 점이 모자라다는 것은 곡선이
        # 성기다는 뜻이고, 그때 다른 구간을 고르면 소성 구역이 뽑힌다.
        return None, count, rising
    return (float(x[inside].min()), float(x[inside].max())), count, rising


@register(
    id="tensile.elastic_modulus",
    kind="processing",
    label="탄성계수",
    params=(
        ParamSpec(
            name="method",
            label="방법",
            type="choice",
            default="linear_regression",
            choices=("linear_regression", "chord", "secant", "auto", "manual"),
            choice_labels={
                "linear_regression": "최소제곱 회귀",
                "chord": "현 (구간 양 끝 두 점)",
                "secant": "할선 (원점에서 구간 끝)",
                "auto": "자동 (응력 띠)",
                "manual": "직접 입력",
            },
            help=(
                "같은 곡선에서도 방법마다 몇 % 다릅니다. 어느 쪽이 옳은지는 규격이 "
                "정합니다 — **규격이 구간을 지정하면 자동을 쓰지 마세요.**"
            ),
        ),
        ParamSpec(
            name="minimum_strain",
            dimension="strain",
            label="구간 시작",
            type="float",
            default=0.0005,
            unit="1",
            when={"method": ("linear_regression", "chord", "secant")},
            help=(
                "**공칭 변형률**입니다. 기본 0.05~0.25% 는 금속 판재의 관례이고 "
                "곡선마다 맞지 않습니다 — 그 구간에 점이 없으면 값이 안 나옵니다. "
                "구간을 모르겠으면 방법을 「자동」 으로 두세요."
            ),
        ),
        ParamSpec(
            name="maximum_strain",
            dimension="strain",
            label="구간 끝",
            type="float",
            default=0.0025,
            unit="1",
            when={"method": ("linear_regression", "chord", "secant")},
            help="**공칭 변형률**입니다. 항복 전이어야 합니다 — 넘으면 기울기가 눕습니다.",
        ),
        ParamSpec(
            name="auto_stress_low",
            label="자동 띠 아래끝",
            type="float",
            default=_AUTO_STRESS_LOW,
            unit="1",
            when={"method": ("auto",)},
            help=(
                "최대응력에 대한 비율. 토우를 지나야 하므로 0 이 아닙니다. "
                "**항복이 낮은 재료면 위아래를 함께 낮추세요** — "
                "5~20% 로 재는 경우가 있습니다."
            ),
        ),
        ParamSpec(
            name="auto_stress_high",
            label="자동 띠 위끝",
            type="float",
            default=_AUTO_STRESS_HIGH,
            unit="1",
            when={"method": ("auto",)},
            help=(
                "항복 앞에서 끊어야 합니다. "
                "항복이 인장강도의 60~70% 인 강은 40% 가 안전합니다."
            ),
        ),
        ParamSpec(
            name="manual_modulus",
            label="직접 입력",
            type="float",
            unit="Pa",
            required=True,
            when={"method": ("manual",)},
        ),
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    makes_values=(
        Produced(
            key="youngs_modulus",
            label="탄성계수",
            si_unit="Pa",
            help="탄성 구간의 기울기(E). 항복강도·진소성변형률이 이 값을 씁니다.",
        ),
        Produced(
            key="elastic_intercept",
            label="탄성 절편",
            si_unit="Pa",
            help=(
                "맞춘 직선이 변형률 0 에서 갖는 값. "
                "0 에서 크게 벗어나면 토우가 남아 있다는 뜻입니다."
            ),
        ),
        Produced(
            key="elastic_r_squared",
            label="탄성 구간 R²",
            si_unit="1",
            help=(
                "그 구간이 실제로 직선이었는가. **0.98 미만이면 탄성계수를 내지 "
                "않습니다** — 직선이 아닌 구간의 기울기는 탄성계수가 아닙니다."
            ),
        ),
        Produced(
            key="elastic_point_count",
            label="탄성 구간 점 수",
            si_unit="1",
            help=(
                "그 구간에 실제로 있던 점의 수. **5개 미만이면 탄성계수를 내지 "
                "않습니다** — 값이 왜 없는지 이 수가 말합니다."
            ),
        ),
        Produced(
            key="elastic_window_start",
            label="탄성 구간 시작",
            si_unit="1",
            help=(
                "실제로 쓴 구간의 시작 변형률. **자동으로 고른 값은 무엇을 골랐는지 "
                "보여야** 사람이 검토할 수 있습니다."
            ),
        ),
        Produced(
            key="elastic_window_end",
            label="탄성 구간 끝",
            si_unit="1",
            help="실제로 쓴 구간의 끝 변형률.",
        ),
    ),
    order=50,
    version="1",
)
def elastic_modulus(frame: Frame, options: dict[str, Any]) -> StepResult:
    """지정 구간에서 탄성계수를 잰다. 곡선은 안 바뀐다.

    **방법을 고르게 두는 이유:** 같은 곡선에서도 회귀와 현이 몇 % 다르고, 어느
    쪽이 옳은지는 규격과 재료가 정한다. 하나로 박아 두면 규격이 다른 부서가 쓸
    수 없고, 그렇다고 조용히 바꾸면 예전 값과 비교가 안 된다. **무엇으로 쟀는지가
    값과 함께 남아야** 비교가 성립한다.

    R² 를 함께 낸다. 구간을 잘못 잡으면(항복 뒤까지 포함) 값 자체는 나오는데
    직선이 아니다 — 그 사실이 R² 에만 보인다.
    """
    strain, stress, strain_key, _ = _pair(frame, options)
    require_increasing(strain, what=f"'{strain_key}'")

    method = option_text(
        options, "method", ("linear_regression", "chord", "secant", "auto", "manual")
    )
    low = option_float(options, "minimum_strain", 0.0005)
    high = option_float(options, "maximum_strain", 0.0025)

    auto_note: str | None = None
    if method == "auto":
        band_low = option_float(options, "auto_stress_low", _AUTO_STRESS_LOW)
        band_high = option_float(options, "auto_stress_high", _AUTO_STRESS_HIGH)
        if not 0 < band_low < band_high <= 1:
            raise ProcessingError(
                f"자동 띠가 0 < 아래끝({band_low}) < 위끝({band_high}) ≤ 1 이어야 합니다."
            )
        found, in_band, rising = _auto_window(strain, stress, band_low, band_high)
        if found is None:
            # **값을 안 낸다.** 지어낸 구간으로 낸 값은 그럴듯해 보이고, 그대로
            # 카드와 덱까지 간다. 고정 구간의 거절과 같은 자리다.
            # **왜 없는지를 값으로도 남긴다.** 고정 구간 쪽이 그렇게 하고 있고
            # (「값이 없다」 만으로는 고칠 데를 모른다), 자동만 안 남기면 사람이
            # 곡선을 직접 열어 점을 세게 된다 — 실측 2026-08-31 에 그 일을 했다.
            return StepResult(
                frame,
                notes=(
                    f"최대응력의 {band_low:.0%}~{band_high:.0%} 띠 안에 {in_band}점밖에 "
                    f"없어 **탄성계수를 내지 않았습니다**(상승 구간 전체가 {rising}점). "
                    f"{MIN_TRUSTWORTHY_POINTS}점은 있어야 합니다 — {in_band}점을 지나는 "
                    "직선은 거의 언제나 R²≈1 이라 맞았는지 알 수 없습니다. "
                    "**곡선이 성깁니다** — 더 조밀한 원본을 쓰거나, 구간을 아는 경우 "
                    "방법을 「최소제곱 회귀」 로 바꿔 직접 지정하세요.",
                ),
                scalars=(
                    Scalar("elastic_point_count", "탄성 구간 점 수", float(in_band), "1"),
                ),
            )
        low, high = found
        auto_note = (
            f"최대응력의 {band_low:.0%}~{band_high:.0%} 띠로 잡은 구간: "
            f"변형률 [{low:.6g}, {high:.6g}]. "
            "**규격이 구간을 정하는 경우에는 이 방법을 쓰지 마세요.**"
        )
        method = "linear_regression"
    elif low >= high:
        raise ProcessingError(f"구간 시작({low})이 끝({high}) 이상입니다.")

    intercept = 0.0
    if method == "manual":
        modulus = option_float(options, "manual_modulus")
        count = 0
        r_squared = float("nan")
    else:
        mask = (strain >= low) & (strain <= high)
        count = int(np.sum(mask))
        if count < 2:
            raise ProcessingError(
                f"변형률 [{low:.6g}, {high:.6g}] 안에 {count}점만 있습니다. "
                f"관측 범위는 [{float(strain.min()):.6g}, {float(strain.max()):.6g}] 입니다."
            )
        selected_x, selected_y = strain[mask], stress[mask]
        if method == "linear_regression":
            modulus, intercept = _fit_line(selected_x, selected_y, what="탄성계수")
        elif method == "chord":
            start_stress = float(np.interp(low, strain, stress))
            end_stress = float(np.interp(high, strain, stress))
            modulus = (end_stress - start_stress) / (high - low)
            intercept = start_stress - modulus * low
        else:  # secant — 원점에서 끝점까지
            if high <= 0:
                raise ProcessingError("할선 탄성계수는 구간 끝이 양수여야 합니다.")
            modulus = float(np.interp(high, strain, stress)) / high
        r_squared = _r_squared(selected_x, selected_y, modulus, intercept)

    if not math.isfinite(modulus) or modulus <= 0:
        raise ProcessingError(
            f"탄성계수가 유한한 양수가 아닙니다: {modulus}. "
            f"구간이 항복 뒤에 걸쳐 있거나 응력 부호가 뒤집혔을 수 있습니다."
        )

    # **점이 모자라면 값을 안 낸다.** 경고만 붙이고 값은 내던 때가 있었다 — 그러면
    # 그 값이 채택돼 통계·카드·해석 덱까지 흘러가고, 경고는 처리 화면에만 남는다.
    #
    # 2점을 지나는 직선은 언제나 R²=1 이라 **R² 로는 못 막는다.** 점 수로 막는다.
    # 실측(2026-08-29): 18점 곡선에서 1.83 GPa, 같은 코드가 2000점에서 200.2 GPa.
    #
    # 단계는 실패시키지 않는다 — 인장강도·연신율은 멀쩡히 나온 것이고, 그것까지
    # 잃으면 사람이 「점이 모자란 것」 을 고치는 대신 이 단계를 빼 버린다.
    if method != "manual":
        window = f"변형률 [{low:.6g}, {high:.6g}] 구간"
        observed = (
            f"관측 범위는 [{float(strain.min()):.6g}, {float(strain.max()):.6g}] 입니다."
        )
        # **자동이면 고칠 데가 다르다.** 「창을 좁히세요」 는 구간을 손으로 지정한
        # 사람에게 하는 말이고, 자동을 쓴 사람에게는 띠가 손잡이다.
        advice = (
            "자동이라면 **띠를 낮춰 보세요** — 항복이 인장강도의 절반 아래인 재료는 "
            "기본 띠(10~40%)가 항복 뒤에 놓입니다. "
            if auto_note is not None
            else ""
        )
        refused = None
        if count < MIN_TRUSTWORTHY_POINTS:
            refused = (
                f"{window}에 {count}점밖에 없어 **탄성계수를 내지 않았습니다.** "
                f"{MIN_TRUSTWORTHY_POINTS}점은 있어야 합니다 — {count}점을 지나는 직선은 "
                f"거의 언제나 R²≈1 이라 맞았는지 알 수 없습니다. 구간을 넓히거나, 더 "
                f"조밀한 곡선을 쓰거나, 값을 아는 경우 방법을 「직접 입력」 으로 바꾸세요. "
                f"{observed}"
            )
        elif math.isfinite(r_squared) and r_squared < MIN_TRUSTWORTHY_R_SQUARED:
            # **점을 채우려고 창을 넓힌 경우가 여기 걸린다.** 5점은 들어왔는데 그
            # 구간이 항복 뒤까지 걸쳐 직선이 아니다 — 기울기는 나오지만 그것은
            # 탄성계수가 아니다.
            refused = (
                f"{window}의 {count}점이 직선이 아닙니다(R²={r_squared:.4f}) — "
                f"**탄성계수를 내지 않았습니다.** 기울기 {modulus / 1e9:.4g} GPa 는 나왔지만 "
                f"그 구간이 직선이 아니면 그것은 탄성계수가 아닙니다. 구간이 항복 뒤까지 "
                f"걸쳤거나 초기 토우가 섞였는지 보고 창을 좁히세요. 값을 아는 경우 방법을 "
                f"「직접 입력」 으로 바꾸세요. {advice}{observed}"
            )
        if refused is not None:
            # **인장강도·연신율은 멀쩡히 나온 것이다.** 단계를 실패시키면 사람이
            # 원인을 고치는 대신 이 단계를 빼 버린다.
            #
            # 남기는 것은 **거절의 근거**뿐이다. 점이 모자라 거절했으면 R² 는 안
            # 남긴다 — 2점의 R²=1 이 화면에 뜨면 「완벽한데 왜 값이 없지」 가 된다.
            scalars = [Scalar("elastic_point_count", "탄성 구간 점 수", float(count), "1")]
            if count >= MIN_TRUSTWORTHY_POINTS and math.isfinite(r_squared):
                scalars.append(
                    Scalar("elastic_r_squared", "탄성 구간 R²", float(r_squared), "1")
                )
            return StepResult(frame, notes=(refused,), scalars=tuple(scalars))

    scalars = [
        Scalar("youngs_modulus", "탄성계수", float(modulus), "Pa"),
        Scalar("elastic_intercept", "탄성 절편", float(intercept), "Pa"),
    ]
    if method != "manual":
        # **실제로 쓴 구간을 남긴다.** 자동이면 사람이 안 고른 값이고, 손으로
        # 지정했어도 나중에 「무엇으로 쟀나」 에 답해야 한다.
        scalars.append(Scalar("elastic_window_start", "탄성 구간 시작", float(low), "1"))
        scalars.append(Scalar("elastic_window_end", "탄성 구간 끝", float(high), "1"))
    if math.isfinite(r_squared):
        scalars.append(Scalar("elastic_r_squared", "탄성 구간 R²", float(r_squared), "1"))
    if method != "manual":
        scalars.append(Scalar("elastic_point_count", "탄성 구간 점 수", float(count), "1"))

    note = (
        f"직접 입력한 탄성계수 {modulus / 1e9:.4g} GPa"
        if method == "manual"
        else (
            f"{method} 로 변형률 [{low:.6g}, {high:.6g}] 구간의 {count}점에서 "
            f"{modulus / 1e9:.4g} GPa (R²={r_squared:.5f})"
        )
    )
    if auto_note is not None:
        # **사람이 안 고른 구간이다.** 무엇을 골랐는지 메모에 남지 않으면
        # 검토할 근거가 없다.
        note = f"{auto_note} {note}"
    notes = [note]
    if math.isfinite(r_squared) and r_squared < 0.995:
        # **경고이지 실패가 아니다.** 0.98 미만은 위에서 이미 막았다 — 여기는 그
        # 문턱을 넘었지만 완전하지는 않은 자리로, 토우가 조금 섞였을 때 걸린다.
        notes.append(
            f"R² 가 {r_squared:.4f} 입니다 — 초기 토우(시편 물림)가 조금 섞였는지 "
            f"확인하세요. 토우 보정 단계를 앞에 두면 좋아집니다."
        )
    return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))


def _fit_line(x: np.ndarray, y: np.ndarray, *, what: str) -> tuple[float, float]:
    """구간에 직선을 얹는다. **퇴화한 구간은 숫자를 내기 전에 막는다.**

    `polyfit` 은 거의 한 점인 구간이나 상수 응력에 대해서도 숫자를 돌려준다 —
    유한하고 양수인 기울기가 나오므로 뒤따르는 `isfinite`·`> 0` 검사를 빠져나가고,
    그 값이 그대로 탄성계수가 되거나 원점을 옮긴다. **조용히 틀리는 자리다.**

    절대값으로 못 막는다: 고무는 MPa 이고 금속은 GPa 라 "이보다 작으면 이상하다"
    는 기준이 재료마다 다르다. **부동소수의 eps 에 데이터 크기를 곱해** 그 재료
    기준의 바닥을 만든다.

    토우 보정에만 있던 방어다. 탄성계수 회귀는 `count < 2` 만 보고 있었는데,
    **같은 함수를 같은 방식으로 쓰면서 한쪽만 막아 둔 것**이라 옮겨 왔다. 탄성계수는
    처리 경로에서 가장 많이 불리고, 그 값은 카드를 거쳐 솔버 덱까지 간다.
    """
    count = int(x.size)
    span = float(x[-1] - x[0])
    centered = x - float(np.mean(x))
    spread = float(np.dot(centered, centered))
    x_scale = max(float(np.max(np.abs(x))), span)
    floor = (
        np.finfo(np.float64).eps * count * max(x_scale * x_scale, np.finfo(np.float64).tiny)
    )
    if span <= 0 or spread <= floor:
        raise ProcessingError(
            f"구간의 변형률이 사실상 한 점입니다(폭 {span:.3g}). 직선을 얹을 수 "
            f"없습니다 — 구간을 넓히세요."
        )

    slope, intercept = (float(value) for value in np.polyfit(x, y, 1))
    y_scale = max(float(np.max(np.abs(y))), 1.0)
    slope_floor = np.finfo(np.float64).eps * count * y_scale / span
    if not math.isfinite(slope) or slope <= slope_floor:
        raise ProcessingError(
            f"{what}가 유한한 양수가 아닙니다: {slope:.6g}. "
            f"구간이 항복 뒤에 걸쳐 있거나 응력 부호가 뒤집혔을 수 있습니다."
        )
    return slope, intercept


def _r_squared(x: np.ndarray, y: np.ndarray, slope: float, intercept: float) -> float:
    predicted = slope * x + intercept
    total = float(np.sum((y - np.mean(y)) ** 2))
    residual = float(np.sum((y - predicted) ** 2))
    if total == 0:
        return 1.0 if residual == 0 else 0.0
    return 1.0 - residual / total


@register(
    id="tensile.proof_stress",
    kind="processing",
    label="오프셋 항복강도",
    params=(
        ParamSpec(
            name="offset_strain",
            dimension="strain",
            label="오프셋",
            type="float",
            default=0.002,
            unit="1",
            help="규격이 정합니다. 금속은 보통 0.2%.",
        ),
        ParamSpec(
            name="youngs_modulus",
            label="탄성계수",
            type="float",
            unit="Pa",
            required=True,
            help="앞 단계에서 잰 값을 그대로 쓰거나, 직접 넣습니다.",
        ),
        ParamSpec(
            name="search_start",
            dimension="strain",
            label="탐색 시작",
            type="float",
            unit="1",
            help="**공칭 변형률**입니다. 오프셋 직선과 곡선의 교점을 이 구간에서 찾습니다.",
        ),
        ParamSpec(
            name="search_end",
            dimension="strain",
            label="탐색 끝",
            type="float",
            unit="1",
            help="**공칭 변형률**입니다. 비우면 관측 끝까지 봅니다.",
        ),
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    makes_values=(
        Produced(
            key="proof_stress",
            label="항복강도",
            si_unit="Pa",
            help=(
                "오프셋 선과 곡선이 만나는 점의 응력. "
                "**만나지 않으면 외삽하지 않고 실패합니다.**"
            ),
        ),
        Produced(
            key="proof_strain", label="항복 변형률", si_unit="1", help="그 교점의 변형률."
        ),
        Produced(
            key="proof_offset",
            label="오프셋",
            si_unit="1",
            help="쓴 오프셋 값. 금속은 보통 0.2% 이고 규격이 정합니다.",
        ),
    ),
    order=60,
    version="1",
)
def proof_stress(frame: Frame, options: dict[str, Any]) -> StepResult:
    """오프셋 선과 곡선의 **관측된 교점**을 찾는다.

    **없으면 만들어 내지 않는다.** 오프셋 선이 탐색 구간 안에서 곡선을 가로지르지
    않으면 실패한다. 65 에서 이 태도를 가져온 이유: 외삽으로 만든 항복강도는
    그럴듯한 숫자로 나와서 아무도 의심하지 않고, 그 값으로 적합한 소성 곡선이
    해석에 들어간다. 실패는 시끄럽고 외삽은 조용하다.

    탄성계수를 안 주면 앞 단계 값을 쓴다 — 사람이 같은 숫자를 두 번 적지 않게.
    """
    strain, stress, strain_key, _ = _pair(frame, options)
    require_increasing(strain, what=f"'{strain_key}'")

    modulus = option_float(options, "youngs_modulus")
    offset = option_float(options, "offset_strain", 0.002)
    start = option_float(options, "search_start", float(strain.min()))
    end = option_float(options, "search_end", float(strain.max()))
    if modulus <= 0:
        raise ProcessingError(f"탄성계수가 양수가 아닙니다: {modulus} Pa")
    if offset < 0:
        raise ProcessingError(f"오프셋이 음수입니다: {offset}")
    if start >= end:
        raise ProcessingError(f"탐색 시작({start})이 끝({end}) 이상입니다.")

    mask = (strain >= start) & (strain <= end)
    domain_x, domain_y = strain[mask], stress[mask]
    if len(domain_x) < 2:
        raise ProcessingError(
            f"탐색 구간 [{start:.6g}, {end:.6g}] 안에 {len(domain_x)}점만 있습니다."
        )

    # 오프셋 선 아래로 내려가는 첫 지점. 부호가 + 에서 - 로 바뀌는 곳이 교점이다.
    difference = domain_y - modulus * (domain_x - offset)
    crossings = np.where((difference[:-1] >= 0) & (difference[1:] <= 0))[0]
    if not len(crossings):
        raise ProcessingError(
            f"{offset * 100:.3g}% 오프셋 선이 탐색 구간 안에서 곡선과 만나지 않습니다. "
            f"탄성계수({modulus / 1e9:.4g} GPa)가 맞는지, 탐색 구간을 항복 뒤까지 "
            f"넓혀야 하는지 확인하세요. **외삽해서 값을 만들지 않습니다.**"
        )

    index = int(crossings[0])
    span = difference[index] - difference[index + 1]
    fraction = 0.0 if span == 0 else float(difference[index] / span)
    proof_strain = float(domain_x[index] + fraction * (domain_x[index + 1] - domain_x[index]))
    value = float(domain_y[index] + fraction * (domain_y[index + 1] - domain_y[index]))

    return StepResult(
        frame,
        notes=(
            f"{offset * 100:.3g}% 오프셋 선이 변형률 {proof_strain:.6g} 에서 곡선과 "
            f"만납니다 — {value / 1e6:.4g} MPa (관측 구간 안의 교점).",
        ),
        scalars=(
            Scalar("proof_stress", "항복강도", value, "Pa"),
            Scalar("proof_strain", "항복 변형률", proof_strain, "1", "strain"),
            Scalar("proof_offset", "오프셋", offset, "1", "strain"),
        ),
    )


@register(
    id="tensile.strength",
    kind="processing",
    label="인장강도·연신율",
    params=(
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    makes_values=(
        Produced(
            key="tensile_strength",
            label="인장강도",
            si_unit="Pa",
            help="최대 공칭응력(UTS). 곡선의 봉우리입니다.",
        ),
        Produced(
            key="strain_at_strength",
            label="최대하중 변형률",
            si_unit="1",
            help="봉우리에서의 변형률. 균일 변형이 끝나는 지점으로 봅니다.",
        ),
        Produced(
            key="elongation_observed",
            label="관측 최대 변형률",
            si_unit="1",
            help=(
                "**파단 연신율이 아닙니다** — 기록이 끝난 지점입니다. "
                "장비가 파단 뒤에도 적으면 그만큼 커집니다."
            ),
        ),
    ),
    order=70,
    version="1",
)
def strength(frame: Frame, options: dict[str, Any]) -> StepResult:
    """최대 공칭응력(UTS)과 그때의 변형률, 그리고 관측 최대 변형률.

    **연신율은 '관측된 끝'이지 파단 연신율이 아니다.** 장비가 파단 후에도 기록을
    이어 가거나, 반대로 파단 전에 멈추기도 한다. 그 구분은 곡선만 봐서는 알 수
    없으므로 이름과 근거에 사실만 적는다.
    """
    strain, stress, _, _ = _pair(frame, options)
    if len(stress) < 2:
        raise ProcessingError("2점 미만입니다.")

    peak = int(np.argmax(stress))
    return StepResult(
        frame,
        notes=(
            f"최대 공칭응력 {float(stress[peak]) / 1e6:.4g} MPa "
            f"(변형률 {float(strain[peak]):.6g}, {peak + 1}번째 점). "
            f"연신율은 **관측 구간의 끝**이며 파단점이 아닙니다.",
        ),
        scalars=(
            Scalar("tensile_strength", "인장강도", float(stress[peak]), "Pa"),
            Scalar(
                "strain_at_strength", "최대하중 변형률", float(strain[peak]), "1", "strain"
            ),
            Scalar(
                "elongation_observed", "관측 최대 변형률", float(strain[-1]), "1", "strain"
            ),
        ),
    )


@register(
    id="tensile.necking_candidate",
    kind="processing",
    label="네킹 후보",
    params=(
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    makes_values=(
        Produced(
            key="necking_candidate_index",
            label="네킹 후보 위치",
            si_unit="1",
            help=("몇 번째 점인가. 진응력 단계의 '자를 위치'에 그대로 넣을 수 있습니다."),
        ),
        Produced(key="necking_candidate_strain", label="네킹 후보 변형률", si_unit="1"),
        Produced(key="necking_candidate_stress", label="네킹 후보 응력", si_unit="Pa"),
    ),
    order=80,
    version="1",
)
def necking_candidate(frame: Frame, options: dict[str, Any]) -> StepResult:
    """최대 공칭응력 지점을 네킹 후보로 제시한다. **아무것도 자르지 않는다.**

    이 단계가 따로 있는 이유가 태도 전부다. 네킹 이후의 공칭 응력-변형률은
    균일 변형이 아니라서 진응력 변환식이 성립하지 않는다. 그런데 어디서
    네킹이 시작됐는지는 **곡선만 봐서는 확정할 수 없다** — 최대하중점은 근거가
    있는 후보일 뿐이다.

    그래서 후보만 내고 자르는 것은 사람이 정한다. 자동으로 잘라 버리면 잘렸다는
    사실이 화면 어디에도 안 남고, 그 뒤 계산은 전부 그 가정 위에 선다.
    """
    strain, stress, _, _ = _pair(frame, options)
    index = int(np.argmax(stress))
    if not 1 <= index < len(stress):
        raise ProcessingError(
            f"최대응력이 {index}번째 점이라 네킹 후보로 쓸 수 없습니다 — "
            f"곡선이 단조 감소하거나 점이 너무 적습니다."
        )
    return StepResult(
        frame,
        notes=(
            f"네킹 후보는 최대하중점(index {index}, "
            f"변형률 {float(strain[index]):.6g}) 입니다. **자동 후보일 뿐 "
            f"아무것도 자르지 않았습니다** — 자를지는 사람이 정합니다.",
        ),
        scalars=(
            Scalar("necking_candidate_index", "네킹 후보 위치", float(index), "1"),
            Scalar(
                "necking_candidate_strain",
                "네킹 후보 변형률",
                float(strain[index]),
                "1",
                "strain",
            ),
            Scalar("necking_candidate_stress", "네킹 후보 응력", float(stress[index]), "Pa"),
        ),
    )


@register(
    id="tensile.true_plastic",
    kind="processing",
    label="진응력·진소성변형률",
    params=(
        ParamSpec(
            name="youngs_modulus",
            label="탄성계수",
            type="float",
            unit="Pa",
            required=True,
            help="앞 단계에서 잰 값을 그대로 쓰거나, 직접 넣습니다.",
        ),
        ParamSpec(
            name="necking_policy",
            label="네킹 경계",
            type="choice",
            default="observed_full_domain",
            choices=("observed_full_domain", "manual_index"),
            choice_labels={
                "observed_full_domain": "관측 전체 (자르지 않음)",
                "manual_index": "지정한 위치에서 자름",
            },
            help="자르지 않으면 네킹 뒤가 섞입니다 — 변환식은 균일 변형을 전제합니다.",
        ),
        ParamSpec(
            name="manual_index",
            label="자를 위치",
            type="int",
            required=True,
            # **앞 단계가 낸 후보를 그대로 집는다.** 손으로 옮겨 적게 하면
            # 곡선을 다시 처리했을 때 옛 index 가 남고, 그 결과는 그럴듯해
            # 보인다 — 네킹을 엉뚱한 데서 자른 표가 덱으로 간다.
            links_to="necking_candidate_index",
            when={"necking_policy": ("manual_index",)},
            help="네킹 후보 단계가 낸 위치를 이어 붙일 수 있습니다. 그 점까지가 "
            "균일 변형이고, 뒤는 진응력 변환식이 성립하지 않습니다.",
        ),
        ParamSpec(
            name="negative_policy",
            label="음의 소성변형률",
            type="choice",
            default="clip_zero",
            choices=("clip_zero", "drop", "retain"),
            choice_labels={
                "clip_zero": "0 으로 자름",
                "drop": "버림",
                "retain": "그대로 둠",
            },
            help="탄성 되돌림 때문에 초기 구간이 음수로 나옵니다.",
        ),
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    makes_columns=(
        Produced(
            key=TRUE_STRAIN,
            label="진변형률",
            si_unit="1",
            help="ln(1 + 공칭변형률). 매 순간의 길이를 기준으로 다시 잰 변형률입니다.",
        ),
        Produced(
            key=TRUE_STRESS,
            label="진응력",
            si_unit="Pa",
            help=(
                "공칭응력 곱하기 (1 + 공칭변형률). 줄어든 실제 단면으로 나눈 값입니다. "
                "**CAE 카드가 이 열을 씁니다.**"
            ),
        ),
        Produced(
            key=PLASTIC_STRAIN,
            label="진소성변형률",
            si_unit="1",
            help=(
                "진변형률 빼기 진응력/E. 탄성으로 되돌아갈 몫을 뺀 것입니다. "
                "**경화식 적합과 CAE 카드의 x 축입니다.**"
            ),
        ),
    ),
    order=90,
    version="1",
)
def true_plastic(frame: Frame, options: dict[str, Any]) -> StepResult:
    """공칭 → 진응력·진변형률·진소성변형률.

        true_strain    = ln(1 + eng_strain)
        true_stress    = eng_stress * (1 + eng_strain)
        plastic_strain = true_strain - true_stress / E

    **이 식은 균일 변형을 전제한다.** 네킹 뒤에는 성립하지 않으므로, 자르지 않고
    전체를 쓰면 근거에 경고를 남긴다 — 조용히 넘어가면 그 곡선으로 적합한 경화식이
    네킹 후 구간까지 맞추려다 전체를 왜곡한다.

    탄성 되돌림 때문에 초기 구간의 소성변형률이 **음수**로 나온다. 0 으로 자르는
    것이 기본이지만 버리거나 남길 수도 있게 둔다 — 적합 코드마다 요구가 다르다.
    """
    strain, stress, strain_key, stress_key = _pair(frame, options)
    require_increasing(strain, what=f"'{strain_key}'")

    modulus = option_float(options, "youngs_modulus")
    if modulus <= 0:
        raise ProcessingError(f"탄성계수가 양수가 아닙니다: {modulus} Pa")
    if np.any(strain <= -1):
        raise ProcessingError("공칭 변형률에 -1 이하가 있어 ln(1+ε) 를 계산할 수 없습니다.")
    if np.any(stress < 0):
        raise ProcessingError(
            "공칭 응력에 음수가 있습니다. 앞에서 압축·제하 구간을 잘라내세요."
        )

    policy = option_text(options, "necking_policy", ("observed_full_domain", "manual_index"))
    if policy == "observed_full_domain":
        boundary = len(strain) - 1
    else:
        boundary = option_int(options, "manual_index")
    if not 1 <= boundary < len(strain):
        raise ProcessingError(
            f"자를 위치 {boundary} 가 범위를 벗어납니다 (1 ~ {len(strain) - 1}). "
            f"최소 2점은 남아야 합니다."
        )

    cut = frame.select(np.arange(boundary + 1))
    eng_strain = cut.columns[strain_key]
    eng_stress = cut.columns[stress_key]

    true_strain = np.log1p(eng_strain)
    true_stress = eng_stress * (1.0 + eng_strain)
    plastic = true_strain - true_stress / modulus

    negative = option_text(options, "negative_policy", ("clip_zero", "drop", "retain"))
    notes = [
        f"E={modulus / 1e9:.4g} GPa 로 진응력·진소성변형률을 만들었습니다 "
        f"(네킹 경계 {policy}, index {boundary})."
    ]
    if policy == "observed_full_domain":
        notes.append(
            "관측 전체를 썼습니다 — **네킹 뒤 구간이 섞여 있을 수 있습니다.** "
            "진응력 변환식은 균일 변형을 전제합니다. 'tensile.necking_candidate' 가 "
            "제시한 후보로 잘라 다시 계산해 비교해 보세요."
        )

    negative_count = int(np.sum(plastic < 0))
    if negative == "clip_zero":
        plastic = np.maximum(plastic, 0.0)
        if negative_count:
            notes.append(f"음의 진소성변형률 {negative_count}점을 0 으로 잘랐습니다.")
    elif negative == "drop":
        keep = plastic > 0.0
        if int(np.sum(keep)) < 2:
            raise ProcessingError(
                "양의 진소성변형률이 2점 미만입니다. 탄성계수가 과대하거나 "
                "탄성 구간만 측정된 곡선일 수 있습니다."
            )
        cut = cut.select(keep)
        true_strain, true_stress, plastic = true_strain[keep], true_stress[keep], plastic[keep]
        notes.append(f"양이 아닌 진소성변형률 {negative_count}점을 버렸습니다.")
    elif negative_count:
        notes.append(f"음의 진소성변형률 {negative_count}점을 그대로 남겼습니다.")

    return StepResult(
        cut.with_columns(
            {TRUE_STRAIN: true_strain, TRUE_STRESS: true_stress, PLASTIC_STRAIN: plastic},
            {TRUE_STRAIN: "1", TRUE_STRESS: "Pa", PLASTIC_STRAIN: "1"},
        ),
        notes=tuple(notes),
    )
