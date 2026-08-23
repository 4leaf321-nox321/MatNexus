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

from dataclasses import dataclass, replace
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

    def tangent(self, plastic_strain: np.ndarray) -> np.ndarray | None:
        """적합된 식의 기울기. 식이 접선을 선언하지 않았으면 `None`.

        **수치 미분으로 대신하지 않는다.** 특이점에서 거짓말을 하고, 그것이
        "여기서 기울기가 크다" 로 읽히면 위험한 외삽을 안전해 보이게 만든다.
        """
        family = FAMILIES[self.family]
        if family.tangent is None:
            return None
        values = np.asarray([item.value for item in self.parameters], dtype=np.float64)
        computed: np.ndarray = family.tangent(
            values, np.asarray(plastic_strain, dtype=np.float64)
        )
        return computed


@dataclass(frozen=True)
class Family:
    """적합할 식 한 종류.

    **어느 축에 맞추는지를 식이 선언한다.** 전에는 라우트가 `strain_true_plastic`·
    `stress_true` 를 상수로 들고 있었는데, 그것은 금속 소성의 축이다. 고무는
    **공칭 응력과 공칭 변형률**에 맞춘다 — 축이 다르면 같은 데이터로도 전혀 다른
    파라미터가 나온다.

    축을 여기 적어 두면 새 식을 더할 때 라우트를 안 고친다(D7).
    """

    key: str
    label: str
    parameter_names: tuple[str, ...]
    parameter_units: tuple[str, ...]
    evaluate: Any
    """`(파라미터 배열, x 배열) -> y 배열`"""
    guess: Any
    """`(x, y) -> 초기값`. 초기값이 나쁘면 엉뚱한 곳에 수렴한다."""
    bounds: Any
    """`(x, y) -> (하한, 상한)`"""
    describe: str

    x_label: str = "진소성변형률"
    y_label: str = "진응력"
    """사람이 읽는 축 이름. 메모와 **화면의 축 라벨**에 그대로 들어간다.

    고무 카드에 "소성변형률 0~2 구간" 이라고 적히거나 그래프의 x 축이 그렇게
    붙으면 그것은 거짓말이다 — 고무는 공칭 변형률에 맞춘다."""

    x_column: str = "strain_true_plastic"
    y_column: str = "stress_true"
    """**적합에 쓰는 축.** 금속 소성은 진응력·진소성변형률, 고무는 공칭이다.

    솔버가 받는 것이 그 축이기 때문이다 — 공칭으로 맞춘 파라미터를 진응력 자리에
    넣으면 조용히 틀린 해석이 된다."""

    prepare: Any = None
    """`(x, y) -> (x, y, 메모)`. 적합 전에 구간을 다듬는다.

    금속은 탄성 구간의 자국을 걷어낸다(`plastic_branch`) — 안 걷으면 x 가 전부
    0 인 점 수십 개가 적합을 지배해서, 식이 맞는데도 R² 가 0.4 로 나온다."""

    block: str = "hardening"
    """적합 결과가 담기는 물성 블록(ADR 0012). 초탄성은 `hyperelastic` 이다."""

    applies_to: tuple[str, ...] = ()
    """이 식이 뜻을 갖는 재료군. 비면 제한 없음.

    **Voce 와 Ogden 을 나란히 세워 RMSE 로 줄 세우면 안 된다** — 금속 경화식과
    고무 초탄성은 같은 물음의 답이 아니다. 무엇이 나란히 설 수 있는지는 식이 안다."""

    tangent: Any = None
    """`(파라미터, x) -> dy/dx`. **외삽이 물리적으로 말이 되는지 보는 근거다.**

    접선이 음수면 그 구간에서 재료가 연화한다는 뜻이고, 해석은 발산하거나 조용히
    이상한 답을 낸다. 측정 구간 안에서는 데이터가 그 모양이면 그런 것이지만,
    **외삽 구간의 연화는 식이 지어낸 것**이라 반드시 짚어야 한다.

    수치 미분으로 대신할 수도 있지만 그러면 특이점에서 거짓말을 한다 —
    Hockett-Sherby 의 접선은 ε=0 에서 **진짜 +∞ 극한**이지 큰 유한값이 아니다.
    """

    extras: Any = None
    """`(파라미터) -> {키: 값}`. 이 식만의 요약값.

    초탄성의 초기 전단탄성률이 그렇다 — 식마다 계산이 다른데(Neo-Hookean 은
    `2·C10`, Ogden 은 `μ`), **식이 달라도 이 값은 비슷하게 나와야 한다.** 서로
    견줄 수 있는 유일한 공통 척도라 카드에 함께 담는다."""

    stability: Any = None
    """`(파라미터, x) -> 경고 목록`. 적합 자체는 됐는데 **해석이 발산하는** 계수를
    짚는다. 고무에서 실제로 나는 일이다 — 막지 않고 말한다."""


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


