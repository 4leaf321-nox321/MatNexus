"""스칼라 분포 적합 — **흩어짐에 모양을 붙인다.**

`statistics` 는 평균·SD·CV 를 낸다. 그것은 흩어짐이 **얼마나** 큰지를 말하고,
여기서는 흩어짐이 **어떤 모양**인지를 묻는다. 다른 물음이다.

왜 필요한가. 시편 12개의 최대응력이 평균 620 MPa, CV 4% 라고 하자. 설계에서
알고 싶은 것은 대개 *"하위 5% 가 얼마인가"* 인데, 그 답은 모양이 정한다 —
정규면 대칭이라 평균에서 1.64σ 아래이고, 와이블이면 왼쪽 꼬리가 더 길다.
**같은 평균과 같은 SD 에서 하위 5% 가 다르게 나온다.**

## 곡선이 아니라 값 여럿을 받는다

`matcore.fitting` 의 `Family` 는 `(x, y)` 를 받는다 — 곡선에 식을 얹는 일이다.
분포는 **x 가 없다.** 값 n 개가 전부이고, 맞추는 것은 그 값들이 어디서 나왔을
법한 확률분포다.

그래서 레지스트리를 따로 뒀다. `Family` 에 `x` 를 선택으로 만들어 한 레지스트리에
욱여넣을 수도 있었지만, 그러면 **Voce 와 Weibull 이 한 목록에서 RMSE 로 줄
서게 된다** — `applies_to` 로 막는 것과 같은 종류의 실수다. 곡선 적합과 분포
적합은 같은 물음의 답이 아니다.

## "적합 실패" 와 "적합 대상 아님" 을 가른다

한 칸에 넣으면 나중에 못 가른다. 시편 5개는 실패한 것이 아니라 **애초에 물을 수
없는 것**이고(`not_eligible`), 그 둘을 섞으면 *"와이블이 안 맞는 재료"* 와
*"시편이 모자란 재료"* 가 같은 색으로 보인다.

    not_eligible   표본이 모자라 물을 수 없다      n < 8
    failed         물었는데 답이 안 나왔다          수렴 실패·정의역 벗어남
    succeeded      답이 나왔다                     n >= 8

관측값도 마찬가지다. **없는 것과 못 쓰는 것을 가른다.**

    observed       쓴 값
    missing        그 시편에 그 항목이 없다
    non_finite     있는데 NaN·inf 다
    censored       정의역 밖이다 (로그정규·와이블은 양수만)

## 견주는 방법 — AICc 와 Anderson-Darling

**둘 다 필요하고, 둘이 다른 것을 본다.**

AICc 는 *"후보들 중 어느 것이 낫나"* 를 답한다. 상대적이라 **전부 안 맞아도 하나는
1등이 된다.** 표본이 작을 때 AIC 는 파라미터가 많은 쪽으로 치우쳐서, 유한표본
보정을 쓴다 — 우리 n 은 대개 10~20 이라 이 보정이 실제로 갈린다.

Anderson-Darling 은 *"이것이 맞기는 하나"* 를 답한다. 절대적이다. 꼬리에 가중치를
크게 두므로 하위 5% 를 묻는 이 자리에 맞다.

## 모자랄 때도 빈손으로 두지 않는다

n < 8 이면 분포는 못 맞춘다. 그렇다고 아무것도 못 말하는 것은 아니다 —
**분포를 가정하지 않고도** 말할 수 있는 것이 있다(`empirical`).

    n·최소·사분위·중앙·최대        가정 없이 그냥 있는 값
    최소값이 덮는 분위수            순서통계량. `1 - (1-p)^n = 신뢰도`

세 시편의 최소값은 **63% 분위수의 95% 하한**이다 — 하위 5% 근처에도 못 간다.
그 사실 자체가 값진 정보다: 「데이터가 모자라다」 가 아니라 **「지금 데이터로는
여기까지 말할 수 있고, 하위 5% 를 분포 없이 말하려면 59개가 필요하다」** 로
바뀐다. 앞엣말은 막다른 길이고 뒤엣말은 판단이다.

분포를 맞추는 이유가 여기 있다. 59개를 재는 대신 **모양을 가정해서** 꼬리를
외삽하는 것이고, 그 가정이 맞는지를 AD 검정이 묻는다.

p 값은 **모수 부트스트랩**으로 낸다. 파라미터를 데이터에서 추정했으므로 표준
임계값표를 쓸 수 없다 — 추정한 만큼 A² 가 작아지고, 그 표를 쓰면 안 맞는 분포도
통과한다. 적합한 분포에서 표본을 다시 뽑아 매번 다시 적합하고, 그 A² 분포에서
관측값의 자리를 본다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

#: 이보다 적으면 묻지 않는다. **답이 안 나오는 것이 아니라 물음이 성립하지 않는다.**
#:
#: 2-파라미터 분포에 7점을 맞추면 숫자는 나온다. 그런데 그 숫자로 하위 5% 를
#: 말하면 표본 밖을 통째로 지어내는 것이다 — 7점의 최솟값이 이미 12.5 백분위쯤이라
#: 5% 는 관측된 적이 없다.
MIN_ELIGIBLE = 8

#: 이 아래에서는 답을 내되 **믿을 만하지 않다고 말한다.**
WARN_BELOW = 20

#: 부트스트랩 반복. 999 인 이유는 p 가 `(1 + 초과 횟수) / (B + 1)` 이라
#: B=999 면 최소 p 가 0.001 로 딱 떨어지기 때문이다.
BOOTSTRAP = 999

#: 한 번에 이 이상은 안 받는다. 부트스트랩이 n 에 비례해 무거워진다.
MAX_SAMPLES = 500

#: 비모수 하한을 말할 때의 신뢰도. 설계 관행이 95% 다.
NONPARAMETRIC_CONFIDENCE = 0.95

#: 설계가 실제로 묻는 분위수. 「하위 5%」.
DESIGN_QUANTILE = 0.05


class DistributionError(Exception):
    """물음 자체가 성립하지 않을 때. 적합 실패는 이것이 아니라 `Candidate.status` 다."""


@dataclass(frozen=True)
class Distribution:
    """맞춰 볼 분포 한 종류.

    `matcore.fitting.Family` 와 자리는 같지만 **받는 것이 다르다** — 곡선의
    `(x, y)` 가 아니라 값 배열 하나다.
    """

    key: str
    label: str
    parameter_names: tuple[str, ...]
    parameter_labels: tuple[str, ...]
    """사람이 읽는 이름. `sigma` 를 그대로 보이면 응력과 헷갈린다."""

    fit: Any
    """`(값 배열) -> 파라미터 배열`. 최대우도 추정."""
    logpdf: Any
    """`(파라미터, 값) -> 로그밀도`. AICc 의 우도가 여기서 나온다."""
    cdf: Any
    """`(파라미터, 값) -> 누적확률`. Anderson-Darling 이 이것을 쓴다."""
    ppf: Any
    """`(파라미터, 확률) -> 값`. **분위수가 이 모듈의 쓸모다** — 하위 5% 를 묻는
    자리이므로, 파라미터만 주고 끝내면 사람이 다시 계산해야 한다."""
    sample: Any
    """`(파라미터, 개수, 난수기) -> 값 배열`. 부트스트랩이 쓴다."""

    describe: str
    positive_only: bool = False
    """양수만 받는가. 로그정규·와이블이 그렇다 — 0 이하는 `censored` 로 뺀다."""


DISTRIBUTIONS: dict[str, Distribution] = {}


def register(distribution: Distribution) -> Distribution:
    """분포 하나를 등록한다. **확장 폴더에서도 부를 수 있다**(ADR 0013)."""
    if distribution.key in DISTRIBUTIONS:
        raise ValueError(f"분포 key 중복: {distribution.key}")
    DISTRIBUTIONS[distribution.key] = distribution
    return distribution


@dataclass(frozen=True)
class Observation:
    """값 하나가 어떻게 됐는가. **없는 것과 못 쓰는 것을 가른다.**"""

    index: int
    """부른 쪽이 준 목록에서의 자리. 어느 시편인지 되짚는 데 쓴다."""
    status: str
    """`observed` · `missing` · `non_finite` · `censored`"""
    value: float | None


@dataclass(frozen=True)
class Candidate:
    """분포 하나를 맞춰 본 결과."""

    key: str
    label: str
    status: str
    """`succeeded` · `not_eligible` · `failed`. **셋을 한 칸에 넣지 않는다.**"""
    reason: str | None = None
    """`not_eligible`·`failed` 일 때 왜인지. 성공이면 `None`."""

    parameters: tuple[float, ...] = ()
    parameter_names: tuple[str, ...] = ()
    parameter_labels: tuple[str, ...] = ()

    log_likelihood: float | None = None
    aicc: float | None = None
    """유한표본 보정 AIC. **작을수록 낫다.** 후보끼리만 뜻이 있다."""
    delta_aicc: float | None = None
    """1등과의 차이. 관례상 2 미만이면 구별 못 하는 것으로 본다."""

    anderson_darling: float | None = None
    p_value: float | None = None
    """모수 부트스트랩 p. **작으면 이 분포가 아니라는 뜻이다.**

    큰 p 가 "맞다" 는 증명은 아니다 — 표본이 작으면 무엇으로도 안 갈린다."""

    quantiles: dict[str, float] = field(default_factory=dict)
    """`p05`·`p50`·`p95`. **이 모듈의 쓸모가 여기 있다.**"""


@dataclass(frozen=True)
class Empirical:
    """**분포를 가정하지 않은** 요약. n 이 몇이든 낸다.

    분포 적합이 못 돌 때(n < 8) 화면이 빈손이 되지 않게 하는 것이 첫 목적이고,
    돌 때도 값이 있다 — 적합한 분위수가 관측값에서 얼마나 떨어졌는지 견줄
    자리가 된다.
    """

    count: int
    minimum: float | None
    q1: float | None
    median: float | None
    q3: float | None
    maximum: float | None

    covered_quantile: float | None
    """관측 **최소값**이 덮는 분위수. `1 - (1-p)^n = 신뢰도` 를 p 에 대해 푼 것.

    「최소값 아래에 모집단의 p 이하가 있다」 를 95% 신뢰로 말할 수 있다는 뜻이다.
    n=3 이면 0.63, n=20 이면 0.14 — **작은 n 이 꼬리를 못 본다는 사실 자체**를
    수로 보여 준다.
    """

    needed_for_design: int | None
    """하위 5% 를 **분포 없이** 말하려면 몇 개가 필요한가. 95% 신뢰로 59개다."""

    confidence: float = NONPARAMETRIC_CONFIDENCE


def covered_quantile(
    count: int, *, confidence: float = NONPARAMETRIC_CONFIDENCE
) -> float | None:
    """관측 최소값이 덮는 분위수. 표본이 없으면 `None`.

    순서통계량이다. 최소값 `X(1)` 이 p 분위수보다 작을 확률은
    `1 - (1-p)^n` 이므로, 그것을 신뢰도로 놓고 p 를 푼다:

        p = 1 - (1 - 신뢰도)^(1/n)

    **분포를 가정하지 않는다.** 그래서 작은 n 에서 정직하게 약하다 — 그 약함이
    곧 「지금 데이터로 꼬리를 말할 수 없다」 는 답이다.
    """
    if count < 1:
        return None
    return float(1.0 - (1.0 - confidence) ** (1.0 / count))


def needed_for(
    quantile: float = DESIGN_QUANTILE, *, confidence: float = NONPARAMETRIC_CONFIDENCE
) -> int:
    """그 분위수를 **분포 없이** 말하려면 표본이 몇 개여야 하는가.

    위 식을 n 에 대해 푼다: `n >= ln(1 - 신뢰도) / ln(1 - p)`. 하위 5% 를 95%
    신뢰로 말하려면 59개다 — **분포를 맞추는 이유가 이 수다.**
    """
    return math.ceil(math.log(1.0 - confidence) / math.log(1.0 - quantile))


def empirical(values: Sequence[float] | np.ndarray) -> Empirical:
    """가정 없는 요약. **비어 있어도 자료형은 돌려준다** — 화면이 갈리지 않게."""
    data = np.asarray([float(v) for v in values], dtype=np.float64)
    count = int(data.size)
    if count == 0:
        return Empirical(
            count=0,
            minimum=None,
            q1=None,
            median=None,
            q3=None,
            maximum=None,
            covered_quantile=None,
            needed_for_design=needed_for(),
        )
    # `linear` 는 numpy 기본이자 대부분의 통계 도구가 쓰는 정의다. 표본이 적을 때
    # 정의마다 사분위가 갈리므로 **무엇을 썼는지가 중요하다.**
    q1, median, q3 = (float(v) for v in np.quantile(data, [0.25, 0.5, 0.75], method="linear"))
    return Empirical(
        count=count,
        minimum=float(np.min(data)),
        q1=q1,
        median=median,
        q3=q3,
        maximum=float(np.max(data)),
        covered_quantile=covered_quantile(count),
        needed_for_design=needed_for(),
    )


@dataclass(frozen=True)
class Report:
    """한 항목에 대한 답 한 벌."""

    count: int
    """실제로 쓴 값의 개수. 준 값의 개수가 아니다."""
    observations: tuple[Observation, ...]
    candidates: tuple[Candidate, ...]
    """AICc 오름차순. 실패한 것도 **목록에 남는다** — 안 뜨면 "안 해 봤다" 로 읽힌다."""
    best: str | None
    """1등의 key. 아무것도 성공 못 했으면 `None`."""
    empirical: Empirical | None = None
    """**가정 없는 요약.** 적합이 하나도 못 돌아도 이것은 늘 있다."""
    notes: tuple[str, ...] = ()


def _sift(
    values: Sequence[float | None], *, positive_only: bool
) -> tuple[np.ndarray, list[Observation]]:
    """쓸 값과 못 쓴 값을 가른다."""
    kept: list[float] = []
    marks: list[Observation] = []
    for index, raw in enumerate(values):
        if raw is None:
            marks.append(Observation(index=index, status="missing", value=None))
            continue
        number = float(raw)
        if not math.isfinite(number):
            marks.append(Observation(index=index, status="non_finite", value=None))
            continue
        if positive_only and number <= 0:
            marks.append(Observation(index=index, status="censored", value=number))
            continue
        marks.append(Observation(index=index, status="observed", value=number))
        kept.append(number)
    return np.asarray(kept, dtype=np.float64), marks


def _aicc(log_likelihood: float, count: int, parameters: int) -> float | None:
    """AIC + 유한표본 보정.

    **n - k - 1 이 0 이하면 보정이 발산한다.** 그때는 AICc 를 내지 않는다 —
    큰 수를 돌려주면 "이 분포가 나쁘다" 로 읽히는데 사실은 "잴 수 없다" 다.
    """
    remaining = count - parameters - 1
    if remaining <= 0:
        return None
    return (
        2.0 * parameters
        - 2.0 * log_likelihood
        + (2.0 * parameters * (parameters + 1)) / remaining
    )


def _anderson_darling(sorted_probabilities: np.ndarray) -> float:
    """A². 값이 아니라 **누적확률**을 받는다 — 어느 분포든 같은 식이다.

    확률이 0 이나 1 에 딱 붙으면 로그가 발산한다. 배정밀도에서 실제로 일어나므로
    (와이블의 오른쪽 꼬리) 아주 조금 안쪽으로 밀어 넣는다.
    """
    count = len(sorted_probabilities)
    clipped = np.clip(sorted_probabilities, 1e-12, 1.0 - 1e-12)
    index = np.arange(1, count + 1)
    total = np.sum((2.0 * index - 1.0) * (np.log(clipped) + np.log1p(-clipped[::-1])))
    return float(-count - total / count)


def _statistic(
    distribution: Distribution, parameters: np.ndarray, values: np.ndarray
) -> float:
    return _anderson_darling(np.sort(distribution.cdf(parameters, values)))


def _bootstrap_p(
    distribution: Distribution,
    parameters: np.ndarray,
    observed: float,
    count: int,
    *,
    rounds: int,
    seed: int,
) -> float | None:
    """모수 부트스트랩 p 값.

    **표준 임계값표를 쓸 수 없다.** 파라미터를 데이터에서 추정했으므로 A² 가
    그만큼 작아지고, 표를 쓰면 안 맞는 분포도 통과한다. 적합한 분포에서 표본을
    다시 뽑아 **매번 다시 적합해야** 그 편향이 재현된다 — 참 파라미터를 그대로
    쓰면 부트스트랩의 뜻이 없어진다.
    """
    generator = np.random.default_rng(seed)
    exceeded = 0
    usable = 0
    for _ in range(rounds):
        drawn = distribution.sample(parameters, count, generator)
        try:
            refitted = distribution.fit(drawn)
            simulated = _statistic(distribution, refitted, drawn)
        except Exception:
            # 시뮬레이션 한 번이 실패하는 것은 흔하다. 전부 실패하면 p 를 안 낸다.
            continue
        usable += 1
        if simulated >= observed:
            exceeded += 1
    if usable == 0:
        return None
    return (1.0 + exceeded) / (usable + 1.0)


def fit_all(
    values: Sequence[float | None],
    *,
    keys: tuple[str, ...] | None = None,
    bootstrap: int = BOOTSTRAP,
    seed: int = 20260824,
) -> Report:
    """후보 분포를 나란히 맞춘다. **고르지 않고 견줘 준다.**

    경화식과 같은 태도다(ADR 0009) — 1등만 돌려주면 2등과 얼마나 갈렸는지가
    사라지고, 그 차이가 작을 때는 **데이터가 정한 것이 아니라 우리가 정한 것**이
    된다.

    `seed` 를 받는 이유: 부트스트랩 p 는 난수에 따라 흔들린다. 같은 데이터에서
    다른 p 가 나오면 "재현이 안 된다" 가 되고, 그것은 이 값의 근거를 무너뜨린다.
    """
    load_builtin()
    chosen = keys or tuple(sorted(DISTRIBUTIONS))
    unknown = [key for key in chosen if key not in DISTRIBUTIONS]
    if unknown:
        known = ", ".join(sorted(DISTRIBUTIONS))
        raise DistributionError(f"모르는 분포입니다: {', '.join(unknown)}. 있는 것: {known}")
    if len(values) > MAX_SAMPLES:
        raise DistributionError(
            f"한 번에 {MAX_SAMPLES}개까지입니다 (지금 {len(values)}개). "
            f"부트스트랩이 표본 수에 비례해 무거워집니다."
        )

    notes: list[str] = []
    candidates: list[Candidate] = []
    # 관측 표시는 **양수 제약이 없는 기준**으로 한 벌 낸다. 분포마다 다른 표시를
    # 내면 같은 시편이 표마다 다르게 보인다 — censored 는 후보의 사유로 말한다.
    _, marks = _sift(values, positive_only=False)
    usable = np.asarray(
        [mark.value for mark in marks if mark.status == "observed"], dtype=np.float64
    )
    count = len(usable)

    dropped = len(values) - count
    if dropped:
        notes.append(
            f"쓸 수 없는 값 {dropped}개를 뺐습니다 — 어느 것인지는 관측 표에 있습니다."
        )

    for key in chosen:
        distribution = DISTRIBUTIONS[key]
        data, _ = _sift(
            [mark.value if mark.status == "observed" else None for mark in marks],
            positive_only=distribution.positive_only,
        )
        candidates.append(_one(distribution, data, bootstrap=bootstrap, seed=seed))

    scored = [item for item in candidates if item.aicc is not None]
    best: str | None = None
    if scored:
        floor = min(item.aicc for item in scored if item.aicc is not None)
        candidates = [
            replace(item, delta_aicc=item.aicc - floor) if item.aicc is not None else item
            for item in candidates
        ]
        best = next(item.key for item in candidates if item.aicc == floor)

    candidates.sort(key=lambda item: (item.aicc is None, item.aicc or 0.0))

    summary = empirical(usable)
    if count < MIN_ELIGIBLE:
        notes.append(
            f"쓸 수 있는 값이 {count}개입니다. 분포를 맞추려면 {MIN_ELIGIBLE}개 이상이어야 "
            f"합니다 — 모자란 것이지 안 맞는 것이 아닙니다."
        )
        if summary.covered_quantile is not None:
            # **빈손으로 돌려보내지 않는다.** 분포 없이도 말할 수 있는 것이 있고,
            # 그 말의 약함 자체가 「지금 데이터로 꼬리를 못 본다」 는 답이다.
            notes.append(
                f"그래도 **가정 없이** 말할 수 있는 것이 있습니다 — 관측 최소값은 "
                f"{summary.covered_quantile:.0%} 분위수의 "
                f"{NONPARAMETRIC_CONFIDENCE:.0%} 신뢰 하한입니다(순서통계량). "
                f"하위 {DESIGN_QUANTILE:.0%} 를 분포 없이 말하려면 "
                f"{summary.needed_for_design}개가 필요합니다 — **분포를 맞추는 이유가 "
                f"그 수입니다.** {MIN_ELIGIBLE}개부터 모양을 가정해 꼬리를 외삽합니다."
            )
    elif count < WARN_BELOW:
        notes.append(
            f"값이 {count}개입니다. 답은 냈지만 **어느 분포인지 가려낼 힘이 없습니다** — "
            f"{WARN_BELOW}개는 돼야 p 값이 후보를 갈라 줍니다. 하위 5% 는 특히 "
            f"조심해서 쓰세요."
        )
    if best is not None:
        near = [
            item.label
            for item in candidates
            if item.key != best and item.delta_aicc is not None and item.delta_aicc < 2.0
        ]
        if near:
            notes.append(
                f"{', '.join(near)} 도 AICc 차이가 2 미만이라 **이 데이터로는 구별되지 "
                f"않습니다.** 1등을 고르는 것은 데이터가 아니라 사람입니다."
            )

    return Report(
        count=count,
        observations=tuple(marks),
        candidates=tuple(candidates),
        best=best,
        empirical=summary,
        notes=tuple(notes),
    )


def _one(
    distribution: Distribution, values: np.ndarray, *, bootstrap: int, seed: int
) -> Candidate:
    """분포 하나. **실패해도 목록에 남는다.**"""
    blank = Candidate(
        key=distribution.key,
        label=distribution.label,
        status="failed",
        parameter_names=distribution.parameter_names,
        parameter_labels=distribution.parameter_labels,
    )
    count = len(values)
    if count < MIN_ELIGIBLE:
        return replace(
            blank,
            status="not_eligible",
            reason=(
                f"쓸 수 있는 값이 {count}개입니다 ({MIN_ELIGIBLE}개 이상 필요). "
                f"적합에 실패한 것이 아니라 **물음이 성립하지 않습니다.**"
            ),
        )

    try:
        parameters = np.asarray(distribution.fit(values), dtype=np.float64)
        if not np.all(np.isfinite(parameters)):
            raise ValueError("파라미터가 유한하지 않습니다.")
        log_likelihood = float(np.sum(distribution.logpdf(parameters, values)))
        if not math.isfinite(log_likelihood):
            raise ValueError("로그우도가 유한하지 않습니다.")
        statistic = _statistic(distribution, parameters, values)
    except Exception as caught:
        return replace(blank, reason=str(caught) or type(caught).__name__)

    return replace(
        blank,
        status="succeeded",
        parameters=tuple(float(one) for one in parameters),
        log_likelihood=log_likelihood,
        aicc=_aicc(log_likelihood, count, len(parameters)),
        anderson_darling=statistic,
        p_value=_bootstrap_p(
            distribution, parameters, statistic, count, rounds=bootstrap, seed=seed
        ),
        quantiles={
            name: float(distribution.ppf(parameters, probability))
            for name, probability in (("p05", 0.05), ("p50", 0.50), ("p95", 0.95))
        },
    )


_LOADED = False


def load_builtin() -> None:
    """기본 분포 셋을 등록한다. 두 번 불러도 안전하다."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from matcore.distributions import builtin

    builtin.load()


def clear() -> None:
    """시험용. 등록을 비운다."""
    global _LOADED
    DISTRIBUTIONS.clear()
    _LOADED = False
