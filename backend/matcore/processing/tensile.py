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
from dataclasses import dataclass
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
from matcore.processing._auto_yield_fit import (
    AutoYieldFitError,
    AutoYieldFitResult,
    fit_event_cores,
)
from matcore.processing._drop_recovery import DropEvent, detect_events

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


def _window_from_displacement(
    frame: Frame, options: dict[str, Any], strain: np.ndarray
) -> tuple[float, float, str]:
    """변위로 적은 구간을 **그 곡선 위에서** 변형률로 옮긴다.

    사람이 보는 원본 그래프는 하중-변위다. 거기서 직선 구간을 눈으로 고른 뒤
    변형률로 적으려면 게이지 길이를 손으로 나눠야 하고, **그 자리에서 틀린다** —
    실사용에서 나왔다(2026-09-02: 「f-delta 그래프를 보고 구간을 입력해야 하는데
    strain 기준으로 입력하다 보니 몇으로 해야 할지 모르겠다」).

    **게이지 길이를 다시 받지 않는다.** 곡선에 변위 열이 그대로 남아 있으므로
    같은 행의 변형률을 보간해 쓴다 — 앞 단계가 무엇으로 나눴든 그것과 어긋나지
    않는다(따로 받으면 두 값이 갈리는 순간이 온다).
    """
    displacement = frame.require("displacement", what="변위")
    # SI(m)로 온다 — 화면이 mm 를 받아 환산해 보낸다. 여기서 또 나누면 1000배 틀어진다.
    low_m = option_float(options, "minimum_displacement", float("nan"))
    high_m = option_float(options, "maximum_displacement", float("nan"))
    if not (math.isfinite(low_m) and math.isfinite(high_m)):
        raise ProcessingError("구간을 변위로 적기로 했으면 시작과 끝을 둘 다 주세요.")
    if low_m >= high_m:
        raise ProcessingError(
            f"변위 구간이 뒤집혔습니다: {low_m * 1e3:.4g} ≥ {high_m * 1e3:.4g} mm"
        )

    order = np.argsort(displacement, kind="stable")
    low = float(np.interp(low_m, displacement[order], strain[order]))
    high = float(np.interp(high_m, displacement[order], strain[order]))
    return (
        low,
        high,
        f"변위 {low_m * 1e3:.4g}~{high_m * 1e3:.4g} mm 로 적은 구간을 "
        f"변형률 {low:.5g}~{high:.5g} 로 옮겼습니다.",
    )


#: 참고로만 내는 기울기의 키. **`youngs_modulus` 와 다른 이름이어야 한다** —
#: 같은 이름이면 항복강도·카드·덱이 그대로 물어 가고, 그것이 이 가드를 만든 이유다.
REFERENCE_SLOPE = "elastic_slope_reference"


def _reference_slope(
    strain: np.ndarray, stress: np.ndarray, band_low: float, band_high: float
) -> tuple[tuple[Scalar, ...], str]:
    """믿을 수 없는 구간의 기울기를 **참고값으로** 낸다.

    「점이 몇 개 없어도 일단 그 기울기는 계산해 줄 수 있지 않나」 — 맞는 말이다
    (2026-09-02). 사람이 그 숫자를 보면 **맞는지 아닌지 대개 안다**: 강판인데 1.8
    GPa 가 나오면 구간이 틀린 것이고, 190 GPa 면 점이 둘이어도 쓸 만하다.

    **다른 이름으로 낸다.** `youngs_modulus` 로 내면 항복강도가 그것을 물어 가고
    카드와 덱까지 흘러간다 — 값을 못 믿는다고 판단해 놓고 뒷문으로 내보내는 셈이다.
    쓰기로 했으면 사람이 「직접 입력」 에 옮겨 적는다. 그 한 번의 손이 「이 값을
    쓰겠다」 는 결정이고, 결과에도 그렇게 남는다.

    점이 둘도 없으면 기울기 자체가 없다 — 그때는 아무것도 안 낸다.
    """
    peak = float(np.max(stress)) if stress.size else 0.0
    # NaN 은 모든 비교에서 False 라 `peak <= 0` 을 **통과해 버린다** — 빠진 칸이
    # 섞인 곡선에서 NaN 기울기가 JSON 까지 흘러간다.
    if not math.isfinite(peak) or peak <= 0:
        return (), ""
    mask = (stress >= peak * band_low) & (stress <= peak * band_high)
    if int(np.sum(mask)) < 2:
        # 띠가 너무 좁으면 상승 구간 앞쪽으로 넓혀 본다 — **참고값이라** 구간이
        # 넓어도 되고, 아무 숫자도 없는 것보다 낫다.
        rising = int(np.argmax(stress)) + 1
        mask = np.zeros_like(stress, dtype=bool)
        mask[: max(2, min(rising, 5))] = True
    x, y = strain[mask], stress[mask]
    if x.size < 2 or float(np.ptp(x)) <= 0:
        return (), ""
    slope = float(np.polyfit(x, y, 1)[0])
    if not math.isfinite(slope):
        return (), ""
    return (
        (Scalar(REFERENCE_SLOPE, "참고 기울기(믿을 수 없음)", slope, "Pa"),),
        f" 그 구간의 기울기는 **{slope / 1e9:.4g} GPa** 입니다 — 참고값입니다. "
        f"맞다고 보시면 방법을 「직접 입력」 으로 두고 이 값을 넣으세요.",
    )


def _uniform_grid(x: Any) -> int:
    """이 x 축이 **균등 격자인가** — 맞으면 점 수, 아니면 0.

    ## 왜 이것을 알아야 하나 (실측 2026-09-11)

    표준 레시피가 재샘플(400점)을 이 단계 **앞**에 두고 있었다. 그러면 탄성계수는
    잰 점이 아니라 **격자점**으로 계산된다. 금속은 항복이 변형률 0.002 언저리인데
    곡선은 0.4 까지 가므로, 400점을 전 구간에 고르게 뿌리면 항복 전에는
    **한두 점**만 남는다 — 실제로 시험 다섯 건 전부 「띠 안에 0~1점」 으로 값이
    안 나왔다.

    ## 점을 늘려서 풀면 안 되는 이유

    같은 곡선을 4000점으로 재샘플하면 띠 안에 6~12점이 들어와 값이 **나온다.**
    그런데 잰 점이 18개뿐인 곡선에서도 6점이 들어온다 — 그 6점은 두 잰 점 사이를
    직선으로 이은 자리라 **새 정보가 없고**, 직선 위의 점이라 R² 도 1 에 붙는다.
    점 수와 R² 두 방어가 함께 뚫린다.

    그래서 여기서는 **격자라는 사실을 말해 준다.** 값을 막지는 않는다 — 촘촘한
    곡선을 재샘플한 것이면 기울기는 맞다(실측 205.9 GPa, 잰 점으로 계산한 것과
    같았다). 다만 「점이 몇 개」 라는 말의 뜻이 달라지므로 그것을 적는다.
    """
    values = np.asarray(x, dtype=float)
    if values.size < 3:
        return 0
    gaps = np.diff(values)
    span = float(values[-1] - values[0])
    if span <= 0 or not np.all(np.isfinite(gaps)):
        return 0
    # `np.linspace` 가 만든 격자는 간격이 부동소수 오차 안에서 같다.
    return int(values.size) if float(np.ptp(gaps)) <= abs(span) * 1e-9 else 0


