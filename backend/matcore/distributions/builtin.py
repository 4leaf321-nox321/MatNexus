"""기본 분포 셋 — 정규 · 로그정규 · 와이블.

**셋인 이유가 있다.** 재료 시험의 특징값에서 실제로 갈리는 것이 이 셋이다.

    정규      대칭. 여러 작은 오차가 더해진 것이면 이 모양이 된다
    로그정규  오른쪽으로 늘어진다. 오차가 곱해지면(두께·폭이 함께 흔들리면) 이쪽
    와이블    왼쪽 꼬리가 짧다. **가장 약한 곳이 정한다** — 파괴가 그렇다

셋 다 2-파라미터다. 위치 파라미터를 풀면 3-파라미터가 되는데, 우리 n(10~20)에서
그것은 **표본을 외우는 것**이지 모형이 아니다. 로그정규·와이블의 `loc` 을 0 으로
고정하는 이유가 그것이다.

`scipy.stats` 를 얇게 감싼다. 직접 MLE 를 짜지 않는 이유: 와이블의 형상
파라미터는 닫힌 해가 없어 반복으로 풀어야 하고, 그 반복을 우리가 다시 짜면
**검증되지 않은 수치 코드가 하나 더 는다.** 대신 무엇을 어떻게 고정했는지는
여기서 명시한다.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore.distributions import Distribution, register


def _norm_fit(values: np.ndarray) -> np.ndarray:
    from scipy import stats

    mu, sigma = stats.norm.fit(values)
    return np.asarray([mu, sigma], dtype=np.float64)


def _norm_logpdf(parameters: np.ndarray, values: np.ndarray) -> Any:
    from scipy import stats

    return stats.norm.logpdf(values, loc=parameters[0], scale=parameters[1])


def _norm_cdf(parameters: np.ndarray, values: np.ndarray) -> Any:
    from scipy import stats

    return stats.norm.cdf(values, loc=parameters[0], scale=parameters[1])


def _norm_ppf(parameters: np.ndarray, probability: float) -> Any:
    from scipy import stats

    return stats.norm.ppf(probability, loc=parameters[0], scale=parameters[1])


def _norm_sample(
    parameters: np.ndarray, count: int, generator: np.random.Generator
) -> np.ndarray:
    return np.asarray(generator.normal(parameters[0], parameters[1], count), dtype=np.float64)


def _lognorm_fit(values: np.ndarray) -> np.ndarray:
    from scipy import stats

    # **`floc=0` 으로 고정한다.** 풀면 3-파라미터가 되는데, 위치가 자유로우면
    # 최솟값 바로 아래에 붙어 우도가 발산하는 방향으로 간다 — 표본을 외운다.
    shape, _loc, scale = stats.lognorm.fit(values, floc=0)
    return np.asarray([shape, scale], dtype=np.float64)


def _lognorm_logpdf(parameters: np.ndarray, values: np.ndarray) -> Any:
    from scipy import stats

    return stats.lognorm.logpdf(values, parameters[0], loc=0, scale=parameters[1])


def _lognorm_cdf(parameters: np.ndarray, values: np.ndarray) -> Any:
    from scipy import stats

    return stats.lognorm.cdf(values, parameters[0], loc=0, scale=parameters[1])


def _lognorm_ppf(parameters: np.ndarray, probability: float) -> Any:
    from scipy import stats

    return stats.lognorm.ppf(probability, parameters[0], loc=0, scale=parameters[1])


def _lognorm_sample(
    parameters: np.ndarray, count: int, generator: np.random.Generator
) -> np.ndarray:
    # ln X ~ N(ln scale, shape). scipy 의 매개변수화를 그대로 따른다.
    return np.asarray(
        generator.lognormal(np.log(parameters[1]), parameters[0], count), dtype=np.float64
    )


def _weibull_fit(values: np.ndarray) -> np.ndarray:
    from scipy import stats

    shape, _loc, scale = stats.weibull_min.fit(values, floc=0)
    return np.asarray([shape, scale], dtype=np.float64)


def _weibull_logpdf(parameters: np.ndarray, values: np.ndarray) -> Any:
    from scipy import stats

    return stats.weibull_min.logpdf(values, parameters[0], loc=0, scale=parameters[1])


def _weibull_cdf(parameters: np.ndarray, values: np.ndarray) -> Any:
    from scipy import stats

    return stats.weibull_min.cdf(values, parameters[0], loc=0, scale=parameters[1])


def _weibull_ppf(parameters: np.ndarray, probability: float) -> Any:
    from scipy import stats

    return stats.weibull_min.ppf(probability, parameters[0], loc=0, scale=parameters[1])


def _weibull_sample(
    parameters: np.ndarray, count: int, generator: np.random.Generator
) -> np.ndarray:
    return np.asarray(
        parameters[1] * generator.weibull(parameters[0], count), dtype=np.float64
    )


def load() -> None:
    """등록한다. `matcore.distributions.load_builtin` 이 부른다."""
    register(
        Distribution(
            key="normal",
            label="정규",
            parameter_names=("mu", "sigma"),
            parameter_labels=("평균", "표준편차"),
            fit=_norm_fit,
            logpdf=_norm_logpdf,
            cdf=_norm_cdf,
            ppf=_norm_ppf,
            sample=_norm_sample,
            describe="대칭. 여러 작은 오차가 더해진 결과라면 이 모양이 된다.",
        )
    )
    register(
        Distribution(
            key="lognormal",
            label="로그정규",
            parameter_names=("sigma_log", "scale"),
            parameter_labels=("로그 표준편차", "척도(중앙값)"),
            fit=_lognorm_fit,
            logpdf=_lognorm_logpdf,
            cdf=_lognorm_cdf,
            ppf=_lognorm_ppf,
            sample=_lognorm_sample,
            describe="오른쪽으로 늘어진다. 오차가 더해지지 않고 곱해질 때의 모양이다.",
            positive_only=True,
        )
    )
    register(
        Distribution(
            key="weibull",
            label="와이블",
            parameter_names=("shape", "scale"),
            parameter_labels=("형상 m", "척도"),
            fit=_weibull_fit,
            logpdf=_weibull_logpdf,
            cdf=_weibull_cdf,
            ppf=_weibull_ppf,
            sample=_weibull_sample,
            describe=(
                "가장 약한 곳이 정하는 모양. 파괴·수명에 쓴다 — 형상 m 이 클수록 "
                "흩어짐이 작다."
            ),
            positive_only=True,
        )
    )
