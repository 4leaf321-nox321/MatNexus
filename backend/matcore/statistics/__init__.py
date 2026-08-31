"""반복 시편의 통계 — **여러 시편이 같은 것을 말하는가.**

시편 하나의 물성은 그 시편의 물성이다. 재료의 물성이라고 말하려면 여러 번 재고
그 흩어짐을 봐야 한다. 이 패키지는 그 흩어짐을 숫자로 낸다.

## 이 패키지가 지키는 것

**정렬을 대신 하지 않는다.** 시편들의 x 격자가 다르면 계산하지 않고 거부한다.
평균을 내려면 같은 x 에서 비교해야 하는데, 통계가 조용히 보간하면 **그 보간이
결과에 섞이고 아무도 모른다.** 정렬은 처리(`curve.resample`)의 일이다.

다만 **거부하고 끝내지 않는다.** 어디까지가 공통 구간인지 계산해 알려 준다 —
그 값이 있어야 사람이 레시피를 고칠 수 있다.

**이상치를 버리지 않는다.** 표시만 한다. 시편 하나가 낮은 것이 재료 특성인지
시험 실수인지는 곡선을 본 사람이 안다. 65 의 같은 모듈이 두 시편이 어긋났을 때
**양쪽 다** 검토 대상으로 표시하는 것과 같은 판단이다 — 둘만으로는 어느 쪽이
이상한지 알 수 없다.

**평균과 중앙값을 함께 낸다.** 이상치가 있을 때 중앙값이 낫고, 어느 것을 쓸지는
쓰는 쪽이 정한다. MAD·IQR 을 함께 두는 이유도 같다 — 표준편차는 이상치 하나에
크게 휘둘린다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

#: 표본이 이보다 적으면 흩어짐을 말할 수 없다.
MIN_SAMPLES = 2

#: 이보다 많으면 배치가 잘못 묶인 것이다 — 한 재료·방향에 시편 50개는 없다.
MAX_SAMPLES = 50

#: 변동계수·이상치를 낼 수 있는 최소 표본.
#:
#: **2개로는 이상치를 판정할 수 없다.** 둘이 다르면 어느 쪽이 이상한지 알 방법이
#: 없다(65 도 같은 이유로 양쪽을 다 표시한다). CV 도 표본 2개에서는 뜻이 약하다.
MIN_FOR_SPREAD = 3

#: modified z-score 의 기본 임계. 관례값이다.
DEFAULT_OUTLIER_THRESHOLD = 3.5

#: 정규분포에서 MAD 를 표준편차로 맞추는 계수(0.6745 = Φ⁻¹(0.75)).
MODIFIED_Z_SCALE = 0.6745

#: 양측 95% 신뢰구간의 t 값. 인덱스는 자유도(n-1) - 1.
#:
#: **정규분포가 아니라 t 를 쓰는 이유:** 시편은 3~10개다. 그 수에서 정규분포를
#: 쓰면 신뢰구간이 실제보다 좁게 나온다 — n=3 이면 4.30 이어야 할 것이 1.96 이 된다.
_T_975 = (
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
    2.040,
    2.037,
    2.035,
    2.032,
    2.030,
    2.028,
    2.026,
    2.024,
    2.023,
    2.021,
    2.020,
    2.018,
    2.017,
    2.015,
    2.014,
    2.013,
    2.012,
    2.011,
    2.010,
)


class StatisticsError(Exception):
    """이 표본으로는 통계를 낼 수 없다.

    메시지는 **사용자가 읽는다.** 무엇이 모자라고 무엇을 하면 되는지 적는다 —
    '통계 실패' 만 남기면 다음 사람이 데이터를 직접 들여다봐야 한다.
    """


@dataclass(frozen=True)
class ScalarStats:
    """값 하나에 대한 흩어짐.

    **평균만 내지 않는다.** 중앙값·MAD·IQR 을 함께 두는 이유: 표준편차는 이상치
    하나에 크게 휘둘리는데, 시편 5개 중 하나가 잘못 물렸으면 정확히 그 일이 난다.
    두 벌을 나란히 두면 "평균과 중앙값이 많이 다르다" 는 것 자체가 신호가 된다.
    """

    count: int
    mean: float
    sample_sd: float
    """표본표준편차(n-1). **시편은 표본이다** — 그 재료로 만들 수 있는 모든
    시편이 아니라 그중 몇 개를 잰 것이므로 n 이 아니라 n-1 로 나눈다."""
    median: float
    mad: float
    """중앙값 절대편차. 이상치에 안 휘둘리는 흩어짐."""
    iqr: float
    minimum: float
    maximum: float
    coefficient_of_variation: float | None
    """`sd / |mean|`. 평균이 0 이면 뜻이 없어 `None` 이다. 표본이 3 미만이어도 낸다 —
    다만 그 수에서 CV 를 믿을 수 없다는 것은 쓰는 쪽이 안다(`count` 를 함께 준다)."""
    ci95_low: float | None
    ci95_high: float | None
    """평균의 95% 신뢰구간. 표본이 2 미만이면 없다."""


@dataclass(frozen=True)
class Outlier:
    """이상치 **후보**. 버리지 않는다."""

    index: int
    """표본 목록에서의 자리. 호출부가 어느 시편인지 되짚는다."""
    value: float
    score: float | None
    """modified z-score. MAD 가 0 이면 계산할 수 없어 `None` 이다."""
    reason: str


@dataclass(frozen=True)
class CurvePointStats:
    x: float
    y: ScalarStats


@dataclass(frozen=True)
class GridCheck:
    """시편들의 x 격자가 통계를 낼 수 있는 상태인가.

    **거부하고 끝내지 않는다.** 공통 구간을 함께 준다 — 그 값이 있어야 사람이
    `curve.resample` 의 구간을 정해 다시 처리할 수 있다.
    """

    ok: bool
    reason: str
    common_start: float | None = None
    common_end: float | None = None
    shortest_index: int | None = None
    """공통 구간의 끝을 정한 시편. "누구 때문에 여기까지인가" 를 답한다."""


def scalar_stats(values: list[float]) -> ScalarStats:
    """값 목록의 흩어짐. 표본이 모자라면 거부한다."""
    count = len(values)
    if count < MIN_SAMPLES:
        raise StatisticsError(
            f"통계를 내려면 시험이 {MIN_SAMPLES}건 이상이어야 합니다 (지금 {count}건)."
        )
    if count > MAX_SAMPLES:
        raise StatisticsError(
            f"한 번에 {MAX_SAMPLES}건까지입니다 (지금 {count}건). "
            f"묶음이 잘못됐는지 확인하세요 — 한 재료·방향에 "
            f"시편 {MAX_SAMPLES}개는 흔치 않습니다."
        )
    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise StatisticsError("유한하지 않은 값이 섞여 있습니다.")

    mean = float(np.mean(array))
    # ddof=1 — 표본표준편차. 시편은 표본이다.
    sample_sd = float(np.std(array, ddof=1))
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    iqr = float(np.percentile(array, 75) - np.percentile(array, 25))

    half_width = _T_975[count - 2] * sample_sd / math.sqrt(count) if count >= 2 else None
    return ScalarStats(
        count=count,
        mean=mean,
        sample_sd=sample_sd,
        median=median,
        mad=mad,
        iqr=iqr,
        minimum=float(np.min(array)),
        maximum=float(np.max(array)),
        coefficient_of_variation=(sample_sd / abs(mean) if mean != 0 else None),
        ci95_low=(mean - half_width) if half_width is not None else None,
        ci95_high=(mean + half_width) if half_width is not None else None,
    )


def outliers(
    values: list[float], *, threshold: float = DEFAULT_OUTLIER_THRESHOLD
) -> list[Outlier]:
    """이상치 **후보**를 표시한다. 아무것도 버리지 않는다.

    평균·표준편차 대신 **중앙값·MAD** 를 쓴다. 이상치가 평균을 끌고 가므로,
    평균 기준으로 재면 정작 그 이상치가 안 걸린다.

    **MAD 가 0 인 경우가 실제로 온다.** 시편 5개 중 4개가 정확히 같고 하나만
    다르면 중앙값 절대편차가 0 이고 z 가 무한대가 된다. 그때는 점수를 내지 않고
    "다르다" 는 사실만 표시한다 — 65 도 같은 자리를 따로 다룬다.
    """
    count = len(values)
    if count < MIN_FOR_SPREAD:
        # **2개로는 판정할 수 없다.** 둘이 다르면 어느 쪽이 이상한지 알 방법이 없다.
        return []
    if not 0 < threshold <= 20:
        raise StatisticsError(f"임계값은 0 초과 20 이하여야 합니다: {threshold}")

    array = np.asarray(values, dtype=np.float64)
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))

    found: list[Outlier] = []
    if mad == 0:
        for index, value in enumerate(values):
            if value != median:
                found.append(
                    Outlier(
                        index=index,
                        value=value,
                        score=None,
                        reason=(
                            "나머지가 모두 같은 값인데 이것만 다릅니다. "
                            "흩어짐이 0 이라 점수를 낼 수 없습니다 — 사람이 봐야 합니다."
                        ),
                    )
                )
        return found

    for index, value in enumerate(values):
        score = abs(MODIFIED_Z_SCALE * (value - median) / mad)
        if score >= threshold:
            found.append(
                Outlier(
                    index=index,
                    value=value,
                    score=score,
                    reason=(
                        f"중앙값에서 {score:.2f}만큼 벗어났습니다 (임계 {threshold}). "
                        f"버리지 않았습니다 — 재료 특성인지 시험 실수인지는 "
                        f"곡선을 보고 정하세요."
                    ),
                )
            )
    return found


def grid_check(grids: list[np.ndarray]) -> GridCheck:
    """시편들의 x 격자가 같은가. 다르면 공통 구간을 계산해 준다.

    **통계가 정렬을 대신 하지 않는 이유:** 평균을 내려면 같은 x 에서 비교해야
    하는데, 여기서 조용히 보간하면 그 보간이 결과에 섞이고 나중에 알 수 없다.
    정렬은 처리(`curve.resample`)의 일이고, 그 단계를 레시피에 넣었는지는 사람이
    안다.

    다만 **막다른 길로 두지 않는다.** 공통 구간을 알려 줘야 재샘플 구간을 정할 수
    있다 — 그 값은 시편을 전부 봐야 나오므로 사람이 손으로 구할 수 없다.
    """
    if len(grids) < MIN_SAMPLES:
        return GridCheck(ok=False, reason=f"곡선이 {len(grids)}개뿐입니다.")

    starts = [float(grid[0]) for grid in grids]
    ends = [float(grid[-1]) for grid in grids]
    common_start = max(starts)
    common_end = min(ends)
    shortest = int(np.argmin(ends))

    first = grids[0]
    for index, grid in enumerate(grids[1:], start=1):
        if len(grid) == len(first) and np.allclose(grid, first, rtol=0, atol=0):
            continue

        # **왜 다른지를 갈라 말한다.** 둘은 고칠 데가 다르다.
        #
        #   점 수가 다르다      → 재샘플 단계가 아예 없다(또는 점 수를 달리 적었다)
        #   점 수는 같다        → 재샘플은 했는데 **구간이 시편마다 다르다**
        #
        # 뒤엣것이 흔하다. 표준 레시피는 끝을 비워 두고, 비우면 각자의 관측
        # 최댓값이 쓰인다 — 400점씩 잘 만들어 놓고도 안 맞는다. 그때 전에는
        # "(400점 vs 400점)" 이라고만 적었고, 그것은 고칠 데를 안 알려 주는 데다
        # 버그처럼 읽혔다(2026-08-31 실측).
        if len(grid) != len(first):
            why = (
                f"점 수가 다릅니다 ({len(first)}점 vs {len(grid)}점) — "
                f"'균등 격자로 재샘플' 단계가 빠졌거나 점 수를 달리 적었습니다."
            )
        else:
            why = (
                f"점 수는 {len(first)}점으로 같은데 **구간이 다릅니다** "
                f"([{float(first[0]):.6g}, {float(first[-1]):.6g}] vs "
                f"[{float(grid[0]):.6g}, {float(grid[-1]):.6g}]) — 재샘플의 끝을 "
                f"비워 두면 시편마다 제 관측 최댓값이 쓰입니다."
            )
        return GridCheck(
            ok=False,
            reason=(
                f"{index + 1}번째 곡선의 x 가 첫 곡선과 다릅니다. {why} "
                f"통계는 정렬을 대신 하지 않습니다 — 레시피의 '균등 격자로 재샘플' "
                f"구간을 [{common_start:.6g}, {common_end:.6g}] 로 **고정한 뒤** 다시 "
                f"처리하세요."
            ),
            common_start=common_start,
            common_end=common_end,
            shortest_index=shortest,
        )

    return GridCheck(
        ok=True,
        reason=f"모든 곡선이 같은 {len(first)}점 격자를 씁니다.",
        common_start=common_start,
        common_end=common_end,
        shortest_index=shortest,
    )


@dataclass(frozen=True)
class CurveStats:
    points: tuple[CurvePointStats, ...]
    grid: GridCheck
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mean_curve(self) -> list[tuple[float, float]]:
        """평균 곡선. **피팅의 입력이다.**"""
        return [(point.x, point.y.mean) for point in self.points]

    @property
    def median_curve(self) -> list[tuple[float, float]]:
        """중앙값 곡선. 이상치가 있을 때 평균보다 낫다 — 둘 다 내고 쓰는 쪽이 고른다."""
        return [(point.x, point.y.median) for point in self.points]


def curve_stats(grids: list[np.ndarray], values: list[np.ndarray]) -> CurveStats:
    """격자 점마다 흩어짐을 낸다. 격자가 다르면 거부한다."""
    check = grid_check(grids)
    if not check.ok:
        raise StatisticsError(check.reason)
    if len(grids) != len(values):
        raise StatisticsError("x 와 y 의 곡선 수가 다릅니다.")

    grid = grids[0]
    stacked = np.vstack(values)
    if stacked.shape[1] != len(grid):
        raise StatisticsError("x 와 y 의 점 수가 다릅니다.")

    points = tuple(
        CurvePointStats(x=float(grid[index]), y=scalar_stats(list(stacked[:, index])))
        for index in range(len(grid))
    )
    return CurveStats(
        points=points,
        grid=check,
        notes=(
            f"시편 {len(values)}개의 각 점에서 평균과 흩어짐을 냈습니다 "
            f"({len(grid)}점, x {float(grid[0]):.6g}~{float(grid[-1]):.6g}).",
        ),
    )