#: 격자 위에서 계산할 때 붙이는 말. **점 수의 뜻이 달라진다.**
GRID_NOTE = (
    "이 곡선은 **균등 격자로 재샘플된 것**입니다({count}점) — 아래의 점 수는 잰 점이 "
    "아니라 보간된 점을 셉니다. 잰 점으로 계산하려면 레시피에서 "
    "**「균등 격자로 재샘플」 을 이 단계 뒤로** 옮기세요."
)


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
            name="window_basis",
            label="구간을 무엇으로 적나",
            type="choice",
            choices=("strain", "displacement"),
            default="strain",
            when={"method": ("linear_regression", "chord", "secant")},
            help=(
                "**사람이 보는 그래프로 적게 한다.** 원본 화면은 하중-변위이고, "
                "거기서 직선 구간을 눈으로 고른 뒤 변형률로 환산해 적으려면 "
                "게이지 길이를 손으로 나눠야 한다 — 그 자리에서 틀린다."
            ),
        ),
        # **단위는 SI(m)다 — 다른 모든 칸과 같은 규약.** 화면이 mm 로 바꿔 보여
        # 준다(`shared/units.ts` 의 표). 여기 mm 라고 적으면 지금은 표에 mm 가
        # 없어서 우연히 맞지만, 표에 등재되는 날 값이 조용히 1000배 틀어진다.
        ParamSpec(
            name="minimum_displacement",
            dimension="length",
            label="구간 시작(변위)",
            type="float",
            unit="m",
            when={"window_basis": ("displacement",)},
            help="원본 곡선의 x 축 그대로입니다. 그 값들 사이의 점으로 직선을 얹습니다.",
        ),
        ParamSpec(
            name="maximum_displacement",
            dimension="length",
            label="구간 끝(변위)",
            type="float",
            unit="m",
            when={"window_basis": ("displacement",)},
            help="항복 전이어야 합니다 — 넘으면 기울기가 눕습니다.",
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
            property_key="mechanical.youngs_modulus",
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
            key=REFERENCE_SLOPE,
            label="참고 기울기(믿을 수 없음)",
            si_unit="Pa",
            help=(
                "점이 모자라거나 직선이 아니어서 **탄성계수로는 안 낸** 구간의 기울기입니다. "
                "**이 값은 뒤 단계로 안 갑니다** — 쓰기로 했으면 「직접 입력」 에 옮겨 "
                "적으세요. 그 한 번의 손이 「이 값을 쓰겠다」 는 결정입니다."
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
    basis_note: str | None = None
    # 기본은 변형률 — `option_text` 는 목록의 첫 값을 기본으로 쓴다.
    if option_text(options, "window_basis", ("strain", "displacement")) == "displacement":
        low, high, basis_note = _window_from_displacement(frame, options, strain)

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
            hint, hint_note = _reference_slope(strain, stress, band_low, band_high)
            # **격자 때문이면 고칠 데가 다르다.** 「곡선이 성깁니다」 는 다시 잴
            # 수 없다는 말인데, 사실은 잰 점을 우리가 버린 것일 수 있다.
            grid = _uniform_grid(strain)
            grid_note = (" " + GRID_NOTE.format(count=grid)) if grid else ""
            return StepResult(
                frame,
                notes=(
                    f"최대응력의 {band_low:.0%}~{band_high:.0%} 띠 안에 {in_band}점밖에 "
                    f"없어 **탄성계수를 내지 않았습니다**(상승 구간 전체가 {rising}점)."
                    f"{grid_note} "
                    f"{MIN_TRUSTWORTHY_POINTS}점은 있어야 합니다 — {in_band}점을 지나는 "
                    "직선은 거의 언제나 R²≈1 이라 맞았는지 알 수 없습니다. "
                    "**곡선이 성깁니다.** 이미 찍힌 파일이면 다시 잴 수 없으므로 "
                    "**재료에 적어 둔 탄성계수를 씁니다** — 방법을 「직접 입력」 으로 두고 "
                    "「탄성계수 값」 칸에 `@declared_youngs_modulus` 를 적으면 "
                    "그 값으로 돌고, 결과에는 "
                    "잰 값이 아니라 적은 값이라고 남습니다. 구간을 아는 경우에는 "
                    "「최소제곱 회귀」 로 바꿔 직접 지정하세요." + hint_note,
                ),
                scalars=(
                    Scalar("elastic_point_count", "탄성 구간 점 수", float(in_band), "1"),
                    *hint,
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
        # 격자 위에서 잰 「점 수」 는 잰 점의 수가 아니다 — 거절할 때 그 사실을
        # 말해야 사람이 「곡선이 성기다」 를 고치려 들지 않는다.
        grid = _uniform_grid(strain)
        grid_note = (" " + GRID_NOTE.format(count=grid)) if grid else ""
        refused = None
        if count < MIN_TRUSTWORTHY_POINTS:
            refused = (
                f"{window}에 {count}점밖에 없어 **탄성계수를 내지 않았습니다.** "
                f"{MIN_TRUSTWORTHY_POINTS}점은 있어야 합니다 — {count}점을 지나는 직선은 "
                f"거의 언제나 R²≈1 이라 맞았는지 알 수 없습니다. 구간을 넓히거나, "
                f"**재료에 적어 둔 탄성계수를 쓰세요** — 방법을 「직접 입력」 으로 두고 "
                f"「탄성계수 값」 칸에 `@declared_youngs_modulus` 를 적으면 그 값으로 돕니다"
                f"(재료 > 물성에 적어 두어야 합니다). "
                # **숫자를 보여 준다.** 사람은 그 값을 보면 맞는지 대개 안다 —
                # 강판인데 1.8 GPa 면 구간이 틀린 것이고, 190 GPa 면 점이 둘이어도
                # 쓸 만하다. 쓰기로 했으면 「직접 입력」 에 옮겨 적는다.
                f"그 구간의 기울기는 **{modulus / 1e9:.4g} GPa** 입니다 — 참고값입니다. "
                f"{observed}{grid_note}"
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
                f"「직접 입력」 으로 바꾸세요. {advice}{observed}{grid_note}"
            )
        if refused is not None:
            # **인장강도·연신율은 멀쩡히 나온 것이다.** 단계를 실패시키면 사람이
            # 원인을 고치는 대신 이 단계를 빼 버린다.
            #
            # 남기는 것은 **거절의 근거**뿐이다. 점이 모자라 거절했으면 R² 는 안
            # 남긴다 — 2점의 R²=1 이 화면에 뜨면 「완벽한데 왜 값이 없지」 가 된다.
            scalars = [Scalar("elastic_point_count", "탄성 구간 점 수", float(count), "1")]
            # **참고 기울기는 다른 이름으로 낸다.** `youngs_modulus` 로 내면
            # 항복강도가 물어 가고 카드와 덱까지 간다 — 못 믿는다고 판단해 놓고
            # 뒷문으로 내보내는 셈이다.
            if math.isfinite(modulus):
                scalars.append(
                    Scalar(REFERENCE_SLOPE, "참고 기울기(믿을 수 없음)", float(modulus), "Pa")
                )
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
    if basis_note is not None:
        # 변위로 적은 값을 변형률로 옮겼다는 사실을 남긴다 — 나중에 이 결과를 보는
        # 사람은 변형률만 보게 되는데, 사람이 적은 것은 mm 였다.
        note = f"{basis_note} {note}"
    notes = [note]
    # **값이 나왔어도 격자면 말한다.** 여기가 조용히 틀리는 자리다 — 잰 점이
    # 18개뿐인 곡선을 4000점으로 재샘플하면 띠 안에 6점이 들어오고 R² 는 1 에
    # 붙는다. 두 방어가 함께 뚫리므로, 사람이 그 수를 잰 점으로 읽지 않게 한다.
    if method != "manual":
        on_grid = _uniform_grid(strain)
        if on_grid:
            notes.append(GRID_NOTE.format(count=on_grid))
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
            property_key="mechanical.yield_strength",
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
            property_key="mechanical.tensile_strength",
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


def _prepare_true_plastic_options(options: dict[str, Any]) -> dict[str, Any]:
    """Pair old saved proof-stress references with the matching proof strain."""
    if (
        options.get("yield_policy", "proof_stress") == "proof_stress"
        and options.get("proof_stress") == "@proof_stress"
        and "proof_strain" not in options
    ):
        return {**options, "proof_strain": "@proof_strain"}
    return dict(options)


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
            name="yield_policy",
            label="항복 정의",
            type="choice",
            default="proof_stress",
            choices=("proof_stress", "line_crossing"),
            choice_labels={
                "proof_stress": "항복강도(Rp)부터",
                "line_crossing": "E 직선을 넘는 곳부터 (옛 방식)",
            },
            choice_help={
                "proof_stress": (
                    "앞 단계가 잰 항복강도보다 낮은 점을 버리고 첫 점을 소성변형률 0 에 "
                    "앉힙니다. 오프셋이 곧 소성 곡선의 시작입니다."
                ),
                "line_crossing": (
                    "ε - σ/E 가 양수가 되는 곳부터입니다. 토우·장비 컴플라이언스가 있으면 "
                    "탄성 구간이 소성 곡선에 남습니다."
                ),
            },
            help="소성 곡선이 어디서 시작하는가.",
        ),
        ParamSpec(
            name="proof_stress",
            label="항복강도",
            type="float",
            unit="Pa",
            # **앞 단계의 값을 가리키는 것이 기본이다.** 사람이 옮겨 적으면 오프셋을
            # 바꿔 항복강도를 다시 쟀는데 소성 곡선은 옛 항복점에서 시작한다.
            default="@proof_stress",
            required=True,
            when={"yield_policy": ("proof_stress",)},
            help=(
                "항복강도 단계가 잰 값(공칭응력). 대응하는 교점 변형률과 함께 "
                "시작점을 정합니다."
            ),
        ),
        ParamSpec(
            name="proof_strain",
            label="항복 변형률",
            type="float",
            dimension="strain",
            unit="1",
            default=None,
            when={"yield_policy": ("proof_stress",)},
            help=(
                "내력 값과 함께 그 교점의 변형률을 연결합니다. 수동 응력 기준만 "
                "사용할 때는 비워 둡니다."
            ),
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
    version="3",
    prepare_options=_prepare_true_plastic_options,
)
def true_plastic(frame: Frame, options: dict[str, Any]) -> StepResult:
    """공칭 → 진응력·진변형률·진소성변형률.

        true_strain    = ln(1 + eng_strain)
        true_stress    = eng_stress * (1 + eng_strain)
        plastic_strain = true_strain - true_stress / E

    **이 식은 균일 변형을 전제한다.** 네킹 뒤에는 성립하지 않으므로, 자르지 않고
    전체를 쓰면 근거에 경고를 남긴다 — 조용히 넘어가면 그 곡선으로 적합한 경화식이
    네킹 후 구간까지 맞추려다 전체를 왜곡한다.

    ## 소성 곡선은 항복점부터다 (2026-09-11 VOC)

    v1 은 이 식을 첫 점부터 적용하고 음수만 0 으로 눌렀다. 「어디서부터 소성인가」
    를 정하는 자리가 없어서, 소성 곡선의 시작은 **곡선이 기울기 E 인 직선을 넘는
    곳**이 됐다 — 그것은 노이즈·토우·장비 컴플라이언스·E 값이 정하지 항복이 정하지
    않는다. 합성 강판 곡선으로 재현: 토우가 있으면 항복 앞의 20~50점이 양의
    소성변형률을 달고 그대로 남아 덱 첫 점이 (0, 0 MPa) 가 되고, Voce 항복이
    304 → 225 MPa 로 내려앉았다. 항복강도 단계의 오프셋은 **아무도 읽지 않아서**
    아무리 바꿔도 이 열은 비트 하나 안 바뀌었다.

    그래서 기본은 앞 단계가 낸 항복강도와 그 교점 변형률을 함께 받아, 그 좌표를
    (소성변형률 0, 공칭응력 Rp) 의 첫 점으로 둔다. 곡선을 다시 검색하지 않으므로 중간에
    재샘플해도 원래 교점이 보존된다. 뒤의 관측점은 식 그대로다 — 오프셋 정의상 항복점에는
    이미 오프셋만큼의 영구 변형이 있으므로 둘째 점의 소성변형률은 오프셋 근처에서
    시작한다. 잰 점을 옮기지 않는다. 옛 방식은 `line_crossing` 으로 남겨 둔다.

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

    yield_policy = option_text(options, "yield_policy", ("proof_stress", "line_crossing"))
    if yield_policy == "proof_stress":
        if options.get("proof_stress") is None:
            raise ProcessingError(
                "항복강도 값이 없습니다. 앞에 '항복강도' 단계를 두고 이 칸에 "
                "'@proof_stress' 를 이어 붙이거나, 항복 정의를 '옛 방식' 으로 두세요."
            )
        proof = option_float(options, "proof_stress")
        if proof <= 0:
            raise ProcessingError(f"항복강도가 양수가 아닙니다: {proof} Pa")

        raw_proof_strain = options.get("proof_strain")
        if raw_proof_strain is not None:
            yield_strain = option_float(options, "proof_strain")
            if yield_strain < float(eng_strain[0]) or yield_strain > float(eng_strain[-1]):
                raise ProcessingError(
                    f"항복 변형률 좌표 {yield_strain:.6g}가 관측 변형률 범위 "
                    f"[{eng_strain[0]:.6g}, {eng_strain[-1]:.6g}]를 벗어납니다."
                )

            right = int(np.searchsorted(eng_strain, yield_strain, side="left"))
            exact = right < len(eng_strain) and eng_strain[right] == yield_strain
            first_after = right + 1 if exact else right
            if len(eng_strain) - first_after < 2:
                raise ProcessingError(
                    f"항복 변형률 좌표 {yield_strain:.6g} 뒤에 관측점이 2점 미만입니다. "
                    "교점 뒤에 관측점 두 개 이상이 남도록 네킹 경계나 입력 곡선을 확인하세요."
                )

            if exact:
                # 교점이 이미 관측 행이면 중복 x 를 만들지 않고 그 행부터 잇는다.
                cut_columns = {
                    key: values[right:].copy() for key, values in cut.columns.items()
                }
                cut_columns[strain_key] = cut_columns[strain_key].astype(
                    np.float64, copy=False
                )
                cut_columns[stress_key] = cut_columns[stress_key].astype(
                    np.float64, copy=False
                )
                cut_columns[strain_key][0] = yield_strain
                cut_columns[stress_key][0] = proof
                cut = Frame(cut_columns, dict(cut.units))
                yield_true = proof * (1.0 + yield_strain)
                true_strain = np.concatenate(
                    [[np.log1p(yield_strain)], true_strain[right + 1 :]]
                )
                true_stress = np.concatenate([[yield_true], true_stress[right + 1 :]])
                plastic = np.concatenate([[0.0], plastic[right + 1 :]])
            else:
                left = right - 1
                fraction = float(
                    (yield_strain - eng_strain[left]) / (eng_strain[right] - eng_strain[left])
                )
                # 모든 채널은 같은 strain bracket 으로 보간한다. proof scalar 는
                # 원래 교점 계산의 값을 보존하므로 x 와 y 에 정확히 덮어쓴다.
                yield_row = {
                    key: np.asarray([values[left] + fraction * (values[right] - values[left])])
                    for key, values in cut.columns.items()
                }
                yield_row[strain_key] = np.asarray([yield_strain])
                yield_row[stress_key] = np.asarray([proof])
                cut = Frame(
                    {
                        key: np.concatenate([yield_row[key], values[right:]])
                        for key, values in cut.columns.items()
                    },
                    dict(cut.units),
                )
                yield_true = proof * (1.0 + yield_strain)
                true_strain = np.concatenate([[np.log1p(yield_strain)], true_strain[right:]])
                true_stress = np.concatenate([[yield_true], true_stress[right:]])
                plastic = np.concatenate([[0.0], plastic[right:]])

            notes.append(
                f"항복강도 {proof / 1e6:.4g} MPa(공칭)와 짝지은 변형률 "
                f"{yield_strain:.6g}의 교점을 첫 점으로 앉혔습니다 — 솔버는 첫 점을 "
                "항복점으로 읽습니다. 둘째 점부터는 식 그대로라 오프셋 근처에서 시작합니다."
            )
        else:
            reached = np.flatnonzero(eng_stress >= proof)
            if not len(reached):
                raise ProcessingError(
                    f"항복강도 {proof / 1e6:.4g} MPa 에 이르는 점이 없습니다 — 항복강도를 "
                    f"다른 곡선·다른 E 로 쟀거나, 네킹 경계가 항복 앞에서 잘렸습니다."
                )
            at = int(reached[0])
            if at == 0:
                raise ProcessingError(
                    f"첫 점부터 항복강도 {proof / 1e6:.4g} MPa 이상입니다 — 탄성 구간이 "
                    f"앞에서 잘려 나갔거나 항복강도가 너무 낮습니다."
                )
            if len(eng_stress) - at < 2:
                raise ProcessingError(
                    f"항복강도 {proof / 1e6:.4g} MPa 뒤에 남는 점이 2점 미만입니다."
                )
            # 숫자 Rp 의 옛 레시피는 좌표를 알 수 없으므로 첫 응력 교차를 쓴다.
            below, above = float(eng_stress[at - 1]), float(eng_stress[at])
            fraction = 0.0 if above == below else (proof - below) / (above - below)
            yield_row = {
                key: np.asarray([value[at - 1] + fraction * (value[at] - value[at - 1])])
                for key, value in cut.columns.items()
            }
            yield_strain = float(yield_row[strain_key][0])
            yield_true = proof * (1.0 + yield_strain)
            cut = Frame(
                {
                    key: np.concatenate([yield_row[key], value[at:]])
                    for key, value in cut.columns.items()
                },
                dict(cut.units),
            )
            true_strain = np.concatenate([[np.log1p(yield_strain)], true_strain[at:]])
            true_stress = np.concatenate([[yield_true], true_stress[at:]])
            plastic = np.concatenate([[0.0], plastic[at:]])
            notes.append(
                f"항복강도 {proof / 1e6:.4g} MPa(공칭) 앞의 {at}점을 버리고, 곡선이 그 값을 "
                f"지나는 교점(변형률 {yield_strain:.4g}, 진응력 {yield_true / 1e6:.4g} MPa)을 "
                f"소성변형률 0 의 첫 점으로 앉혔습니다 — 솔버는 첫 점을 항복점으로 읽습니다. "
                f"둘째 점부터는 식 그대로라 오프셋 근처에서 시작합니다."
            )
            notes.append(
                "항복 변형률 좌표 없이 항복강도와 곡선의 첫 응력 교차로 시작점을 잡았습니다."
            )
    else:
        notes.append(
            "소성 곡선을 항복강도가 아니라 「ε - σ/E 가 양수가 되는 곳」 부터 잡았습니다 "
            "(옛 방식). 토우·장비 컴플라이언스가 있으면 탄성 구간이 남습니다."
        )
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


# ── 항복 강하 정리 ────────────────────────────────────────────────────────────

#: 양수인 선행 최대 응력에 견주어 이보다 작은 하강은 잡음이다.
YIELD_DROP_THRESHOLD = 0.005

YIELD_DROP_SCOPES = ("full", "range", "events")
AUTO_LOWER_ENVELOPE_METHOD = "lower_envelope_auto_v1"
AUTO_EVENT_ANCHOR_POLICY = "observed_event_anchors_v1"
_AUTO_PROFILE_THRESHOLD = 0.005
_AUTO_PROFILE_RECOVERY_THRESHOLD = 0.005
_AUTO_PROFILE_MIN_REFERENCE_FRACTION = 0.05
_AUTO_PROFILE_MIN_SLOPE = 0.0


@dataclass(frozen=True)
class _AutoYieldProfile:
    id: str
    method: str
    label: str
    slope_constraint: str | None = None
    anchor_policy: str | None = None


AUTO_YIELD_PROFILES = (
    _AutoYieldProfile("envelope_auto_v1", "envelope", "상측 포락선 — 자동"),
    _AutoYieldProfile("isotonic_auto_v1", "isotonic", "단조 회귀 — 자동"),
    _AutoYieldProfile("lower_envelope_auto_v1", "lower_envelope", "하측 포락선 — 자동"),
    _AutoYieldProfile(
        "median_plateau_auto_v1",
        "median_plateau",
        "중앙값 평탄부 — 자동",
        anchor_policy=AUTO_EVENT_ANCHOR_POLICY,
    ),
    _AutoYieldProfile(
        "linear_auto_v1",
        "linear",
        "양끝 직선 — 자동",
        "nondecreasing",
        AUTO_EVENT_ANCHOR_POLICY,
    ),
    _AutoYieldProfile(
        "least_squares_auto_v1",
        "least_squares",
        "최소제곱 직선 — 자동",
        "nondecreasing",
        AUTO_EVENT_ANCHOR_POLICY,
    ),
    _AutoYieldProfile(
        "robust_linear_auto_v1",
        "robust_linear",
        "Huber 강건 직선 — 자동",
        "nondecreasing",
        AUTO_EVENT_ANCHOR_POLICY,
    ),
)
_AUTO_YIELD_PROFILE_BY_ID = {profile.id: profile for profile in AUTO_YIELD_PROFILES}
AUTO_YIELD_PROFILE_IDS = tuple(profile.id for profile in AUTO_YIELD_PROFILES)
_AUTO_METHOD_HELP = {
    profile.id: (
        (
            f"같은 사건 검출을 사용해 {profile.label.removesuffix(' — 자동')}의 "
            "접합 구간을 자동으로 선택합니다. "
            if profile.anchor_policy is not None
            else (
                f"같은 자동 검출 구간에 {profile.label.removesuffix(' — 자동')}을 적용합니다. "
            )
        )
        + "하강·회복 문턱 0.5%, 기준 봉우리 비율 5%, 최소 기울기 0, "
        "말단 원본 보존 규칙은 고정되어 있습니다."
        + (
            " 직선 기울기는 비감소로 고정합니다."
            if profile.slope_constraint == "nondecreasing"
            else ""
        )
    )
    for profile in AUTO_YIELD_PROFILES
}
# Keep the original private names stable for any in-repository diagnostics.
_AUTO_LOWER_ENVELOPE_THRESHOLD = _AUTO_PROFILE_THRESHOLD
_AUTO_LOWER_ENVELOPE_RECOVERY_THRESHOLD = _AUTO_PROFILE_RECOVERY_THRESHOLD
_AUTO_LOWER_ENVELOPE_MIN_REFERENCE_FRACTION = _AUTO_PROFILE_MIN_REFERENCE_FRACTION
_AUTO_LOWER_ENVELOPE_MIN_SLOPE = _AUTO_PROFILE_MIN_SLOPE
YIELD_DROP_METHODS = (
    "envelope",
    "isotonic",
    "lower_yield",
    "cut",
    "keep",
    "lower_envelope",
    "median_plateau",
    "linear",
    "least_squares",
    "robust_linear",
    *AUTO_YIELD_PROFILE_IDS,
)
_YIELD_DROP_MANUAL_METHODS = tuple(
    method for method in YIELD_DROP_METHODS if method not in _AUTO_YIELD_PROFILE_BY_ID
)
_FULL_METHODS = ("envelope", "isotonic", "lower_yield", "cut", "keep")
_SCOPED_METHODS = (
    "envelope",
    "isotonic",
    "cut",
    "keep",
    "lower_envelope",
    "median_plateau",
    "linear",
    "least_squares",
    "robust_linear",
)
_MONOTONE_SCOPED_METHODS = ("envelope", "isotonic", "lower_envelope")
_REGRESSION_METHODS = ("linear", "least_squares", "robust_linear")


def _option_value_matches(actual: Any, expected: Any) -> bool:
    """Compare possibly malformed stale options without validating or coercing them."""
    try:
        return bool(actual == expected)
    except (TypeError, ValueError):
        return False


def _isotonic(values: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """가중치가 있는 단조 비감소 최소제곱 회귀(PAVA).

    weights 를 생략하면 기존 yield_drop 의 점당 동일 가중치 계약과 같다.
    블록의 점 수가 아니라 실제 가중치로 평균을 내므로, 같은 계산을 독립
    검산하는 쪽에서 SciPy PAVA 결과와 대조할 수 있다.
    """
    source = np.asarray(values, dtype=np.float64)
    if source.ndim != 1:
        raise ValueError("isotonic 입력은 1차원이어야 합니다")
    if not np.all(np.isfinite(source)):
        raise ValueError("isotonic 입력에 유한하지 않은 값이 있습니다")
    if weights is None:
        weight_values = np.ones(source.size, dtype=np.float64)
    else:
        weight_values = np.asarray(weights, dtype=np.float64)
        if weight_values.shape != source.shape:
            raise ValueError("isotonic 가중치의 길이가 값과 다릅니다")
        if not np.all(np.isfinite(weight_values)) or np.any(weight_values <= 0):
            raise ValueError("isotonic 가중치는 양의 유한값이어야 합니다")
    blocks: list[list[float | int]] = []
    for index, (value, weight) in enumerate(zip(source, weight_values, strict=True)):
        blocks.append([float(value), float(weight), index, index + 1])
        while len(blocks) > 1 and float(blocks[-2][0]) > float(blocks[-1][0]):
            left, right = blocks[-2], blocks[-1]
            total = float(left[1]) + float(right[1])
            merged = (
                float(left[0]) * float(left[1]) + float(right[0]) * float(right[1])
            ) / total
            blocks[-2:] = [[merged, total, int(left[2]), int(right[3])]]
    out = np.empty(source.size, dtype=np.float64)
    for level, _weight, start, end in blocks:
        out[int(start) : int(end)] = float(level)
    return out


def _first_drop(stress: np.ndarray, threshold: float) -> int | None:
    """첫 상대 하강 — 양수인 선행 최댓값에서 threshold 만큼 내려간 첫 점."""
    running = np.maximum.accumulate(stress)
    drop = running - stress
    hit = np.nonzero((running > 0) & (drop > threshold * running))[0]
    return int(hit[0]) if hit.size else None


def _finite_pair(
    strain: np.ndarray, stress: np.ndarray, strain_key: str, stress_key: str
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(strain, dtype=np.float64)
    y = np.asarray(stress, dtype=np.float64)
    if x.ndim != 1 or y.ndim != 1:
        raise ProcessingError(f"'{strain_key}' 와 '{stress_key}' 는 1차원 열이어야 합니다.")
    if x.size != y.size:
        raise ProcessingError(
            f"'{strain_key}' 와 '{stress_key}' 의 점 수가 다릅니다: {x.size}, {y.size}"
        )
    if not np.all(np.isfinite(x)):
        raise ProcessingError(f"'{strain_key}' 에 유한하지 않은 값이 있습니다.")
    if not np.all(np.isfinite(y)):
        raise ProcessingError(f"'{stress_key}' 에 유한하지 않은 값이 있습니다.")
    if x.size < 2:
        raise ProcessingError("하강 처리는 관측점이 2점 이상이어야 합니다.")
    return x, y


def _domain_indices(
    strain: np.ndarray, scope: str, options: dict[str, Any]
) -> tuple[np.ndarray, float | None, float | None]:
    has_start = options.get("range_start") is not None
    has_end = options.get("range_end") is not None
    start: float | None
    end: float | None
    if scope == "full":
        if has_start or has_end:
            raise ProcessingError(
                "scope='full' 에서는 range_start/range_end 를 지정할 수 없습니다."
            )
        return np.arange(strain.size, dtype=int), None, None
    if scope == "range" and not (has_start and has_end):
        raise ProcessingError(
            "scope='range' 에서는 range_start 와 range_end 를 함께 지정해야 합니다."
        )
    if has_start != has_end:
        raise ProcessingError(
            "range_start 와 range_end 는 둘 다 지정하거나 둘 다 비워야 합니다."
        )
    if has_start:
        start = option_float(options, "range_start")
        end = option_float(options, "range_end")
        if not start < end:
            raise ProcessingError(f"선택 범위 시작({start})이 끝({end})보다 작아야 합니다.")
        observed_min = float(np.min(strain))
        observed_max = float(np.max(strain))
        if start < observed_min or end > observed_max:
            raise ProcessingError(
                f"선택 범위({start}~{end})가 관측 변형률 범위"
                f"({observed_min}~{observed_max}) 안에 있어야 합니다."
            )
        selected = np.flatnonzero((strain >= start) & (strain <= end))
        if selected.size < 2:
            raise ProcessingError(f"선택 범위 {start}~{end} 에 관측점이 2점 미만입니다.")
    else:
        start = end = None
        selected = np.arange(strain.size, dtype=int)
    if selected.size < 2:
        raise ProcessingError("선택 계산 범위에 관측점이 2점 미만입니다.")
    if selected.size > 1 and np.any(np.diff(selected) != 1):
        raise ProcessingError(
            "선택 계산 범위가 원행에서 이어지지 않습니다(disconnected-domain). "
            "행을 이어 붙이거나 원행 순서를 바꾸지 않고 범위를 다시 지정하세요."
        )
    return selected, start, end


def _actual_domain_note(
    indices: np.ndarray,
    strain: np.ndarray,
    scope: str,
    requested_start: float | None,
    requested_end: float | None,
) -> str:
    actual_start = float(strain[int(indices[0])])
    actual_end = float(strain[int(indices[-1])])
    requested = (
        f", 요청 변형률 {requested_start:.6g}~{requested_end:.6g}"
        if requested_start is not None and requested_end is not None
        else ""
    )
    return (
        f"계산 scope={scope}, 실제 원행 index {int(indices[0])}~{int(indices[-1])}, "
        f"변형률 {actual_start:.6g}~{actual_end:.6g}{requested}"
    )


def _event_scalars(events: list[DropEvent]) -> list[Scalar]:
    full = sum(event.kind == "full_recovery" for event in events)
    partial = sum(event.kind == "partial_recovery" for event in events)
    terminal = sum(event.kind == "terminal_unrecovered" for event in events)
    open_partial = sum(
        event.kind == "partial_recovery" and event.end_at_observation_boundary
        for event in events
    )
    return [
        Scalar("event_count", "검출 사건 수", float(len(events)), "1"),
        Scalar("recovered_count", "완전 회복 사건 수", float(full), "1"),
        Scalar("partial_count", "부분 회복 사건 수", float(partial), "1"),
        Scalar(
            "open_partial_count", "관측 종료 열린 부분 회복 사건 수", float(open_partial), "1"
        ),
        Scalar("unrecovered_count", "미회복 사건 수", float(terminal), "1"),
    ]


def _event_notes(
    events: list[DropEvent],
    domain: np.ndarray,
    strain: np.ndarray,
    stress: np.ndarray,
    threshold: float,
    min_reference_fraction: float,
) -> list[str]:
    domain_stress = stress[domain]
    positive = domain_stress[domain_stress > 0]
    reference_max = float(np.max(positive)) if positive.size else 0.0
    floor = reference_max * min_reference_fraction
    low_rows = int(np.count_nonzero((domain_stress > 0) & (domain_stress < floor)))
    notes = [
        f"양의 관측응력 최댓값 {reference_max:.6g} Pa의 "
        f"{min_reference_fraction:.6g} 배({floor:.6g} Pa) 미만인 {low_rows}점은 "
        "상대 하강 기준에서 제외했습니다.",
        f"하강 문턱 {threshold:.6g}에 따라 원행 순서로 사건을 검출했습니다. "
        "검출만으로 시편 파손·잡음 등의 원인을 확정하지 않습니다.",
    ]
    if any(event.kind == "full_recovery" for event in events):
        notes.append(
            "full_recovery는 첫 원봉우리 복귀까지의 내부 하강을 한 outer 사건으로 묶었습니다. "
            "recovery index는 trough 뒤 의미 있는 반등 시작입니다."
        )
    for number, event in enumerate(events, start=1):
        peak = int(event.peak_index)
        trough = int(event.trough_index)
        end = int(event.end_index)
        recovery = (
            str(int(event.recovery_index)) if event.recovery_index is not None else "없음"
        )
        notes.append(
            f"사건 {number}: peak index {peak}, drop_start index {int(event.drop_start)}, "
            f"trough index {trough}, recovery index {recovery}, end index {end}, "
            f"분류 {event.kind}, 관측끝={event.end_at_observation_boundary}, "
            f"peak 변형률 {float(strain[peak]):.6g}, "
            f"trough 응력 {float(stress[trough]):.6g} Pa."
        )
    return notes


def _absolute_events(local_events: list[DropEvent], domain: np.ndarray) -> list[DropEvent]:
    def convert(event: DropEvent) -> DropEvent:
        def row(value: int) -> int:
            return int(domain[value])

        return DropEvent(
            row(event.peak_index),
            row(event.drop_start),
            row(event.trough_index),
            row(event.recovery_index) if event.recovery_index is not None else None,
            row(event.end_index),
            event.kind,
            event.end_at_observation_boundary,
        )

    return [convert(event) for event in local_events]


def _fit_linear(
    x: np.ndarray,
    y: np.ndarray,
    *,
    slope_constraint: str,
    min_slope: float = 0.0,
) -> tuple[np.ndarray, float, float]:
    if x.size < 2:
        raise ProcessingError("직선·회귀 방법은 관측점 2점 이상이 필요합니다.")
    center = float(np.mean(x))
    scale = float(np.max(np.abs(x - center)))
    if not np.isfinite(scale) or scale <= 0:
        raise ProcessingError("선택 구간의 변형률이 퇴화해 직선을 계산할 수 없습니다.")
    z = (x - center) / scale

    def weighted_fit(weights: np.ndarray) -> tuple[float, float]:
        total = float(np.sum(weights))
        if not np.isfinite(total) or total <= 0:
            raise ProcessingError("회귀 가중치 합이 유효하지 않습니다.")
        z_bar = float(np.sum(weights * z) / total)
        y_bar = float(np.sum(weights * y) / total)
        denominator = float(np.sum(weights * (z - z_bar) ** 2))
        if not np.isfinite(denominator) or denominator <= np.finfo(float).eps:
            raise ProcessingError("선택 구간의 변형률이 퇴화해 회귀할 수 없습니다.")
        slope = float(np.sum(weights * (z - z_bar) * (y - y_bar)) / denominator)
        if slope_constraint == "nondecreasing":
            slope = max(min_slope * scale, slope)
        elif slope_constraint != "none":
            raise ProcessingError("slope_constraint 는 none 또는 nondecreasing 이어야 합니다.")
        intercept = y_bar - slope * z_bar
        return slope, intercept

    if slope_constraint not in ("none", "nondecreasing"):
        raise ProcessingError("slope_constraint 는 none 또는 nondecreasing 이어야 합니다.")
    slope, intercept = weighted_fit(np.ones(x.size, dtype=np.float64))
    fitted = intercept + slope * z
    return fitted, slope / scale, intercept - slope * center / scale


def _fit_endpoint_line(
    x: np.ndarray,
    y: np.ndarray,
    *,
    slope_constraint: str,
    min_slope: float = 0.0,
) -> tuple[np.ndarray, float, float]:
    if x.size < 2:
        raise ProcessingError("양끝 직선은 관측점 2점 이상이 필요합니다.")
    delta_x = float(x[-1] - x[0])
    if not np.isfinite(delta_x) or delta_x <= 0:
        raise ProcessingError("양끝 직선을 계산하려면 변형률이 엄격히 증가해야 합니다.")
    slope = float((y[-1] - y[0]) / delta_x)
    if slope_constraint == "nondecreasing" and slope < min_slope:
        raise ProcessingError(
            "slope_constraint='nondecreasing' 에서 양끝 직선의 기울기가 "
            f"min_slope({min_slope})보다 작아 양끝 직선을 만들 수 없습니다."
        )
    if slope_constraint not in ("none", "nondecreasing"):
        raise ProcessingError("slope_constraint 는 none 또는 nondecreasing 이어야 합니다.")
    fitted = y[0] + slope * (x - x[0])
    return fitted, slope, float(y[0] - slope * x[0])


def _fit_robust_linear(
    x: np.ndarray,
    y: np.ndarray,
    *,
    slope_constraint: str,
    min_slope: float = 0.0,
) -> tuple[np.ndarray, float, float]:
    if x.size < 2:
        raise ProcessingError("Huber 회귀는 관측점 2점 이상이 필요합니다.")
    center = float(np.mean(x))
    scale_x = float(np.max(np.abs(x - center)))
    if not np.isfinite(scale_x) or scale_x <= 0:
        raise ProcessingError("선택 구간의 변형률이 퇴화해 Huber 회귀를 계산할 수 없습니다.")
    z = (x - center) / scale_x
    if slope_constraint not in ("none", "nondecreasing"):
        raise ProcessingError("slope_constraint 는 none 또는 nondecreasing 이어야 합니다.")

    def weighted_fit(weights: np.ndarray, *, constrained: bool) -> tuple[float, float]:
        total = float(np.sum(weights))
        if not np.isfinite(total) or total <= 0:
            raise ProcessingError("Huber 회귀 가중치 합이 유효하지 않습니다.")
        z_bar = float(np.sum(weights * z) / total)
        y_bar = float(np.sum(weights * y) / total)
        denominator = float(np.sum(weights * (z - z_bar) ** 2))
        if not np.isfinite(denominator) or denominator <= np.finfo(float).eps:
            raise ProcessingError(
                "선택 구간의 변형률이 퇴화해 Huber 회귀를 계산할 수 없습니다."
            )
        slope = float(np.sum(weights * (z - z_bar) * (y - y_bar)) / denominator)
        if constrained and slope_constraint == "nondecreasing":
            slope = max(min_slope * scale_x, slope)
        return slope, y_bar - slope * z_bar

    ones = np.ones(x.size, dtype=np.float64)
    # Huber scale is fixed from unconstrained OLS residuals, even when the final
    # IRLS solve carries a nondecreasing lower bound.
    slope, intercept = weighted_fit(ones, constrained=False)
    initial = intercept + slope * z
    residual = y - initial
    mad = float(np.median(np.abs(residual - np.median(residual))))
    max_abs = float(np.max(np.abs(y))) if y.size else 0.0
    huber_scale = max(1.4826 * mad, 1e-6 * max_abs, 1.0)
    delta = 1.345 * huber_scale
    previous = initial
    converged = False
    for _iteration in range(100):
        residual = y - previous
        absolute = np.abs(residual)
        weights = np.ones_like(absolute)
        outside = absolute > delta
        weights[outside] = delta / absolute[outside]
        slope, intercept = weighted_fit(weights, constrained=True)
        fitted = intercept + slope * z
        if not np.all(np.isfinite(fitted)):
            raise ProcessingError("Huber 회귀 결과가 유한하지 않습니다.")
        change = float(np.max(np.abs(fitted - previous)))
        fit_scale = max(1.0, float(np.max(np.abs(fitted))), float(np.max(np.abs(y))))
        previous = fitted
        if change <= 1e-10 * fit_scale:
            converged = True
            break
    if not converged:
        raise ProcessingError("Huber 회귀가 100회 반복 안에 수렴하지 않았습니다.")
    return previous, slope / scale_x, intercept - slope * center / scale_x


def _fit_segment(
    method: str,
    x: np.ndarray,
    y: np.ndarray,
    *,
    min_slope: float,
    slope_constraint: str,
) -> tuple[np.ndarray, float, float]:
    if x.size < 2:
        raise ProcessingError("선택 계산 구간은 관측점 2점 이상이어야 합니다.")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ProcessingError("선택 계산 구간에 유한하지 않은 값이 있습니다.")
    if method in _MONOTONE_SCOPED_METHODS:
        transformed = y - min_slope * x
        if method == "envelope":
            fitted_transformed = np.maximum.accumulate(transformed)
        elif method == "isotonic":
            fitted_transformed = _isotonic(transformed)
        else:
            fitted_transformed = np.minimum.accumulate(transformed[::-1])[::-1]
        fitted = fitted_transformed + min_slope * x
    elif method == "median_plateau":
        transformed = y - min_slope * x
        fitted = np.full_like(y, float(np.median(transformed)), dtype=np.float64)
        fitted += min_slope * x
    elif method == "linear":
        if min_slope > 0 and slope_constraint == "none":
            raise ProcessingError(
                "linear에서 min_slope>0 을 쓰려면 slope_constraint='nondecreasing'을 "
                "지정해야 합니다."
            )
        fitted, _slope, _intercept = _fit_endpoint_line(
            x, y, slope_constraint=slope_constraint, min_slope=min_slope
        )
    elif method == "least_squares":
        if min_slope > 0 and slope_constraint == "none":
            raise ProcessingError(
                "least_squares에서 min_slope>0 을 쓰려면 "
                "slope_constraint='nondecreasing'을 지정해야 합니다."
            )
        fitted, _slope, _intercept = _fit_linear(
            x, y, slope_constraint=slope_constraint, min_slope=min_slope
        )
    elif method == "robust_linear":
        if min_slope > 0 and slope_constraint == "none":
            raise ProcessingError(
                "robust_linear에서 min_slope>0 을 쓰려면 "
                "slope_constraint='nondecreasing'을 지정해야 합니다."
            )
        fitted, _slope, _intercept = _fit_robust_linear(
            x, y, slope_constraint=slope_constraint, min_slope=min_slope
        )
    else:
        raise ProcessingError(f"범위 처리에서 지원하지 않는 방법입니다: {method}")
    if not np.all(np.isfinite(fitted)):
        raise ProcessingError(f"{method} 계산 결과가 유한하지 않습니다.")
    residual = y - fitted
    total = float(np.sum((y - float(np.mean(y))) ** 2))
    error = float(np.sum(residual**2))
    score = 1.0 if total == 0 and error == 0 else 0.0 if total == 0 else 1.0 - error / total
    rmse = float(np.sqrt(np.mean(residual**2)))
    if not np.isfinite(score) or not np.isfinite(rmse):
        raise ProcessingError(f"{method} 계산 점수가 유한하지 않습니다.")
    return fitted, score, rmse


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _expand_event_intervals(
    intervals: list[tuple[int, int]],
    *,
    domain_start: int,
    domain_end: int,
    strain: np.ndarray,
    original: np.ndarray,
    method: str,
    min_slope: float,
    slope_constraint: str,
    protected_intervals: list[tuple[int, int]] | None = None,
) -> tuple[list[tuple[int, int]], list[str]]:
    current = _merge_intervals(intervals)
    notes: list[str] = []
    protected = _merge_intervals(protected_intervals or [])

    def protected_row(row: int) -> bool:
        return any(start <= row <= end for start, end in protected)

    while True:
        candidate = current[:]
        probe = original.copy()
        for start, end in current:
            probe[start : end + 1], _score, _rmse = _fit_segment(
                method,
                strain[start : end + 1],
                original[start : end + 1],
                min_slope=min_slope,
                slope_constraint=slope_constraint,
            )
        changed = False
        for start, end in current:
            if start > domain_start:
                required = probe[start - 1] + min_slope * float(
                    strain[start] - strain[start - 1]
                )
                if probe[start] < required:
                    if protected_row(start - 1):
                        raise ProcessingError(
                            "terminal_action='keep' 보호 행 때문에 events 단조 방법의 "
                            "왼쪽 경계를 연결할 수 없습니다."
                        )
                    else:
                        candidate.append((start - 1, end))
                        changed = True
            elif start > 0:
                required = probe[start - 1] + min_slope * float(
                    strain[start] - strain[start - 1]
                )
                if probe[start] < required:
                    raise ProcessingError(
                        "events 단조 방법의 왼쪽 경계 연결에 행을 더 넣어야 하지만 "
                        "선택 domain 밖입니다."
                    )
            if end < domain_end:
                required = probe[end] + min_slope * float(strain[end + 1] - strain[end])
                if probe[end + 1] < required:
                    if protected_row(end + 1):
                        if probe[end] == original[end] and probe[end + 1] == original[end + 1]:
                            note = (
                                "terminal_action='keep' 보호 말단에 닿는 기존 하강을 그대로 "
                                f"보존했습니다: index {end}~{end + 1}, "
                                f"{float(original[end]):.6g}→"
                                f"{float(original[end + 1]):.6g} Pa."
                            )
                            if note not in notes:
                                notes.append(note)
                        else:
                            raise ProcessingError(
                                "terminal_action='keep' 보호 행 때문에 events 단조 방법의 "
                                "오른쪽 경계를 연결할 수 없습니다."
                            )
                    else:
                        candidate.append((start, end + 1))
                        changed = True
            elif end + 1 < len(strain):
                required = probe[end] + min_slope * float(strain[end + 1] - strain[end])
                if probe[end + 1] < required:
                    raise ProcessingError(
                        "events 단조 방법의 오른쪽 경계 연결에 행을 더 넣어야 하지만 "
                        "선택 domain 밖입니다."
                    )
        merged = _merge_intervals(candidate)
        if not changed and merged == current:
            break
        current = merged
    if current != _merge_intervals(intervals):
        notes.append(
            "events 단조 방법의 경계 급락을 없애려고 선택 domain 안에서 영향 구간을 "
            f"최소 확장했습니다: {current}."
        )
    return current, notes


def _boundary_metrics(
    original: np.ndarray, fixed: np.ndarray, intervals: list[tuple[int, int]]
) -> tuple[int, float]:
    count = 0
    maximum = 0.0
    for start, end in intervals:
        if start > 0 and fixed[start] != original[start]:
            jump = abs(
                (fixed[start] - fixed[start - 1]) - (original[start] - original[start - 1])
            )
            if jump > 0:
                count += 1
                maximum = max(maximum, float(jump))
        if end + 1 < len(original) and fixed[end] != original[end]:
            jump = abs((fixed[end + 1] - fixed[end]) - (original[end + 1] - original[end]))
            if jump > 0:
                count += 1
                maximum = max(maximum, float(jump))
    return count, maximum


def _fit_interval_statistics(
    original: np.ndarray, fixed: np.ndarray, intervals: list[tuple[int, int]]
) -> tuple[float, float]:
    observed: list[np.ndarray] = []
    predicted: list[np.ndarray] = []
    for start, end in intervals:
        observed.append(original[start : end + 1])
        predicted.append(fixed[start : end + 1])
    if not observed:
        return 1.0, 0.0
    y = np.concatenate(observed)
    fit = np.concatenate(predicted)
    residual = y - fit
    total = float(np.sum((y - float(np.mean(y))) ** 2))
    error = float(np.sum(residual**2))
    score = 1.0 if total == 0 and error == 0 else 0.0 if total == 0 else 1.0 - error / total
    rmse = float(np.sqrt(np.mean(residual**2)))
    if not np.isfinite(score) or not np.isfinite(rmse):
        raise ProcessingError("범위 처리 점수가 유한하지 않습니다.")
    return score, rmse


def _scoped_result(
    frame: Frame,
    strain: np.ndarray,
    stress: np.ndarray,
    strain_key: str,
    stress_key: str,
    *,
    scope: str,
    method: str,
    domain: np.ndarray,
    events: list[DropEvent],
    options: dict[str, Any],
    threshold: float,
    min_reference_fraction: float,
    min_slope: float,
    requested_start: float | None,
    requested_end: float | None,
    auto_profile: _AutoYieldProfile | None = None,
) -> StepResult:
    slope_constraint = str(options.get("slope_constraint") or "none")
    terminal_action = str(options.get("terminal_action") or "hold")
    if terminal_action not in ("hold", "keep"):
        raise ProcessingError("terminal_action 은 hold 또는 keep 이어야 합니다.")
    if method in _REGRESSION_METHODS and slope_constraint not in ("none", "nondecreasing"):
        raise ProcessingError("slope_constraint 는 none 또는 nondecreasing 이어야 합니다.")
    if method not in _REGRESSION_METHODS:
        slope_constraint = "none"

    notes = [_actual_domain_note(domain, strain, scope, requested_start, requested_end)]
    notes.extend(
        _event_notes(events, domain, strain, stress, threshold, min_reference_fraction)
    )
    scalars = _event_scalars(events)

    if method == "keep":
        notes.append("keep: 원본 모든 채널을 그대로 두고 선택 domain의 사건만 진단했습니다.")
        scalars.extend(
            [
                Scalar("yield_drop_points", "손댄 점 수", 0.0, "1"),
                Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                Scalar(
                    "remaining_drop_count",
                    "남은 하강 수",
                    float(np.count_nonzero(np.diff(stress[domain]) < 0)),
                    "1",
                ),
            ]
        )
        return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))

    terminal = [event for event in events if event.kind == "terminal_unrecovered"]
    if scope == "events" and terminal and terminal_action == "hold" and method != "cut":
        detail = ", ".join(str(event.peak_index) for event in terminal)
        raise ProcessingError(
            "events 범위에 terminal_unrecovered 사건이 있어 hold 합니다"
            f"(peak 원행 index: {detail}). terminal_action='keep' 를 선택하면 "
            "미회복 구간을 원본으로 보존할 수 있습니다."
        )

    if method == "cut":
        if not events:
            notes.append("선택 domain 안에 검출 사건이 없어 cut 하지 않았습니다.")
            scalars.extend(
                [
                    Scalar("yield_drop_points", "손댄 점 수", 0.0, "1"),
                    Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                    Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                    Scalar(
                        "remaining_drop_count",
                        "남은 하강 수",
                        float(np.count_nonzero(np.diff(stress[domain]) < 0)),
                        "1",
                    ),
                ]
            )
            return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))
        first_peak = int(events[0].peak_index)
        kept = first_peak + 1
        removed = len(stress) - kept
        notes.append(
            f"선택 domain의 첫 검출 peak 원행 index {first_peak}까지 모든 채널을 보존하고 "
            f"뒤의 {removed}점을 잘랐습니다."
        )
        scalars.append(Scalar("yield_drop_points", "손댄 점 수", float(removed), "1"))
        return StepResult(
            frame.select(np.arange(kept)), notes=tuple(notes), scalars=tuple(scalars)
        )

    intervals: list[tuple[int, int]]
    if scope == "events":
        intervals = []
        for event in events:
            if event.kind == "terminal_unrecovered" and terminal_action == "keep":
                continue
            intervals.append((event.peak_index, event.end_index))
        intervals = _merge_intervals(intervals)
        if not intervals:
            notes.append("편집할 회복 사건이 없어 원본을 그대로 둡니다.")
            scalars.append(Scalar("yield_drop_points", "손댄 점 수", 0.0, "1"))
            return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))
    else:
        intervals = [(int(domain[0]), int(domain[-1]))]

    auto_fit: AutoYieldFitResult | None = None
    if auto_profile is not None and auto_profile.anchor_policy is not None:
        terminal_peaks = [event.peak_index for event in terminal]
        search_end = min(terminal_peaks) if terminal_peaks else len(stress) - 1
        candidate_window, _candidate_count, _rising_count = _auto_window(
            strain[: search_end + 1], stress[: search_end + 1]
        )
        if candidate_window is not None:
            preserve_boundary = int(
                np.searchsorted(strain[: search_end + 1], candidate_window[1], side="right")
                - 1
            )
            preserve_boundary_reason = "_auto_window candidate end row"
        else:
            prefix = stress[: search_end + 1]
            peak = int(np.argmax(prefix))
            initial_max = float(prefix[peak])
            hits = np.flatnonzero(prefix[: peak + 1] >= initial_max * 0.4)
            preserve_boundary = int(hits[0]) if hits.size else peak
            preserve_boundary_reason = (
                "candidate unavailable; conservative first 40% of pre-peak rise"
            )
        auto_cores = [
            (event.peak_index, event.end_index)
            for event in events
            if event.kind in ("full_recovery", "partial_recovery")
        ]
        protected = [
            (event.peak_index, event.end_index)
            for event in terminal
            if terminal_action == "keep"
        ]
        try:
            auto_fit = fit_event_cores(
                strain,
                stress,
                auto_cores,
                protected,
                preserve_boundary,
                method,
                preserve_boundary_reason=preserve_boundary_reason,
            )
        except AutoYieldFitError as exc:
            raise ProcessingError(f"자동 앵커 처리 보류: {exc}") from exc
        fixed = auto_fit.values.copy()
        intervals = [(region.left_anchor, region.right_anchor) for region in auto_fit.regions]
        protected_note = (
            ", ".join(f"{start}~{end}" for start, end in auto_fit.protected_intervals)
            or "없음"
        )
        notes.append(
            f"자동 앵커 정책 {auto_profile.anchor_policy}; 보존 경계 index "
            f"{auto_fit.preserve_boundary} ({auto_fit.preserve_boundary_reason}); "
            f"보호 말단 구간 {protected_note}."
        )
        for region in auto_fit.regions:
            start = region.core_start
            end = region.core_end
            left = region.left_anchor
            right = region.right_anchor
            unconstrained = (
                "없음"
                if region.unconstrained_endpoints is None
                else f"{region.unconstrained_endpoints[0]:.6g}~"
                f"{region.unconstrained_endpoints[1]:.6g} Pa"
            )
            huber_delta = (
                "없음" if region.huber_delta is None else f"{region.huber_delta:.6g} Pa"
            )
            notes.append(
                f"자동 적합 core index {start}~{end}, 실제 앵커 index {left}~{right} "
                f"(변형률 {float(strain[left]):.6g}~{float(strain[right]):.6g}); "
                f"앵커 응력 {float(stress[left]):.6g}~{float(stress[right]):.6g} Pa, "
                f"c0={region.c0 if region.c0 is not None else '없음'}, "
                f"왼쪽 앵커 탐색 기준 {region.target_stress:.6g} Pa, "
                f"비제약 끝값 {unconstrained}, 제약 끝값 "
                f"{region.constrained_endpoints[0]:.6g}~"
                f"{region.constrained_endpoints[1]:.6g} Pa, "
                f"Huber delta={huber_delta}, 제약 적용={region.constraint_applied}; "
                f"접합 구간 {left}~{start} 및 {end}~{right}, "
                f"영향 행 폭 {right - left + 1}, core 대비 확장 폭 "
                f"{right - left + 1 - (end - start + 1)}, "
                f"코어 R²={region.fit_r_squared:.6g}, RMSE={region.fit_rmse:.6g} Pa, "
                f"최대 변경량={region.max_abs_distortion:.6g} Pa."
            )
    elif method in _MONOTONE_SCOPED_METHODS and scope == "events":
        protected_intervals = [
            (event.peak_index, event.end_index)
            for event in terminal
            if terminal_action == "keep"
        ]
        intervals, expansion_notes = _expand_event_intervals(
            intervals,
            domain_start=int(domain[0]),
            domain_end=int(domain[-1]),
            strain=strain,
            original=stress,
            method=method,
            min_slope=min_slope,
            slope_constraint=slope_constraint,
            protected_intervals=protected_intervals,
        )
        notes.extend(expansion_notes)

    if auto_fit is None:
        fixed = stress.astype(np.float64).copy()
        for start, end in intervals:
            fixed[start : end + 1], _score, _rmse = _fit_segment(
                method,
                strain[start : end + 1],
                stress[start : end + 1],
                min_slope=min_slope,
                slope_constraint=slope_constraint,
            )

    if scope == "events" and terminal_action == "keep":
        for event in terminal:
            protected_start, protected_end = event.peak_index, event.end_index
            if np.any(
                fixed[protected_start : protected_end + 1]
                != stress[protected_start : protected_end + 1]
            ):
                raise ProcessingError(
                    "terminal_action='keep' 보호 영역과 회복 영향 구간이 겹쳐 "
                    "미회복 원행을 보존할 수 없습니다. 범위를 다시 지정하세요."
                )

    changed = int(np.count_nonzero(fixed != stress))
    boundary_count, boundary_max = _boundary_metrics(stress, fixed, intervals)
    score, rmse = (
        (auto_fit.fit_r_squared, auto_fit.fit_rmse)
        if auto_fit is not None
        else _fit_interval_statistics(stress, fixed, intervals)
    )
    remaining = int(np.count_nonzero(np.diff(fixed[domain]) < 0))
    method_note = {
        "envelope": "선택 구간 prefix envelope",
        "isotonic": "선택 구간 PAVA 단조 회귀",
        "lower_envelope": "선택 구간 suffix lower envelope",
        "median_plateau": "선택 구간 median plateau",
        "linear": "선택 구간 양끝 직선",
        "least_squares": "선택 구간 OLS 직선",
        "robust_linear": "선택 구간 고정 scale Huber IRLS 직선",
    }.get(method, method)
    notes.append(
        f"{method_note}을 적용했습니다. 영향 index {intervals}, {changed}점을 바꿨습니다."
    )
    if method == "median_plateau" and min_slope > 0:
        notes.append(
            "median_plateau는 y-min_slope*x의 중앙값을 복원했으므로 양수 min_slope에서는 "
            "완전한 수평 평탄부가 아닙니다."
        )
    if method == "robust_linear" and any(end - start + 1 == 2 for start, end in intervals):
        notes.append(
            "2점 robust_linear 구간은 제약이 없을 때 끝점 직선과 동일하지만, "
            "기울기 제약 시 달라질 수 있으며 이상점을 분별할 수 없습니다."
        )
    if auto_fit is not None:
        notes.append(
            "관측 앵커와 보호 말단은 원본 값 그대로 두고, 자동 접합 구간에서만 "
            "비감소 모델 근사를 적용했습니다."
        )
    elif method in ("median_plateau", "linear", "least_squares", "robust_linear"):
        notes.append(
            f"{method}은 양끝 연속을 수치적으로 보장하지 않습니다: 추가 경계 jump "
            f"{boundary_count}개, 최대 {boundary_max:.6g} Pa, 남은 하강 {remaining}개."
        )
    elif method in _MONOTONE_SCOPED_METHODS:
        notes.append(f"단조 계산 뒤 남은 선택 domain 내부 하강은 {remaining}개입니다.")
    if method in _REGRESSION_METHODS:
        notes.append(
            "slope_constraint='none' 이면 하강 기울기를 허용하며, "
            f"현재 선택값은 {slope_constraint} 입니다."
        )

    scalars.extend(
        [
            Scalar("yield_drop_points", "손댄 점 수", float(changed), "1"),
            Scalar("boundary_jump_count", "경계 jump 수", float(boundary_count), "1"),
            Scalar("boundary_jump_max", "최대 경계 jump", boundary_max, "Pa"),
            Scalar("remaining_drop_count", "남은 하강 수", float(remaining), "1"),
            Scalar("fit_r_squared", "처리 구간 R²", score, "1"),
            Scalar("fit_rmse", "처리 구간 RMSE", rmse, "Pa"),
        ]
    )
    return StepResult(
        frame.with_columns({stress_key: fixed}, {}),
        notes=tuple(notes),
        scalars=tuple(scalars),
    )


@register(
    id="tensile.yield_drop",
    kind="processing",
    label="공칭 하강 처리",
    params=(
        ParamSpec(
            name="scope",
            label="계산 범위",
            type="choice",
            default="full",
            choices=YIELD_DROP_SCOPES,
            choice_labels={"full": "전체 관측", "range": "명시 구간", "events": "검출 사건"},
            choice_help={
                "full": "기존 전체 관측 계약으로 계산합니다.",
                "range": "range_start~range_end 안의 원행 구간만 계산하고 밖은 그대로 둡니다.",
                "events": "원행 순서에서 급락과 회복 사건을 검출한 영향 구간만 계산합니다.",
            },
            when={"method": _YIELD_DROP_MANUAL_METHODS},
        ),
        ParamSpec(
            name="method",
            label="방법",
            type="choice",
            default="envelope",
            choices=YIELD_DROP_METHODS,
            choice_labels={
                "envelope": "단조 포락선",
                "isotonic": "단조 회귀",
                "lower_yield": "선택 구간 평탄화 (모델 근사)",
                "cut": "첫 검출 봉우리에서 자르기",
                "keep": "그대로 두고 재기만",
                "lower_envelope": "뒤쪽 최솟값 포락선",
                **{profile.id: profile.label for profile in AUTO_YIELD_PROFILES},
                "median_plateau": "중앙값 평탄부",
                "linear": "양끝 직선",
                "least_squares": "최소제곱 직선",
                "robust_linear": "Huber 강건 직선",
            },
            choice_help={
                "envelope": "prefix running maximum으로 선택 구간의 하강을 올립니다.",
                "isotonic": "PAVA 단조 비감소 최소제곱 회귀를 적용합니다.",
                "lower_yield": "명시한 공칭변형률 구간과 목표 응력으로 모델 근사합니다.",
                "cut": "선택 범위에서 첫 검출 peak까지 모든 채널을 보존하고 뒤를 자릅니다. "
                "range는 검출 범위이며 삭제 보호 범위가 아닙니다.",
                "keep": "곡선은 안 건드리고 선택 범위의 사건과 지표만 기록합니다.",
                "lower_envelope": (
                    "suffix running minimum으로 선택 구간의 하강 아래 경계를 계산합니다."
                ),
                **_AUTO_METHOD_HELP,
                "median_plateau": "선택 구간 응력의 중앙값으로 평탄부를 만듭니다.",
                "linear": "선택 구간 양끝을 잇는 직선을 계산합니다.",
                "least_squares": "선택 구간의 OLS 직선을 계산합니다.",
                "robust_linear": "고정된 Huber scale의 IRLS로 직선을 계산합니다.",
            },
        ),
        ParamSpec(
            name="threshold",
            label="하강 문턱",
            type="float",
            default=YIELD_DROP_THRESHOLD,
            unit="1",
            help="양수인 선행 최댓값에 견준 비율입니다. 이보다 작은 하강은 기존 계약에서 "
            "응력 하강으로 치지 않습니다(기본 0.5%).",
            when={"method": _YIELD_DROP_MANUAL_METHODS},
        ),
        ParamSpec(
            name="recovery_threshold",
            label="회복 문턱",
            type="float",
            default=None,
            unit="1",
            when={"scope": ("range", "events"), "method": _YIELD_DROP_MANUAL_METHODS},
            help=(
                "급락 최저점에서 의미 있는 상승으로 볼 비율입니다. 비우면 threshold를 씁니다."
            ),
        ),
        ParamSpec(
            name="min_reference_fraction",
            label="최소 기준 봉우리 비율",
            type="float",
            default=0.05,
            unit="1",
            when={"scope": ("range", "events"), "method": _YIELD_DROP_MANUAL_METHODS},
            help="선택 domain의 양의 관측응력 최댓값에 대한 최소 기준 비율입니다.",
        ),
        ParamSpec(
            name="terminal_action",
            label="말단 미회복",
            type="choice",
            default="hold",
            choices=("hold", "keep"),
            choice_labels={"hold": "보류", "keep": "원본 보존"},
            choice_help={
                "hold": (
                    "편집 방법에서 events의 terminal_unrecovered가 있으면 "
                    "전체 처리를 보류합니다."
                ),
                "keep": (
                    "회복 사건만 처리하고 미회복 영역은 원본으로 보존합니다. "
                    "cut은 선택한 prefix를 자릅니다."
                ),
            },
            when={"scope": ("events",), "method": _YIELD_DROP_MANUAL_METHODS},
        ),
        ParamSpec(
            name="slope_constraint",
            label="직선 기울기",
            type="choice",
            default="none",
            choices=("none", "nondecreasing"),
            choice_labels={"none": "제약 없음", "nondecreasing": "비감소"},
            choice_help={
                "none": "하강 기울기도 허용합니다. 결과가 내려갈 수 있음을 notes에 남깁니다.",
                "nondecreasing": "OLS/Huber 기울기를 0 이상으로 직접 제약합니다.",
            },
            when={"method": ("linear", "least_squares", "robust_linear")},
        ),
        ParamSpec(
            name="min_slope",
            label="최소 기울기",
            type="float",
            default=0.0,
            unit="Pa",
            help="단조 방법에서 y-min_slope*x를 먼저 계산해 이 기울기 이상을 보장합니다.",
            when={"method": _YIELD_DROP_MANUAL_METHODS},
        ),
        ParamSpec(
            name="range_start",
            label="범위 시작 변형률",
            type="float",
            unit="1",
            dimension="strain",
            required=False,
            when={"scope": ("range", "events"), "method": _YIELD_DROP_MANUAL_METHODS},
            help="명시 범위의 시작. 실제 선택 원행 범위는 notes에 남습니다.",
        ),
        ParamSpec(
            name="range_end",
            label="범위 끝 변형률",
            type="float",
            unit="1",
            dimension="strain",
            required=False,
            when={"scope": ("range", "events"), "method": _YIELD_DROP_MANUAL_METHODS},
            help="명시 범위의 끝. 실제 선택 원행 범위는 notes에 남습니다.",
        ),
        ParamSpec(
            name="plateau_start",
            label="평탄화 시작 변형률",
            type="float",
            unit="1",
            dimension="strain",
            required=True,
            when={"method": ("lower_yield",)},
            help="선택 구간 평탄화의 시작. 관측 공칭변형률 범위 안에서 직접 지정합니다.",
        ),
        ParamSpec(
            name="plateau_end",
            label="평탄화 끝 변형률",
            type="float",
            unit="1",
            dimension="strain",
            required=True,
            when={"method": ("lower_yield",)},
            help="선택 구간 평탄화의 끝. 시작보다 크고 관측 범위 안이어야 합니다.",
        ),
        ParamSpec(
            name="plateau_stress",
            label="평탄화 목표 응력",
            type="float",
            unit="Pa",
            required=True,
            when={"method": ("lower_yield",)},
            help="선택 구간의 원관측 응력을 바꿀 목표 응력입니다. 양수로 직접 지정합니다.",
        ),
        ParamSpec(name="strain", label="변형률 열", type="str", role="column", default=STRAIN),
        ParamSpec(name="stress", label="응력 열", type="str", role="column", default=STRESS),
    ),
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    makes_values=(
        Produced(
            key="yield_drop_max",
            label="최대 하강 폭",
            si_unit="Pa",
            help="직전 최댓값에서 가장 많이 내려간 관측 응력 폭.",
        ),
        Produced(key="yield_drop_points", label="손댄 점 수", si_unit="1"),
        Produced(
            key="event_count",
            label="검출 사건 수",
            si_unit="1",
            help="원행 순서에서 threshold를 넘은 급락 사건 수.",
        ),
        Produced(key="recovered_count", label="완전 회복 사건 수", si_unit="1"),
        Produced(key="partial_count", label="부분 회복 사건 수", si_unit="1"),
        Produced(
            key="open_partial_count",
            label="관측 종료 열린 부분 회복 사건 수",
            si_unit="1",
            help="관측 종료까지 원봉우리로 복귀하지 않은 부분 회복 사건 수입니다.",
        ),
        Produced(key="unrecovered_count", label="미회복 사건 수", si_unit="1"),
        Produced(key="boundary_jump_count", label="경계 jump 수", si_unit="1"),
        Produced(key="boundary_jump_max", label="최대 경계 jump", si_unit="Pa"),
        Produced(key="remaining_drop_count", label="남은 하강 수", si_unit="1"),
        Produced(
            key="auto_edit_applied",
            label="자동 근사 편집 적용",
            si_unit="1",
            help="자동 프로필에서 원응력 값이 실제로 바뀌었으면 1입니다.",
        ),
        Produced(
            key="auto_review_required",
            label="자동 근사 검토 필요",
            si_unit="1",
            help=(
                "미회복 말단 또는 관측 종료까지 열린 부분 회복 사건이 있어 "
                "사람이 검토해야 하면 1입니다."
            ),
        ),
        Produced(
            key="auto_terminal_only",
            label="자동 근사 말단 사건만",
            si_unit="1",
            help="회복 사건 없이 미회복 말단 사건만 검출되면 1입니다.",
        ),
        Produced(
            key="fit_r_squared",
            label="처리 구간 R²",
            si_unit="1",
            help="선택 방법의 수치 적합 점수이며 방법 순위나 물리 승인 지표가 아닙니다.",
        ),
        Produced(
            key="fit_rmse",
            label="처리 구간 RMSE",
            si_unit="Pa",
            help="선택 방법의 수치 잔차이며 방법 순위나 물리 승인 지표가 아닙니다.",
        ),
        Produced(
            key="model_plateau_stress",
            label="모델 평탄 응력",
            si_unit="Pa",
            help="선택 구간 평탄화에 입력한 목표 응력. 규격 하항복강도 측정값이 아닙니다.",
        ),
        Produced(
            key="model_plateau_start",
            label="모델 평탄 시작 변형률",
            si_unit="1",
            help="선택 구간에서 실제로 선택된 첫 관측 변형률입니다.",
        ),
        Produced(
            key="model_plateau_end",
            label="모델 평탄 끝 변형률",
            si_unit="1",
            help="선택 구간에서 실제로 선택된 마지막 관측 변형률입니다.",
        ),
    ),
    order=35,
    version="6",
)
def yield_drop(frame: Frame, options: dict[str, Any]) -> StepResult:
    """공칭 응력의 하강과 회복을 선택한 방법으로 진단·처리한다.

    전체 scope와 기존 방법의 기본값은 유지한다. range/events는 사용자가 선택한
    원행 영역을 계산 대상으로 삼으며, 사건 검출은 변형률 정렬이나 중복 제거 없이
    관측 행 순서에서 수행한다. 검출만으로 하강 원인을 판정하지 않는다.
    """
    requested_method = options.get("method")
    profile = (
        _AUTO_YIELD_PROFILE_BY_ID.get(requested_method)
        if isinstance(requested_method, str)
        else None
    )
    if profile is not None:
        strain_key = str(options.get("strain") or STRAIN)
        stress_key = str(options.get("stress") or STRESS)
        fixed_options: dict[str, Any] = {
            "scope": "events",
            "method": profile.method,
            "threshold": _AUTO_PROFILE_THRESHOLD,
            "recovery_threshold": _AUTO_PROFILE_RECOVERY_THRESHOLD,
            "min_reference_fraction": _AUTO_PROFILE_MIN_REFERENCE_FRACTION,
            "min_slope": _AUTO_PROFILE_MIN_SLOPE,
            "terminal_action": "keep",
            "strain": strain_key,
            "stress": stress_key,
        }
        if profile.slope_constraint is not None:
            fixed_options["slope_constraint"] = profile.slope_constraint
        if profile.anchor_policy is not None:
            fixed_options["anchor_policy"] = profile.anchor_policy
        strain_raw, stress_raw, strain_key, stress_key = _pair(frame, fixed_options)
        strain, _stress = _finite_pair(strain_raw, stress_raw, strain_key, stress_key)
        if np.any(np.diff(strain) <= 0):
            raise ProcessingError(
                f"자동 처리 프로필 '{profile.label}'은 '{strain_key}'의 원행 변형률이 "
                "엄격히 증가해야 "
                "합니다. 원래 측정 순서를 확인하세요. 자동 전역 정렬은 하지 않습니다."
            )

        internal_options = dict(fixed_options)
        if profile.anchor_policy is not None:
            internal_options["_auto_profile"] = profile
        result = yield_drop(frame, internal_options)
        result_values = {item.key: item.value for item in result.scalars}
        event_count = result_values.get("event_count", 0.0)
        full_count = result_values.get("recovered_count", 0.0)
        partial_count = result_values.get("partial_count", 0.0)
        open_partial_count = result_values.get("open_partial_count", 0.0)
        terminal_count = result_values.get("unrecovered_count", 0.0)
        changed_points = result_values.get("yield_drop_points", 0.0)
        terminal_only = bool(
            event_count > 0 and terminal_count > 0 and full_count + partial_count == 0
        )
        has_terminal = terminal_count > 0
        review_required = has_terminal or open_partial_count > 0
        edit_applied = changed_points > 0
        ignored_defaults: dict[str, Any] = {
            "scope": "events",
            "method": profile.id,
            "threshold": _AUTO_PROFILE_THRESHOLD,
            "recovery_threshold": _AUTO_PROFILE_RECOVERY_THRESHOLD,
            "min_reference_fraction": _AUTO_PROFILE_MIN_REFERENCE_FRACTION,
            "min_slope": _AUTO_PROFILE_MIN_SLOPE,
            "terminal_action": "keep",
            "slope_constraint": profile.slope_constraint or "none",
            "anchor_policy": profile.anchor_policy,
            "range_start": None,
            "range_end": None,
            "plateau_start": None,
            "plateau_end": None,
            "plateau_stress": None,
        }
        ignored = [
            key
            for key, expected in ignored_defaults.items()
            if key in options and not _option_value_matches(options[key], expected)
        ]
        notes = list(result.notes)
        if ignored:
            notes.append(
                f"{profile.id} 고정 규칙이 적용되어 전달된 입력 "
                f"{', '.join(ignored)}은 무시했습니다."
            )
        if event_count == 0:
            notes.append(
                "자동 검사에서 v1 기준의 편집 대상 사건이 없어 원본 곡선을 보존했습니다."
            )
        elif terminal_only:
            notes.append(
                "미회복 말단 사건만 있어 곡선을 편집하지 않았습니다. 말단은 원본 그대로이며 "
                "사람의 검토가 필요합니다; 이 결과는 하항복 곡선을 승인하지 않습니다."
            )
        elif has_terminal:
            notes.append(
                "회복 사건의 영향 구간만 편집하고 미회복 말단 구간은 "
                "원행 그대로 보존했습니다. "
                "말단이 남아 있어 사람의 검토가 필요합니다."
            )
        elif edit_applied:
            notes.append(
                f"선택한 자동 방법이 원응력 {changed_points:.0f}점을 실제로 바꿨습니다."
            )
        else:
            notes.append("회복 사건은 검출했지만 포락선이 원응력과 같아 실제 변경은 없습니다.")
        if open_partial_count > 0:
            notes.append(
                "부분 회복 사건이 관측 종료까지 열려 있고 이전 봉우리로 복귀하지 못했습니다. "
                "끝 이후 자료가 없어 사람의 검토가 필요합니다."
            )
        notes.append(
            "자동 프로필은 선택 사건 구간을 처리합니다. 전체 곡선이나 카드의 단조성을 "
            "보장하지 않으며, 규격 하항복 물성을 산출하거나 승인하지 않습니다."
        )
        effective_options = {**fixed_options, "method": profile.id}
        return StepResult(
            result.frame,
            notes=tuple(notes),
            scalars=(
                *result.scalars,
                Scalar("auto_edit_applied", "자동 근사 편집 적용", float(edit_applied), "1"),
                Scalar(
                    "auto_review_required", "자동 근사 검토 필요", float(review_required), "1"
                ),
                Scalar(
                    "auto_terminal_only", "자동 근사 말단 사건만", float(terminal_only), "1"
                ),
            ),
            effective_options=effective_options,
        )

    strain_raw, stress_raw, strain_key, stress_key = _pair(frame, options)
    strain, stress = _finite_pair(strain_raw, stress_raw, strain_key, stress_key)
    scope = option_text(options, "scope", YIELD_DROP_SCOPES)
    method = option_text(options, "method", YIELD_DROP_METHODS)
    threshold = option_float(options, "threshold", YIELD_DROP_THRESHOLD)
    if not 0 <= threshold < 1:
        raise ProcessingError(f"하강 문턱은 0 이상 1 미만이어야 합니다: {threshold}")
    recovery_threshold = (
        option_float(options, "recovery_threshold")
        if options.get("recovery_threshold") is not None
        else threshold
    )
    if not 0 <= recovery_threshold < 1:
        raise ProcessingError(f"회복 문턱은 0 이상 1 미만이어야 합니다: {recovery_threshold}")
    min_reference_fraction = (
        0.0
        if scope == "full" and options.get("min_reference_fraction") is None
        else option_float(options, "min_reference_fraction", 0.05)
    )
    if not 0 <= min_reference_fraction <= 1:
        raise ProcessingError(
            f"최소 기준 봉우리 비율은 0 이상 1 이하이어야 합니다: {min_reference_fraction}"
        )
    min_slope = option_float(options, "min_slope", 0.0)
    if min_slope < 0:
        raise ProcessingError(f"최소 기울기는 0 이상이어야 합니다: {min_slope}")
    domain, requested_start, requested_end = _domain_indices(strain, scope, options)
    if not np.any(stress > 0):
        raise ProcessingError("양의 인장응력이 없어 상대 하강을 평가할 수 없음")

    local_stress = stress[domain]
    try:
        local_events = detect_events(
            local_stress,
            threshold,
            recovery_threshold,
            min_reference_fraction,
        )
    except ValueError as exc:
        raise ProcessingError(f"사건 검출 입력이 유효하지 않습니다: {exc}") from exc
    events = _absolute_events(local_events, domain)
    domain_running = np.maximum.accumulate(stress[domain])
    max_drop = float(np.max(domain_running - stress[domain])) if domain.size else 0.0

    if method == "keep":
        if scope == "full":
            require_increasing(strain, what=f"'{strain_key}'")
            keep_notes = [
                f"계산 scope=full, 실제 원행 index 0~{len(stress) - 1}, "
                f"변형률 {float(strain[0]):.6g}~{float(strain[-1]):.6g}",
            ]
            keep_notes.extend(
                _event_notes(events, domain, strain, stress, threshold, min_reference_fraction)
            )
            keep_notes.append("곡선은 그대로 둡니다.")
            keep_scalars = [
                Scalar("yield_drop_max", "최대 하강 폭", max_drop, "Pa"),
                *_event_scalars(events),
                Scalar("yield_drop_points", "손댄 점 수", 0.0, "1"),
                Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                Scalar(
                    "remaining_drop_count",
                    "남은 하강 수",
                    float(np.count_nonzero(np.diff(stress) < 0)),
                    "1",
                ),
            ]
            return StepResult(frame, notes=tuple(keep_notes), scalars=tuple(keep_scalars))
        result = _scoped_result(
            frame,
            strain,
            stress,
            strain_key,
            stress_key,
            scope=scope,
            method=method,
            domain=domain,
            events=events,
            options=options,
            threshold=threshold,
            min_reference_fraction=min_reference_fraction,
            min_slope=min_slope,
            requested_start=requested_start,
            requested_end=requested_end,
        )
        scalars = list(result.scalars)
        scalars.insert(0, Scalar("yield_drop_max", "최대 하강 폭", max_drop, "Pa"))
        non_increasing = np.diff(strain[domain]) <= 0
        if np.any(non_increasing):
            reversal_count = int(np.count_nonzero(np.diff(strain[domain]) < 0))
            duplicate_count = int(np.count_nonzero(np.diff(strain[domain]) == 0))
            result = StepResult(
                result.frame,
                notes=(
                    *result.notes,
                    f"진단 domain에 역전 {reversal_count}개와 중복 {duplicate_count}개가 "
                    "있어 편집 가능한 단조 곡선으로 보지 않습니다.",
                ),
                scalars=result.scalars,
            )
        return StepResult(result.frame, notes=result.notes, scalars=tuple(scalars))

    if scope != "full" and method not in _SCOPED_METHODS:
        raise ProcessingError(
            f"method='{method}' 은 scope='{scope}' 에서 사용할 수 없습니다. "
            "lower_yield는 scope='full'의 명시 plateau 계약만 지원합니다."
        )
    if scope == "full" and method not in _FULL_METHODS:
        raise ProcessingError(
            f"method='{method}' 은 scope='full'에서 사용할 수 없습니다. "
            "새 범위 방법에는 scope='range' 또는 scope='events'를 지정하세요."
        )
    require_increasing(
        strain if scope == "full" else strain[domain],
        what=(f"'{strain_key}'" if scope == "full" else f"'{strain_key}' 선택 편집 domain"),
    )
    if method == "lower_yield":
        if scope != "full":
            raise ProcessingError(
                "lower_yield는 scope='full'에서만 명시 plateau 계약으로 처리합니다."
            )
        if min_slope != 0:
            raise ProcessingError(
                "선택 구간 평탄화와 최소 기울기 단조화는 한 단계에서 함께 하지 않습니다. "
                "min_slope=0 으로 두고 별도의 단조화 단계를 사용하세요."
            )
        missing = tuple(
            name
            for name in ("plateau_start", "plateau_end", "plateau_stress")
            if options.get(name) is None
        )
        if missing:
            names = ", ".join(missing)
            raise ProcessingError(
                "옛 하항복 자동 평탄화는 지원하지 않습니다. lower_yield 모델 근사를 "
                f"사용하려면 {names} 를 지정하세요."
            )
        plateau_start = option_float(options, "plateau_start")
        plateau_end = option_float(options, "plateau_end")
        plateau_stress = option_float(options, "plateau_stress")
        if plateau_start >= plateau_end:
            raise ProcessingError(
                f"평탄화 구간 시작({plateau_start})이 끝({plateau_end})보다 작아야 합니다."
            )
        observed_start = float(strain[0])
        observed_end = float(strain[-1])
        if plateau_start < observed_start or plateau_end > observed_end:
            raise ProcessingError(
                f"평탄화 구간({plateau_start}~{plateau_end})이 관측 변형률 범위 "
                f"({observed_start}~{observed_end}) 안에 있어야 합니다."
            )
        selected = (strain >= plateau_start) & (strain <= plateau_end)
        selected_count = int(np.count_nonzero(selected))
        if selected_count < 2:
            raise ProcessingError(
                "평탄화 구간에 포함되는 원관측점이 2점 미만입니다. "
                "두 점 이상을 포함하도록 구간을 다시 지정하세요."
            )
        if plateau_stress <= 0:
            raise ProcessingError(f"평탄화 목표 응력은 0보다 커야 합니다: {plateau_stress} Pa")
        fixed = stress.copy()
        fixed[selected] = plateau_stress
        changed = int(np.count_nonzero(fixed != stress))
        selected_strain = strain[selected]
        actual_start = float(selected_strain[0])
        actual_end = float(selected_strain[-1])
        plateau_note = (
            f"선택 구간 평탄화(모델 근사): 요청 변형률 {plateau_start:.6g}~"
            f"{plateau_end:.6g}, 실제 관측 구간 {actual_start:.6g}~{actual_end:.6g}, "
            f"원관측점 {selected_count}점, 입력 목표응력 {plateau_stress:.6g} Pa, "
            f"변경점 {changed}개. 규격 하항복강도(ReL)나 뤼더스 변형률을 측정한 결과가 "
            "아닙니다."
        )
        return StepResult(
            frame.with_columns({stress_key: fixed}, {}),
            notes=(plateau_note,),
            scalars=(
                Scalar("yield_drop_max", "최대 하강 폭", max_drop, "Pa"),
                Scalar("yield_drop_points", "손댄 점 수", float(changed), "1"),
                Scalar("model_plateau_stress", "모델 평탄 응력", plateau_stress, "Pa"),
                Scalar(
                    "model_plateau_start", "모델 평탄 시작 변형률", actual_start, "1", "strain"
                ),
                Scalar("model_plateau_end", "모델 평탄 끝 변형률", actual_end, "1", "strain"),
            ),
        )

    if scope == "full":
        first = _first_drop(stress, threshold)
        full_notes: list[str] = [
            f"계산 scope=full, 실제 원행 index 0~{len(stress) - 1}, "
            f"변형률 {float(strain[0]):.6g}~{float(strain[-1]):.6g}",
        ]
        full_notes.extend(
            _event_notes(events, domain, strain, stress, threshold, min_reference_fraction)
        )
        upper_index: int | None = None
        recover_index: int | None = None
        if first is not None:
            upper_index = int(np.argmax(stress[:first]))
            upper = float(stress[upper_index])
            after = np.nonzero(stress[first:] >= upper)[0]
            recover_index = int(first + after[0]) if after.size else None
            full_notes.append(
                f"기존 full 진단의 첫 상대 하강은 peak index {upper_index} "
                f"({upper / 1e6:.4g} MPa, 변형률 {float(strain[upper_index]):.4g}) 뒤에서 "
                + (
                    f"변형률 {float(strain[recover_index]):.4g} 에서 봉우리를 다시 넘습니다."
                    if recover_index is not None
                    else "끝까지 봉우리를 다시 넘지 않습니다."
                )
            )
        else:
            full_notes.append(
                f"양수인 선행 최댓값에서 {threshold * 100:.2g}%를 넘는 하강이 없습니다"
                f"(최대 {max_drop / 1e6:.3g} MPa) — 응력 하강으로 보지 않습니다."
            )
        full_scalars: list[Scalar] = [
            Scalar("yield_drop_max", "최대 하강 폭", max_drop, "Pa"),
            *_event_scalars(events),
        ]
        if method == "keep" or (first is None and min_slope <= 0):
            if method != "keep":
                full_notes.append("곡선은 그대로 둡니다.")
            full_scalars.extend(
                [
                    Scalar("yield_drop_points", "손댄 점 수", 0.0, "1"),
                    Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                    Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                    Scalar(
                        "remaining_drop_count",
                        "남은 하강 수",
                        float(np.count_nonzero(np.diff(stress) < 0)),
                        "1",
                    ),
                ]
            )
            return StepResult(frame, notes=tuple(full_notes), scalars=tuple(full_scalars))
        if first is None:
            fixed = stress.copy()
            for index in range(1, len(fixed)):
                floor = fixed[index - 1] + min_slope * float(strain[index] - strain[index - 1])
                if fixed[index] < floor:
                    fixed[index] = floor
            changed = int(np.count_nonzero(fixed != stress))
            full_notes.append(
                f"평탄부에 최소 기울기 {min_slope:.3g} Pa 를 줘 엄격히 단조 증가로 "
                "만들었습니다 — "
                f"{changed}점을 올렸습니다."
            )
            full_scalars.extend(
                [
                    Scalar("yield_drop_points", "손댄 점 수", float(changed), "1"),
                    Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                    Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                    Scalar(
                        "remaining_drop_count",
                        "남은 하강 수",
                        float(np.count_nonzero(np.diff(fixed) < 0)),
                        "1",
                    ),
                ]
            )
            return StepResult(
                frame.with_columns({stress_key: fixed}, {}),
                notes=tuple(full_notes),
                scalars=tuple(full_scalars),
            )
        if method == "cut":
            assert upper_index is not None
            kept = upper_index + 1
            removed = len(stress) - kept
            full_notes.append(
                f"기존 full 첫 상대 하강 peak(index {upper_index}, 변형률 "
                f"{float(strain[upper_index]):.4g})에서 잘랐습니다 — "
                f"뒤의 {removed}점은 버렸습니다."
            )
            full_scalars.extend(
                [
                    Scalar("yield_drop_points", "손댄 점 수", float(removed), "1"),
                    Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                    Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                    Scalar(
                        "remaining_drop_count",
                        "남은 하강 수",
                        float(np.count_nonzero(np.diff(stress[:kept]) < 0)),
                        "1",
                    ),
                ]
            )
            return StepResult(
                frame.select(np.arange(kept)),
                notes=tuple(full_notes),
                scalars=tuple(full_scalars),
            )
        # Keep the parent full-domain numeric contract: PAVA/running-max is
        # applied to y first, and the historic forward slope floor follows it.
        if method == "envelope":
            fixed = np.maximum.accumulate(stress).astype(np.float64)
        else:
            fixed = _isotonic(stress)
        if min_slope > 0:
            for index in range(1, len(fixed)):
                floor = fixed[index - 1] + min_slope * float(strain[index] - strain[index - 1])
                if fixed[index] < floor:
                    fixed[index] = floor
        changed = int(np.count_nonzero(fixed != stress))
        full_notes.append(
            (
                "내려가는 구간을 직전 최댓값으로 덮었습니다(단조 포락선)"
                if method == "envelope"
                else "단조 비감소 최소제곱 회귀(PAVA)로 폈습니다"
            )
            + f" — {changed}점을 바꿨습니다."
        )
        full_score, full_rmse = _fit_interval_statistics(stress, fixed, [(0, len(stress) - 1)])
        full_scalars.extend(
            [
                Scalar("yield_drop_points", "손댄 점 수", float(changed), "1"),
                Scalar("boundary_jump_count", "경계 jump 수", 0.0, "1"),
                Scalar("boundary_jump_max", "최대 경계 jump", 0.0, "Pa"),
                Scalar(
                    "remaining_drop_count",
                    "남은 하강 수",
                    float(np.count_nonzero(np.diff(fixed) < 0)),
                    "1",
                ),
                Scalar("fit_r_squared", "처리 구간 R²", full_score, "1"),
                Scalar("fit_rmse", "처리 구간 RMSE", full_rmse, "Pa"),
            ]
        )
        return StepResult(
            frame.with_columns({stress_key: fixed}, {}),
            notes=tuple(full_notes),
            scalars=tuple(full_scalars),
        )

    result = _scoped_result(
        frame,
        strain,
        stress,
        strain_key,
        stress_key,
        scope=scope,
        method=method,
        domain=domain,
        events=events,
        options=options,
        threshold=threshold,
        min_reference_fraction=min_reference_fraction,
        min_slope=min_slope,
        requested_start=requested_start,
        requested_end=requested_end,
        auto_profile=(
            options.get("_auto_profile")
            if isinstance(options.get("_auto_profile"), _AutoYieldProfile)
            else None
        ),
    )
    scalars = list(result.scalars)
    scalars.insert(0, Scalar("yield_drop_max", "최대 하강 폭", max_drop, "Pa"))
    return StepResult(result.frame, notes=result.notes, scalars=tuple(scalars))
