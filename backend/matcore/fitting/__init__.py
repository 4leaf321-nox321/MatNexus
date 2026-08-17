"""물성 적합 — 곡선을 **솔버가 읽는 식**으로 바꾼다.

앞 단계까지가 "이 재료가 이렇게 거동한다" 를 데이터로 보인 것이라면, 여기는 그
거동을 **해석이 쓸 수 있는 모양**으로 만든다. 표로 넘길 수도 있고(tabulated),
식으로 줄일 수도 있다(Voce·Swift·Hockett-Sherby).

## 이 패키지가 지키는 것

**적합도를 숨기지 않는다.** 어떤 식이든 파라미터를 넣으면 곡선은 그려진다.
문제는 그 곡선이 데이터와 얼마나 맞느냐이고, 그것은 RMSE 와 잔차에만 보인다.
"Voce 로 적합했다" 만 남기면 다음 사람은 그 값을 믿을 수밖에 없다.

**적합 구간 밖을 말하지 않는다.** 소성변형률 0.2 까지 잰 데이터로 0.8 을
외삽하면 식마다 전혀 다른 값이 나온다 — Swift 는 계속 올라가고 Voce 는 포화한다.
어느 쪽이 맞는지는 **데이터에 없다.** 그래서 적합 구간을 결과에 박아 두고, 그
밖은 쓰는 쪽이 알고 쓰게 한다.

**경계를 명시한다.** 비선형 최소제곱은 초기값과 경계에 따라 다른 답에 수렴한다.
같은 데이터로 두 번 돌려 다른 값이 나오면 그 값은 근거가 아니다 — 경계와
초기값을 결과에 남겨 재현할 수 있게 한다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: 적합에 쓸 수 있는 최소 점 수. 파라미터 3~4개를 3점으로 맞추면 잔차가 0 이
#: 나오는데 그것은 적합이 아니라 보간이다.
MIN_POINTS = 6


class FittingError(Exception):
    """이 데이터로는 이 식을 적합할 수 없다.

    메시지는 **사용자가 읽는다.** 무엇이 모자라고 무엇을 하면 되는지 적는다.
    """


@dataclass(frozen=True)
class Parameter:
    name: str
    value: float
    si_unit: str
    lower: float
    upper: float
    initial: float
    """**경계와 초기값을 함께 남긴다.** 비선형 적합은 여기에 따라 다른 답에
    수렴한다. 남기지 않으면 같은 데이터로 다시 돌려도 재현이 안 된다."""


@dataclass(frozen=True)
class FitResult:
    family: str
    label: str
    parameters: tuple[Parameter, ...]
    rmse: float
    """제곱평균제곱근 오차(Pa). 절대 크기다."""
    relative_rmse: float
    """RMSE / 평균 응력. **식을 서로 견줄 때 이것을 본다** — 절대값은 재료마다
    크기가 달라 비교가 안 된다."""
    r_squared: float
    max_residual: float
    """가장 크게 어긋난 점. 평균이 좋아도 한 곳이 크게 틀릴 수 있다."""
    point_count: int
    strain_min: float
    strain_max: float
    """**적합 구간.** 이 밖은 외삽이고, 식마다 전혀 다른 값이 나온다."""
    notes: tuple[str, ...]

    def evaluate(self, plastic_strain: np.ndarray) -> np.ndarray:
        """적합된 식으로 응력을 계산한다. 구간 밖도 계산은 한다 — 다만 그것이
        외삽이라는 사실은 `notes` 와 `strain_max` 에 남아 있다."""
        family = FAMILIES[self.family]
        values = np.asarray([item.value for item in self.parameters], dtype=np.float64)
        computed: np.ndarray = family.evaluate(
            values, np.asarray(plastic_strain, dtype=np.float64)
        )
        return computed


@dataclass(frozen=True)
class Family:
    """경화식 한 종류."""

    key: str
    label: str
    parameter_names: tuple[str, ...]
    parameter_units: tuple[str, ...]
    evaluate: Any
    """`(파라미터 배열, 소성변형률 배열) -> 응력 배열`"""
    guess: Any
    """`(소성변형률, 응력) -> 초기값`. 초기값이 나쁘면 엉뚱한 곳에 수렴한다."""
    bounds: Any
    """`(소성변형률, 응력) -> (하한, 상한)`"""
    describe: str


def _voce(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    sigma_0, q, b = parameters
    return np.asarray(sigma_0 + q * (1.0 - np.exp(-b * strain)), dtype=np.float64)


def _voce_guess(strain: np.ndarray, stress: np.ndarray) -> np.ndarray:
    # s0 는 첫 응력, Q 는 마지막-첫 차이, b 는 변형률 범위의 역수쯤에서 시작한다.
    span = max(float(strain[-1] - strain[0]), 1e-6)
    return np.asarray(
        [float(stress[0]), max(float(stress[-1] - stress[0]), 1.0), 1.0 / span],
        dtype=np.float64,
    )


def _voce_bounds(strain: np.ndarray, stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    top = float(np.max(stress))
    return (
        np.asarray([0.0, 0.0, 1e-6], dtype=np.float64),
        np.asarray([top * 2.0, top * 5.0, 1e5], dtype=np.float64),
    )


def _swift(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    k, epsilon_0, n = parameters
    return np.asarray(k * np.power(np.maximum(epsilon_0 + strain, 1e-12), n), dtype=np.float64)


def _swift_guess(strain: np.ndarray, stress: np.ndarray) -> np.ndarray:
    return np.asarray([float(np.max(stress)), 0.005, 0.2], dtype=np.float64)


def _swift_bounds(strain: np.ndarray, stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    top = float(np.max(stress))
    return (
        np.asarray([0.0, 1e-9, 1e-4], dtype=np.float64),
        np.asarray([top * 10.0, 1.0, 1.0], dtype=np.float64),
    )


def _hockett_sherby(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    sigma_0, q, b, n = parameters
    safe = np.maximum(strain, 0.0)
    return np.asarray(sigma_0 + q * (1.0 - np.exp(-b * np.power(safe, n))), dtype=np.float64)


def _hockett_guess(strain: np.ndarray, stress: np.ndarray) -> np.ndarray:
    return np.asarray(
        [float(stress[0]), max(float(stress[-1] - stress[0]), 1.0), 1.0, 0.5],
        dtype=np.float64,
    )


def _hockett_bounds(strain: np.ndarray, stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    top = float(np.max(stress))
    return (
        np.asarray([0.0, 0.0, 1e-6, 1e-3], dtype=np.float64),
        np.asarray([top * 2.0, top * 5.0, 1e5, 5.0], dtype=np.float64),
    )


FAMILIES: dict[str, Family] = {
    "voce": Family(
        key="voce",
        label="Voce",
        parameter_names=("sigma_0", "q", "b"),
        parameter_units=("Pa", "Pa", "1"),
        evaluate=_voce,
        guess=_voce_guess,
        bounds=_voce_bounds,
        describe="sigma = s0 + Q(1 - exp(-b*eps)) — 포화형. 큰 변형에서 일정해진다.",
    ),
    "swift": Family(
        key="swift",
        label="Swift",
        parameter_names=("k", "epsilon_0", "n"),
        parameter_units=("Pa", "1", "1"),
        evaluate=_swift,
        guess=_swift_guess,
        bounds=_swift_bounds,
        describe="sigma = K(e0 + eps)^n — 멱함수형. 큰 변형에서도 계속 올라간다.",
    ),
    "hockett_sherby": Family(
        key="hockett_sherby",
        label="Hockett-Sherby",
        parameter_names=("sigma_0", "q", "b", "n"),
        parameter_units=("Pa", "Pa", "1", "1"),
        evaluate=_hockett_sherby,
        guess=_hockett_guess,
        bounds=_hockett_bounds,
        describe="sigma = s0 + Q(1 - exp(-b*eps^n)) — 포화형이면서 초기 기울기가 자유롭다.",
    ),
}


def fit(family_key: str, plastic_strain: np.ndarray, true_stress: np.ndarray) -> FitResult:
    """경화식 하나를 적합한다.

    **경계를 두고 푼다.** 물리적으로 음수일 수 없는 파라미터에 음수가 나오면
    곡선은 그려지는데 뜻이 없다. 경계와 초기값은 결과에 남겨 재현할 수 있게 한다.
    """
    from scipy.optimize import least_squares

    family = FAMILIES.get(family_key)
    if family is None:
        known = ", ".join(sorted(FAMILIES))
        raise FittingError(f"모르는 경화식입니다: {family_key}. 있는 것: {known}")

    strain = np.asarray(plastic_strain, dtype=np.float64)
    stress = np.asarray(true_stress, dtype=np.float64)
    if strain.shape != stress.shape:
        raise FittingError("변형률과 응력의 점 수가 다릅니다.")
    keep = np.isfinite(strain) & np.isfinite(stress) & (strain >= 0)
    strain, stress = strain[keep], stress[keep]
    if len(strain) < MIN_POINTS:
        raise FittingError(
            f"적합에는 {MIN_POINTS}점 이상이 필요합니다 (지금 {len(strain)}점). "
            f"파라미터 수만큼의 점으로 맞추면 잔차가 0 이 나오는데, 그것은 적합이 "
            f"아니라 보간입니다."
        )
    order = np.argsort(strain)
    strain, stress = strain[order], stress[order]

    lower, upper = family.bounds(strain, stress)
    initial = np.clip(family.guess(strain, stress), lower, upper)

    # 잔차를 응력 크기로 정규화한다. 안 하면 큰 응력 구간이 적합을 지배해서
    # 초기 구간(항복 근처)이 크게 어긋나도 RMSE 가 작게 나온다.
    scale = max(float(np.mean(np.abs(stress))), 1.0)

    def residual(parameters: np.ndarray) -> np.ndarray:
        difference: np.ndarray = family.evaluate(parameters, strain) - stress
        return difference / scale

    solved = least_squares(residual, initial, bounds=(lower, upper), max_nfev=5000)
    fitted = np.asarray(solved.x, dtype=np.float64)

    predicted = family.evaluate(fitted, strain)
    errors = predicted - stress
    rmse = float(np.sqrt(np.mean(errors**2)))
    total = float(np.sum((stress - np.mean(stress)) ** 2))
    r_squared = 1.0 - float(np.sum(errors**2)) / total if total > 0 else 0.0
    relative = rmse / scale

    notes = [
        f"{family.label} 을 소성변형률 {float(strain[0]):.5g}~{float(strain[-1]):.5g} "
        f"구간의 {len(strain)}점에 적합했습니다 (상대 RMSE {relative * 100:.3g}%).",
        # **적합 구간 밖은 식마다 전혀 다르다.** Swift 는 계속 올라가고 Voce 는
        # 포화한다 — 어느 쪽이 맞는지는 데이터에 없다.
        f"이 식은 적합 구간 밖에서 검증되지 않았습니다. "
        f"{float(strain[-1]):.5g} 를 넘는 변형률에 쓰려면 그 사실을 알고 쓰세요.",
    ]
    if relative > 0.05:
        notes.append(
            f"상대 RMSE 가 {relative * 100:.3g}% 로 큽니다 — 이 식이 이 재료의 모양과 "
            f"안 맞을 수 있습니다. 다른 식과 견줘 보세요."
        )
    if not solved.success:
        notes.append("최적화가 수렴하지 않았습니다. 파라미터가 경계에 붙어 있는지 확인하세요.")
    for index, name in enumerate(family.parameter_names):
        if np.isclose(fitted[index], lower[index]) or np.isclose(fitted[index], upper[index]):
            notes.append(
                f"'{name}' 가 경계에 붙었습니다 — 그 값은 데이터가 정한 것이 아니라 "
                f"경계가 정한 것입니다."
            )

    return FitResult(
        family=family.key,
        label=family.label,
        parameters=tuple(
            Parameter(
                name=name,
                value=float(fitted[index]),
                si_unit=family.parameter_units[index],
                lower=float(lower[index]),
                upper=float(upper[index]),
                initial=float(initial[index]),
            )
            for index, name in enumerate(family.parameter_names)
        ),
        rmse=rmse,
        relative_rmse=relative,
        r_squared=r_squared,
        max_residual=float(np.max(np.abs(errors))),
        point_count=len(strain),
        strain_min=float(strain[0]),
        strain_max=float(strain[-1]),
        notes=tuple(notes),
    )


def compare(
    plastic_strain: np.ndarray, true_stress: np.ndarray, families: tuple[str, ...] = ()
) -> list[FitResult]:
    """여러 식을 같은 데이터에 적합해 나란히 준다.

    **어느 것이 맞는지 고르지 않는다.** 상대 RMSE 가 가장 작은 것이 늘 옳지는
    않다 — Swift 와 Voce 는 적합 구간에서 비슷해도 그 밖에서 갈린다. 큰 변형까지
    쓸 것인지가 선택을 바꾸고, 그것은 해석하는 사람이 안다.
    """
    keys = families or tuple(FAMILIES)
    results: list[FitResult] = []
    for key in keys:
        try:
            results.append(fit(key, plastic_strain, true_stress))
        except FittingError:
            # 하나가 안 맞는다고 나머지를 버리지 않는다.
            continue
    return sorted(results, key=lambda item: item.relative_rmse)
