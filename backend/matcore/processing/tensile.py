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

from matcore import ParamSpec, register
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

#: R² 가 뜻을 갖기 시작하는 점 수. 이보다 적으면 값이 아니라 경고를 낸다.
MIN_TRUSTWORTHY_POINTS = 5

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
            help="시편 정의에서 옵니다. 변위를 이 길이로 나눠 변형률을 만듭니다.",
        ),
        ParamSpec(
            name="area",
            label="초기 단면적",
            type="float",
            unit="m2",
            help="폭 곱하기 두께. 하중을 이 넓이로 나눠 응력을 만듭니다.",
        ),
        ParamSpec(name="displacement", label="변위 열", type="str", default="displacement"),
        ParamSpec(name="force", label="하중 열", type="str", default="force"),
    ),
    applies_to=("tensile",),
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
            choices=("linear_regression", "chord", "secant", "manual"),
            choice_labels={
                "linear_regression": "최소제곱 회귀",
                "chord": "현 (구간 양 끝 두 점)",
                "secant": "할선 (원점에서 구간 끝)",
                "manual": "직접 입력",
            },
            help="같은 곡선에서도 방법마다 몇 % 다릅니다. 어느 쪽이 옳은지는 규격이 정합니다.",
        ),
        ParamSpec(
            name="minimum_strain",
            dimension="strain",
            label="구간 시작",
            type="float",
            default=0.0005,
            unit="1",
            when={"method": ("linear_regression", "chord", "secant")},
        ),
        ParamSpec(
            name="maximum_strain",
            dimension="strain",
            label="구간 끝",
            type="float",
            default=0.0025,
            unit="1",
            when={"method": ("linear_regression", "chord", "secant")},
        ),
        ParamSpec(
            name="manual_modulus",
            label="직접 입력",
            type="float",
            unit="Pa",
            when={"method": ("manual",)},
        ),
        ParamSpec(name="strain", label="변형률 열", type="str"),
        ParamSpec(name="stress", label="응력 열", type="str"),
    ),
    applies_to=("tensile",),
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

    method = option_text(options, "method", ("linear_regression", "chord", "secant", "manual"))
    low = option_float(options, "minimum_strain", 0.0005)
    high = option_float(options, "maximum_strain", 0.0025)
    if low >= high:
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
            modulus, intercept = (float(v) for v in np.polyfit(selected_x, selected_y, 1))
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

    scalars = [
        Scalar("youngs_modulus", "탄성계수", float(modulus), "Pa"),
        Scalar("elastic_intercept", "탄성 절편", float(intercept), "Pa"),
    ]
    if math.isfinite(r_squared):
        scalars.append(Scalar("elastic_r_squared", "탄성 구간 R²", float(r_squared), "1"))

    note = (
        f"직접 입력한 탄성계수 {modulus / 1e9:.4g} GPa"
        if method == "manual"
        else (
            f"{method} 로 변형률 [{low:.6g}, {high:.6g}] 구간의 {count}점에서 "
            f"{modulus / 1e9:.4g} GPa (R²={r_squared:.5f})"
        )
    )
    notes = [note]
    if method != "manual" and count < MIN_TRUSTWORTHY_POINTS:
        # **R² 는 점이 적으면 아무 말도 하지 않는다.** 2점을 지나는 직선은 언제나
        # R²=1 이고, 3점도 거의 그렇다. 그런데 화면에 1.00000 이 찍히면 사람은
        # "완벽하게 맞았다" 로 읽는다 — 실제로는 "정보가 없다" 다.
        #
        # 실측으로 걸렸다: 18점짜리 곡선에 [0.001, 0.004] 구간을 잡았더니 2점이
        # 걸려 R²=1 로 6.9 GPa 가 나왔다. 강판이면 200 GPa 여야 한다.
        notes.append(
            f"이 구간에 {count}점밖에 없습니다 — **R² 를 믿을 수 없습니다.** "
            f"{count}점을 지나는 직선은 거의 언제나 R²≈1 입니다. "
            f"구간을 넓히거나 더 조밀하게 측정된 곡선을 쓰세요."
        )
    elif math.isfinite(r_squared) and r_squared < 0.99:
        # **경고이지 실패가 아니다.** 재료에 따라 진짜로 직선이 아닐 수 있다.
        notes.append(
            f"R² 가 {r_squared:.4f} 로 낮습니다 — 구간이 항복 뒤까지 걸쳐 있거나 "
            f"초기 토우(시편 물림) 구간이 섞였는지 확인하세요."
        )
    return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))


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
            help="앞 단계에서 잰 값을 그대로 쓰거나, 직접 넣습니다.",
        ),
        ParamSpec(
            name="search_start", dimension="strain", label="탐색 시작", type="float", unit="1"
        ),
        ParamSpec(
            name="search_end", dimension="strain", label="탐색 끝", type="float", unit="1"
        ),
        ParamSpec(name="strain", label="변형률 열", type="str"),
        ParamSpec(name="stress", label="응력 열", type="str"),
    ),
    applies_to=("tensile",),
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
        ParamSpec(name="strain", label="변형률 열", type="str"),
        ParamSpec(name="stress", label="응력 열", type="str"),
    ),
    applies_to=("tensile",),
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
        ParamSpec(name="strain", label="변형률 열", type="str"),
        ParamSpec(name="stress", label="응력 열", type="str"),
    ),
    applies_to=("tensile",),
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
            when={"necking_policy": ("manual_index",)},
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
        ParamSpec(name="strain", label="변형률 열", type="str"),
        ParamSpec(name="stress", label="응력 열", type="str"),
    ),
    applies_to=("tensile",),
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