def _voce_tangent(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """dσ/dε = Q·b·exp(-b·ε). **늘 양수이고 0 으로 수렴한다** — 포화형의 정의다."""
    _sigma_0, q, b = parameters
    return np.asarray(q * b * np.exp(-b * np.maximum(strain, 0.0)), dtype=np.float64)


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


def _swift_tangent(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """dσ/dε = K·n·(ε0+ε)^(n-1). **줄어들지만 0 이 되지 않는다** — 멱함수형이라
    큰 변형에서도 계속 오른다."""
    k, epsilon_0, n = parameters
    base = np.maximum(epsilon_0 + strain, 1e-12)
    return np.asarray(k * n * np.power(base, n - 1.0), dtype=np.float64)


def _hockett_sherby(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    sigma_0, q, b, n = parameters
    safe = np.maximum(strain, 0.0)
    return np.asarray(sigma_0 + q * (1.0 - np.exp(-b * np.power(safe, n))), dtype=np.float64)


def _hockett_tangent(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """dσ/dε = Q·b·n·ε^(n-1)·exp(-b·ε^n).

    **ε=0 에서 n<1 이면 진짜 +∞ 다.** 유한한 큰 수로 바꿔 돌려주면 "여기서 기울기가
    아주 크다" 와 "여기서 정의되지 않는다" 를 구별할 수 없게 된다. `inf` 를 그대로
    낸다 — 받는 쪽이 그것을 보고 판단한다.
    """
    _sigma_0, q, b, n = parameters
    safe = np.maximum(strain, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        power = np.power(safe, n - 1.0)
        value = q * b * n * power * np.exp(-b * np.power(safe, n))
    return np.asarray(
        np.where(safe > 0.0, value, np.inf if n < 1.0 else value), dtype=np.float64
    )


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


#: 금속 소성식이 뜻을 갖는 재료군.
#:
#: **비워 두면 "제한 없음" 이라 고무 재료에도 뜬다.** 처음에 그렇게 뒀더니 EPDM
#: 재료의 식 목록에 Voce 가 나란히 섰고, 그 둘은 축이 달라서(진응력 vs 공칭) 한
#: 그래프에 겹쳐 그릴 수도 없다.
METALLIC = ("Metal",)

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
        tangent=_voce_tangent,
        applies_to=METALLIC,
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
        tangent=_swift_tangent,
        applies_to=METALLIC,
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
        tangent=_hockett_tangent,
        applies_to=METALLIC,
    ),
}


@dataclass(frozen=True)
class Blended:
    """두 식을 가중평균한 것 — **외삽에서 갈리는 구간을 사람이 조정한다.**

    ## 왜 필요한가

    측정 구간에서 두 식이 거의 같은데 외삽에서 크게 갈린다. 실측(합성 곡선, 측정
    0~0.2):

        측정 구간 상대 RMSE   Voce 0.00%   Swift 1.02%
        외삽 1.0 의 응력      Voce 550     Swift 744 MPa

    **어느 쪽도 맞지 않을 수 있다.** Swift 는 과대, Voce 는 과소 예측하는 경향이
    알려져 있고, 그래서 이 도메인에서는 둘을 섞어 쓴다 — 고장력강 카드에서는
    사실상 표준 기법이다(65 `metal_hardening.py` 도 같은 것을 갖고 있다).

    ## 적합을 좋게 하려는 것이 아니다

    혼합의 상대 RMSE 가 두 식 모두보다 나쁠 수 있다. **그 자체는 문제가 아니다** —
    목적이 적합 구간이 아니라 외삽 구간이기 때문이다. 다만 그 사실을 메모에 적어,
    "RMSE 가 나쁘니 잘못됐다" 고 읽히지 않게 한다.

    ## 가중치는 데이터가 못 정한다

    적합 구간에서는 어느 `w` 든 비슷하게 맞는다 — 그러니 RMSE 로 고를 수 없다.
    얼마나 보수적으로 볼지가 정하고, 그건 해석하는 사람이 안다. 기본값을 두지
    않는 이유가 같다.
    """

    primary: FitResult
    secondary: FitResult
    weight: float
    """`primary` 쪽 비중. 1 이면 `primary` 만, 0 이면 `secondary` 만."""
    label: str
    rmse: float
    relative_rmse: float
    r_squared: float
    max_residual: float
    point_count: int
    strain_min: float
    strain_max: float
    notes: tuple[str, ...]

    @property
    def family(self) -> str:
        return f"{self.primary.family}+{self.secondary.family}"

    @property
    def parameters(self) -> tuple[Parameter, ...]:
        """두 식의 계수를 나란히. **이름에 어느 식인지 붙인다.**

        섞여 들어오므로 `sigma_0` 만으로는 어느 쪽 것인지 구별이 안 된다. 카드가
        표에 담을 때도 같은 방식을 쓴다.
        """
        return tuple(
            replace(item, name=f"{parent.label}·{item.name}")
            for parent in (self.primary, self.secondary)
            for item in parent.parameters
        )

    def evaluate(self, plastic_strain: np.ndarray) -> np.ndarray:
        grid = np.asarray(plastic_strain, dtype=np.float64)
        return np.asarray(
            self.weight * self.primary.evaluate(grid)
            + (1.0 - self.weight) * self.secondary.evaluate(grid),
            dtype=np.float64,
        )

    def tangent(self, plastic_strain: np.ndarray) -> np.ndarray | None:
        """**접선도 같이 섞인다.** 가중평균의 미분은 미분의 가중평균이다.

        한쪽이라도 접선을 선언하지 않았으면 `None` 이다 — 반쪽만 가지고 연화를
        판정하면 없는 안전을 있다고 말하게 된다.
        """
        grid = np.asarray(plastic_strain, dtype=np.float64)
        first = self.primary.tangent(grid)
        second = self.secondary.tangent(grid)
        if first is None or second is None:
            return None
        return np.asarray(self.weight * first + (1.0 - self.weight) * second, dtype=np.float64)


def blend(
    primary: FitResult,
    secondary: FitResult,
    weight: float,
    plastic_strain: np.ndarray,
    true_stress: np.ndarray,
) -> Blended:
    """두 적합을 가중평균하고, **측정 데이터에 다시 재서** 품질을 낸다.

    부모의 RMSE 를 섞어 쓰지 않는다 — 혼합은 다른 곡선이고, 그 곡선이 데이터와
    얼마나 맞는지는 다시 재야 안다.

    **부모끼리 견주지도 않는다.** 처음에 두 부모의 평균을 기준으로 삼았더니
    `w=0.5` 에서 오차가 0 이 나왔다 — 50:50 혼합이 50:50 평균과 같은 것은 당연하고,
    그 숫자는 아무것도 말해 주지 않는다. 순환 논리였다.
    """
    if not 0.0 <= weight <= 1.0:
        raise FittingError(f"혼합 비중은 0~1 이어야 합니다: {weight}")
    if primary.family == secondary.family:
        raise FittingError(f"같은 식끼리는 섞을 수 없습니다: {primary.family}")

    strain = np.asarray(plastic_strain, dtype=np.float64)
    stress = np.asarray(true_stress, dtype=np.float64)
    if len(strain) < MIN_POINTS:
        raise FittingError(
            f"혼합을 재려면 {MIN_POINTS}점 이상이 필요한데 {len(strain)}점입니다."
        )

    label = f"{primary.label} {weight:.3g} + {secondary.label} {1.0 - weight:.3g}"
    draft = Blended(
        primary=primary,
        secondary=secondary,
        weight=weight,
        label=label,
        rmse=0.0,
        relative_rmse=0.0,
        r_squared=0.0,
        max_residual=0.0,
        point_count=len(strain),
        strain_min=float(strain[0]),
        strain_max=float(strain[-1]),
        notes=(),
    )
    errors = draft.evaluate(strain) - stress
    scale = float(np.mean(np.abs(stress))) or 1.0
    rmse = float(np.sqrt(np.mean(errors**2)))
    total = float(np.sum((stress - np.mean(stress)) ** 2))
    relative = rmse / scale

    notes = [
        f"{primary.label} 과 {secondary.label} 을 {weight:.3g} : {1.0 - weight:.3g} 로 "
        f"섞었습니다 (측정 {len(strain)}점 기준 상대 RMSE {relative * 100:.3g}%).",
        "**적합을 좋게 하려는 것이 아니라 외삽을 조정하는 것입니다** — 두 식은 적합 "
        "구간에서 비슷하고 그 밖에서 갈립니다. 혼합의 RMSE 가 두 식 모두보다 나빠도 "
        "그 자체는 문제가 아닙니다.",
        "가중치는 데이터가 정하지 못합니다. 적합 구간에서는 어느 값이든 비슷하게 "
        "맞으므로, 얼마나 보수적으로 볼지가 정합니다.",
    ]
    worse = relative > max(primary.relative_rmse, secondary.relative_rmse)
    if worse:
        notes.append(
            f"적합 구간에서는 두 식 각각보다 덜 맞습니다 "
            f"({primary.label} {primary.relative_rmse * 100:.3g}%, "
            f"{secondary.label} {secondary.relative_rmse * 100:.3g}%) — "
            f"외삽을 위해 치르는 값입니다."
        )
    if primary.tangent(strain) is None or secondary.tangent(strain) is None:
        notes.append("한쪽 식이 접선을 선언하지 않아 외삽 구간의 연화를 검사하지 못합니다.")

    return Blended(
        primary=primary,
        secondary=secondary,
        weight=weight,
        label=label,
        rmse=rmse,
        relative_rmse=relative,
        r_squared=1.0 - float(np.sum(errors**2)) / total if total > 0 else 0.0,
        max_residual=float(np.max(np.abs(errors))),
        point_count=len(strain),
        strain_min=float(strain[0]),
        strain_max=float(strain[-1]),
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class Extended:
    """측정 표를 적합식으로 늘린 결과."""

    points: tuple[tuple[float, float], ...]
    """전체 표 — 측정 구간은 그대로, 그 뒤가 식으로 만든 점이다."""
    measured_max: float
    """측정이 끝난 변형률. **여기까지가 시험이 답한 범위다.**"""
    extrapolated_to: float
    added: int
    junction_gap: float
    """이음매에서 식과 측정이 벌어진 정도(상대). 크면 그 식이 끝을 못 따라간 것이다."""
    notes: tuple[str, ...]


def extend_table(
    result: FitResult | Blended,
    plastic_strain: np.ndarray,
    true_stress: np.ndarray,
    *,
    to: float,
    points: int = 20,
) -> Extended:
    """측정 표 뒤에 적합식으로 만든 점을 잇는다.

    ## 왜 필요한가

    인장시험은 **네킹까지**만 준다(강판이면 진소성변형률 0.1~0.25). 그 뒤로는 변형이
    한 곳에 몰려서 공칭→진응력 변환식이 성립하지 않는다. 그런데 충돌 해석은 0.5~1.5,
    성형은 0.3~1.0 을 쓴다 — **시험이 답한 범위와 해석이 쓰는 범위 사이에 구멍이
    있다.**

    안 채우면 솔버가 자기 기본값으로 채운다(대개 마지막 응력을 붙들고 간다). 그것도
    **물리적 주장**이다 — 금속은 계속 경화하므로 그 구간에서 하중을 낮게 계산한다.
    "지어내지 않는 것" 이 아니라 **다른 값을 조용히 지어내는 것**이다.

    이 도메인에서 통상적으로 하는 일이고, 이름이 있다 — 유동곡선 외삽.

    ## 측정점을 지우지 않는다

    측정 구간은 **그대로 두고 뒤에만 잇는다.** 전 구간을 식으로 다시 그리면 매끄럽긴
    하지만 시험이 실제로 답한 것과 식이 답한 것이 섞여 구별이 사라진다.

    대신 이음매에서 식과 측정이 벌어진 정도를 잰다(`junction_gap`). 크면 그 식이
    곡선의 끝을 못 따라간 것이고, 그런 식으로 외삽하면 안 된다.

    ## 어디까지 늘릴지는 여기서 안 정한다

    `to` 를 받는다. 얼마까지 필요한지는 **무슨 해석을 하느냐**가 정하고 그건 해석하는
    사람이 안다. 기본값을 두면 그 값이 곧 결정이 되는데, 아무도 그것을 결정이라고
    인식하지 않는다.
    """
    if points < 2:
        raise FittingError("외삽 점은 2개 이상이어야 합니다.")
    measured = tuple(
        (float(x), float(y)) for x, y in zip(plastic_strain, true_stress, strict=True)
    )
    if not measured:
        raise FittingError("측정 표가 비어 있어 늘릴 것이 없습니다.")
    measured_max = measured[-1][0]
    if to <= measured_max:
        raise FittingError(
            f"늘릴 한계({to:.5g})가 측정 끝({measured_max:.5g}) 이하입니다 — "
            f"늘릴 구간이 없습니다."
        )

    grid = np.linspace(measured_max, to, points + 1)[1:]
    predicted = np.asarray(result.evaluate(grid), dtype=np.float64)

    notes: list[str] = [
        f"측정은 소성변형률 {measured_max:.5g} 에서 끝납니다. 그 위 {to:.5g} 까지 "
        f"{result.label} 으로 늘렸습니다 — **외삽 구간은 시험으로 검증되지 않았습니다.**"
    ]

    # **이음매가 벌어지면 그 식은 끝을 못 따라간 것이다.**
    at_junction = float(np.asarray(result.evaluate(np.asarray([measured_max])))[0])
    last = measured[-1][1]
    gap = abs(at_junction - last) / abs(last) if last else 0.0
    if gap > 0.02:
        notes.append(
            f"이음매에서 식이 측정보다 {gap * 100:.3g}% 벌어집니다 "
            f"(측정 {last / 1e6:.4g} MPa vs 식 {at_junction / 1e6:.4g} MPa) — "
            f"이 식은 곡선의 끝을 못 따라갑니다. 다른 식을 견줘 보세요."
        )

    # **외삽 구간의 연화는 식이 지어낸 것이다.** 측정 구간과 다르다.
    slope_values = result.tangent(grid)
    if slope_values is not None:
        slope = np.asarray(slope_values, dtype=np.float64)
        soft = np.isfinite(slope) & (slope < 0.0)
        if bool(np.any(soft)):
            notes.append(
                f"외삽 구간에서 접선이 음수가 됩니다(소성변형률 "
                f"{float(grid[np.argmax(soft)]):.5g} 부터) — 재료가 연화한다는 뜻이고 "
                f"해석이 발산하거나 조용히 이상한 답을 낼 수 있습니다. **측정 구간이 "
                f"아니라 식이 지어낸 모양입니다.**"
            )
    else:
        notes.append(
            f"{result.label} 은 접선 선언이 없어 외삽 구간의 연화를 검사하지 못했습니다."
        )

    if bool(np.any(np.diff(predicted) < 0)):
        notes.append(
            "외삽 구간에서 응력이 떨어집니다 — 솔버가 받지 않는 표입니다. "
            "한계를 줄이거나 다른 식을 고르세요."
        )

    return Extended(
        points=measured
        + tuple((float(x), float(y)) for x, y in zip(grid, predicted, strict=True)),
        measured_max=measured_max,
        extrapolated_to=float(to),
        added=len(grid),
        junction_gap=float(gap),
        notes=tuple(notes),
    )


def register_family(family: Family) -> Family:
    """식을 레지스트리에 등록한다. **등록하면 API·화면이 따라온다.**"""
    if family.key in FAMILIES:
        raise ValueError(f"적합식 key 중복: {family.key}")
    FAMILIES[family.key] = family
    return family


def load_builtin() -> None:
    """내장 적합식을 등록한다.

    import 부작용에 기대지 않고 명시적으로 부른다 — `processing.load_builtin`·
    `cards.load_builtin` 과 같은 이유다.
    """
    from matcore.fitting import hyperelastic  # noqa: F401


def families_for(material_family: str | None = None) -> list[Family]:
    """이 재료군에서 뜻이 있는 식.

    **금속 경화식과 고무 초탄성을 한 목록에 섞어 RMSE 로 줄 세우면 안 된다** —
    같은 물음의 답이 아니고, 축도 달라서 한 그래프에 겹쳐 그릴 수 없다.

    **아무 식도 이 재료군을 선언하지 않았으면 감추지 않는다.** 재료군 축은
    `open` 이라 사람이 `Foam` 이든 `Composite` 든 만들 수 있다(기준정보 정의
    참조). 그때 목록을 비우면 화면이 텅 비고, **왜 비었는지 알 길이 없다** —
    사람은 시스템 밖에서 계산하게 된다. 모르면 전부 주고 고르게 한다.
    """
    load_builtin()
    every = list(FAMILIES.values())
    if material_family is None:
        return every
    matched = [item for item in every if material_family in item.applies_to]
    return matched or every


def plastic_branch(
    plastic_strain: np.ndarray, true_stress: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """소성 구간만 남긴다. **경화식은 탄성 구간을 설명하지 않는다.**

    `tensile.true_plastic` 의 `clip_zero` 는 탄성 되돌림 때문에 음수로 나온
    소성변형률을 0 으로 자른다. 그래서 곡선 앞쪽에 **x 가 전부 0 인 점이 여럿**
    남는다 — 실측으로 50점 중 34점이 그랬고, 그 34점의 응력은 133~341 MPa 로
    흩어져 있었다.

    그대로 적합하면 어떤 단조 함수도 그 34점을 맞출 수 없어 잔차가 거기서 다
    나온다. 실제로 R²가 0.42 로 나왔는데, **식이 안 맞아서가 아니라 소성식에
    탄성 구간을 먹인 탓이었다.**

    마지막 0 점(항복점)만 남긴다. 첫 점을 남기면 응력이 낮은 곳을 항복강도로
    쓰게 된다.
    """
    strain = np.asarray(plastic_strain, dtype=np.float64)
    stress = np.asarray(true_stress, dtype=np.float64)
    zeros = int(np.sum(strain <= 0.0))
    if zeros <= 1:
        return strain, stress, []
    return (
        strain[zeros - 1 :],
        stress[zeros - 1 :],
        [
            f"소성변형률이 0 인 점이 {zeros}개였습니다 — 탄성 구간을 0 으로 자른 "
            f"자국입니다. 그중 마지막(항복점, {stress[zeros - 1] / 1e6:.4g} MPa)만 "
            f"남기고 {zeros - 1}점을 빼고 적합했습니다. 경화식은 탄성 구간을 "
            f"설명하지 않습니다."
        ],
    )


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
        f"{family.label} 을 {family.x_label} {float(strain[0]):.5g}~{float(strain[-1]):.5g} "
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
    # **적합은 됐는데 해석이 발산하는 계수가 있다.** 고무에서 실제로 나는 일이라
    # 식이 스스로 짚는다 — 막지는 않는다.
    if family.stability is not None:
        notes.extend(family.stability(fitted, strain))
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
