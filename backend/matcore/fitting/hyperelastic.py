"""고무 초탄성 — **비압축 가정의 공칭 응력-신축비.**

65 의 `hyperelastic_families.py`(429줄) 를 이식했다. 식은 공개된 것이고, 65 와 우리
사이에 다른 것은 **어디에 얹히는가** 뿐이다.

## 축이 금속과 반대다

금속 경화식은 **진응력·진소성변형률**에 맞춘다. 솔버의 `*PLASTIC` 이 그것을 받기
때문이다. 고무는 **공칭 응력·공칭 변형률**에 맞춘다 — Abaqus `*HYPERELASTIC` 의
`UNIAXIAL TEST DATA` 가 공칭이고, 변형 에너지 밀도 함수가 신축비 λ=1+ε 로 쓰이기
때문이다.

**같은 데이터로도 축이 다르면 전혀 다른 파라미터가 나온다.** 공칭으로 맞춘 것을
진응력 자리에 넣으면 덱은 돌고 결과는 그럴듯하다. 그래서 축을 식이 선언한다.

## 단축 하나로 맞춘 계수는 다른 모드에서 어긋난다

이 도메인에서 가장 유명한 함정이다. 단축 인장만으로 맞춘 Ogden 이 **평면 전단이나
등이축에서는 크게 빗나간다** — 비압축 초탄성은 세 모드가 같은 변형에너지에서
나오는데, 한 모드만 보면 그 함수가 덜 정해지기 때문이다.

65 는 모드 여럿을 받고 holdout 까지 나눈다. 우리는 지금 **단축 데이터만 있고**,
그래서 단축만 맞추되 **그 사실을 카드와 덱에 적는다.** 없는 데이터를 지어내는
것보다 낫고, 나중에 평면·등이축 시험이 들어오면 모드를 늘린다.

## 적합은 됐는데 해석이 발산하는 계수

공칭 응력이 적합 구간에서 감소하면(Drucker 안정 위반) 솔버가 발산하거나 조용히
이상한 답을 낸다. **막지는 않는다** — 데이터가 실제로 그런 모양일 수 있고, 막으면
사람은 시스템 밖에서 계수를 만든다. 대신 짚는다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import numpy as np

from matcore.fitting import Family, register_family

#: 공칭 변형률 · 공칭 응력. **진응력이 아니다** — 위 참조.
STRAIN = "strain_engineering"
STRESS = "stress_engineering"

#: 이 식들이 뜻을 갖는 재료군. 금속 경화식과 한 목록에서 RMSE 로 줄 세우면 안 된다.
RUBBERY = ("Rubber", "Elastomer", "Polymer")


def _stretch(strain: np.ndarray) -> np.ndarray:
    """신축비 λ = 1 + ε. **압축으로 뒤집히면 식이 성립하지 않는다.**"""
    stretch = 1.0 + np.asarray(strain, dtype=np.float64)
    if np.any(stretch <= 0):
        raise ValueError("신축비가 0 이하입니다. 공칭 변형률이 -1 보다 커야 합니다.")
    return stretch


def _uniaxial_shape(stretch: np.ndarray) -> np.ndarray:
    """단축 인장의 공통 인자 `λ - λ⁻²`. I₁ 계열 식이 전부 이것을 곱한다."""
    return np.asarray(stretch - stretch**-2.0, dtype=np.float64)


def _neo_hookean(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    (c10,) = parameters
    return np.asarray(2.0 * c10 * _uniaxial_shape(_stretch(strain)), dtype=np.float64)


def _mooney_rivlin(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    c10, c01 = parameters
    stretch = _stretch(strain)
    return np.asarray(2.0 * (c10 + c01 / stretch) * _uniaxial_shape(stretch), dtype=np.float64)


def _yeoh(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    c10, c20, c30 = parameters
    stretch = _stretch(strain)
    # 단축에서 I₁ = λ² + 2/λ. 세 항 모두 I₁ 만의 함수라 I₂ 는 안 쓴다.
    shifted = stretch**2.0 + 2.0 / stretch - 3.0
    derivative = c10 + 2.0 * c20 * shifted + 3.0 * c30 * shifted**2.0
    return np.asarray(2.0 * derivative * _uniaxial_shape(stretch), dtype=np.float64)


def _ogden_1(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    mu, alpha = parameters
    stretch = _stretch(strain)
    if alpha <= 0:
        raise ValueError("Ogden 의 α 는 양수여야 합니다.")
    factor = stretch ** (alpha - 1.0) - stretch ** (-alpha / 2.0 - 1.0)
    return np.asarray((2.0 * mu / alpha) * factor, dtype=np.float64)


# ── 야코비안 ────────────────────────────────────────────────────────────
#
# I₁ 계열 셋(Neo-Hookean·Mooney-Rivlin·Yeoh)은 **파라미터에 선형이다.** 그래서
# 야코비안이 파라미터를 아예 안 쓴다 — 계수를 곱하는 자리마다 그 인자를 그대로
# 세우면 끝이다. Ogden 만 지수 자리에 α 가 들어서 진짜 미분이 필요하다.


def _neo_hookean_jacobian(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    return np.stack([2.0 * _uniaxial_shape(_stretch(strain))], axis=1)


def _mooney_rivlin_jacobian(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    stretch = _stretch(strain)
    shape = _uniaxial_shape(stretch)
    return np.stack([2.0 * shape, 2.0 * shape / stretch], axis=1)


def _yeoh_jacobian(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    stretch = _stretch(strain)
    shape = _uniaxial_shape(stretch)
    shifted = stretch**2.0 + 2.0 / stretch - 3.0
    return np.stack([2.0 * shape, 4.0 * shifted * shape, 6.0 * shifted**2.0 * shape], axis=1)


def _ogden_1_jacobian(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """P = (2μ/α)(λ^(α-1) - λ^(-α/2-1)) 를 μ·α 로 미분한 것.

    **α 가 지수와 분모 양쪽에 있다.** 곱셈 규칙으로 두 항이 나오고, 그중 -f/α²
    항이 α 가 작을 때(하한 1e-3) 커진다.

    그래서 여기가 가장 크게 갈릴 줄 알았는데 **실측은 그렇지 않았다** — 초기값을
    200번 흔들어도 수치·해석 둘 다 200/200 이었다. 남는 값은 속도뿐이다.
    """
    mu, alpha = parameters
    stretch = _stretch(strain)
    if alpha <= 0:
        raise ValueError("Ogden 의 α 는 양수여야 합니다.")
    high = stretch ** (alpha - 1.0)
    low = stretch ** (-alpha / 2.0 - 1.0)
    factor = high - low
    log = np.log(stretch)
    by_alpha = 2.0 * mu * (log * (high + 0.5 * low) / alpha - factor / alpha**2.0)
    return np.stack([(2.0 / alpha) * factor, by_alpha], axis=1)


def _scale(stress: np.ndarray) -> float:
    """응력 크기. 고무는 MPa 단위이고 금속은 GPa 라 경계를 절대값으로 못 적는다."""
    top = float(np.max(np.abs(np.asarray(stress, dtype=np.float64))))
    return top if top > 0 else 1.0


def _guess(count: int, first: float) -> object:
    def guess(strain: np.ndarray, stress: np.ndarray) -> np.ndarray:
        scale = _scale(stress)
        values = [scale * first] + [0.0] * (count - 1)
        return np.asarray(values, dtype=np.float64)

    return guess


def _bounds(lows: tuple[float, ...], highs: tuple[float, ...]) -> object:
    def bounds(strain: np.ndarray, stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        scale = _scale(stress)
        return (
            np.asarray([scale * one for one in lows], dtype=np.float64),
            np.asarray([scale * one for one in highs], dtype=np.float64),
        )

    return bounds


def positive_stretch(
    strain: np.ndarray, stress: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """적합 전에 다듬는다 — **압축 쪽과 원점 중복을 걷는다.**

    금속의 `plastic_branch` 가 하는 일과 자리는 같지만 이유가 다르다. 여기서는
    탄성 구간을 걷는 것이 아니라(초탄성은 그 구간도 설명한다) **식이 성립하지
    않는 점**을 걷는다.
    """
    x = np.asarray(strain, dtype=np.float64)
    y = np.asarray(stress, dtype=np.float64)
    notes: list[str] = []

    keep = x > -1.0
    if not np.all(keep):
        notes.append(
            f"공칭 변형률이 -1 이하인 점 {int(np.sum(~keep))}개를 뺐습니다 — "
            f"신축비가 0 이하라 초탄성 식이 성립하지 않습니다."
        )
        x, y = x[keep], y[keep]

    # 원점에 붙은 점이 여럿이면 그것이 적합을 지배한다. 하나만 남긴다.
    at_origin = np.isclose(x, 0.0, atol=1e-9)
    if int(np.sum(at_origin)) > 1:
        first = int(np.argmax(at_origin))
        drop = at_origin.copy()
        drop[first] = False
        notes.append(
            f"원점에 겹친 점 {int(np.sum(drop))}개를 한 점으로 모았습니다 — "
            f"처리 단계가 남긴 자국입니다."
        )
        x, y = x[~drop], y[~drop]

    return x, y, notes


def _monotonic(evaluate: object) -> object:
    """공칭 응력이 적합 구간에서 감소하는가.

    감소하면 **해석이 발산하거나 조용히 이상한 답을 낸다**(Drucker 안정 위반).
    막지 않고 짚는다 — 데이터가 실제로 그런 모양일 수 있다.
    """

    def check(parameters: np.ndarray, strain: np.ndarray) -> list[str]:
        grid = np.linspace(float(np.min(strain)), float(np.max(strain)), 200)
        try:
            predicted = evaluate(parameters, grid)  # type: ignore[operator]
        except ValueError:
            return ["안정성을 검사하지 못했습니다 — 적합 구간에서 식이 성립하지 않습니다."]
        if np.any(np.diff(predicted) < -1e-8 * max(float(np.max(np.abs(predicted))), 1.0)):
            return [
                "적합 구간 안에서 공칭 응력이 감소합니다 — 이 계수로 해석하면 "
                "발산하거나 조용히 이상한 답이 나올 수 있습니다(Drucker 안정 위반). "
                "다른 식을 견주거나 적합 구간을 좁혀 보세요."
            ]
        return []

    return check


#: 단축 하나로 맞췄다는 사실. **덱까지 따라가야 한다.**
UNIAXIAL_ONLY = (
    "단축 인장 하나로 맞춘 계수입니다 — 평면 전단·등이축에서는 크게 빗나갈 수 "
    "있습니다. 그 모드로 해석하려면 그 시험 데이터가 필요합니다."
)


def _shear(compute: object) -> object:
    """초기 전단탄성률 μ₀ — **변형이 0 에 가까울 때의 기울기에서 나온다.**

    식이 달라도 이 값은 비슷하게 나와야 한다. 크게 갈리면 둘 중 하나는 데이터의
    시작 구간을 못 따라간 것이고, 그 사실은 RMSE 하나로는 안 보인다.
    """

    def extras(parameters: np.ndarray) -> dict[str, object]:
        return {"shear_modulus": float(compute(parameters)), "mode": "단축 인장"}  # type: ignore[operator]

    return extras


def _family(
    key: str,
    label: str,
    names: tuple[str, ...],
    units: tuple[str, ...],
    evaluate: object,
    guess: object,
    bounds: object,
    describe: str,
    shear: object,
    jacobian: object,
) -> Family:
    return Family(
        key=key,
        label=label,
        parameter_names=names,
        parameter_units=units,
        evaluate=evaluate,
        guess=guess,
        bounds=bounds,
        describe=describe,
        x_label="공칭 변형률",
        y_label="공칭 응력",
        x_column=STRAIN,
        y_column=STRESS,
        prepare=positive_stretch,
        block="hyperelastic",
        applies_to=RUBBERY,
        extras=_shear(shear),
        stability=_monotonic(evaluate),
        jacobian=jacobian,
    )


def load() -> None:
    """등록한다. `matcore.fitting.load_builtin` 이 부른다."""


register_family(
    _family(
        key="neo_hookean",
        label="Neo-Hookean",
        names=("c10",),
        units=("Pa",),
        evaluate=_neo_hookean,
        jacobian=_neo_hookean_jacobian,
        guess=_guess(1, 1.0 / 6.0),
        bounds=_bounds((1e-8,), (10.0,)),
        describe="P = 2·C10·(λ - λ⁻²) — 가장 단순한 초탄성. 30% 안쪽 변형에서 쓸 만하다.",
        shear=lambda p: 2.0 * float(p[0]),
    )
)

register_family(
    _family(
        key="mooney_rivlin",
        label="Mooney-Rivlin",
        names=("c10", "c01"),
        units=("Pa", "Pa"),
        evaluate=_mooney_rivlin,
        jacobian=_mooney_rivlin_jacobian,
        guess=_guess(2, 1.0 / 12.0),
        bounds=_bounds((1e-8, 0.0), (10.0, 10.0)),
        describe="P = 2(C10 + C01/λ)(λ - λ⁻²) — I₂ 항이 있어 중간 변형까지 따라간다.",
        shear=lambda p: 2.0 * (float(p[0]) + float(p[1])),
    )
)

register_family(
    _family(
        key="yeoh",
        label="Yeoh",
        names=("c10", "c20", "c30"),
        units=("Pa", "Pa", "Pa"),
        evaluate=_yeoh,
        jacobian=_yeoh_jacobian,
        guess=_guess(3, 1.0 / 6.0),
        bounds=_bounds((1e-8, -10.0, -10.0), (10.0, 10.0, 10.0)),
        describe="I₁ 3차 — 큰 변형에서 다시 뻣뻣해지는 모양(upturn)을 낸다.",
        shear=lambda p: 2.0 * float(p[0]),
    )
)

register_family(
    Family(
        key="ogden_1",
        label="Ogden (1항)",
        parameter_names=("mu", "alpha"),
        parameter_units=("Pa", "1"),
        evaluate=_ogden_1,
        jacobian=_ogden_1_jacobian,
        # α 는 응력 크기와 무관한 지수라 스케일을 곱하면 안 된다.
        guess=lambda strain, stress: np.asarray([_scale(stress) / 3.0, 2.0], dtype=np.float64),
        bounds=lambda strain, stress: (
            np.asarray([_scale(stress) * 1e-8, 1e-3], dtype=np.float64),
            np.asarray([_scale(stress) * 10.0, 30.0], dtype=np.float64),
        ),
        describe="P = (2μ/α)(λ^(α-1) - λ^(-α/2-1)) — 지수가 자유로워 넓은 구간을 따라간다.",
        x_label="공칭 변형률",
        y_label="공칭 응력",
        x_column=STRAIN,
        y_column=STRESS,
        prepare=positive_stretch,
        block="hyperelastic",
        applies_to=RUBBERY,
        # Ogden 1항의 초기 전단탄성률은 μ 그 자체다.
        extras=_shear(lambda p: float(p[0])),
        stability=_monotonic(_ogden_1),
    )
)
