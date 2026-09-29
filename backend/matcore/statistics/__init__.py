"""반복 시편의 통계 — **여러 시편이 같은 것을 말하는가.**

시편 하나의 물성은 그 시편의 물성이다. 재료의 물성이라고 말하려면 여러 번 재고
그 흩어짐을 봐야 한다. 이 패키지는 그 흩어짐을 숫자로 낸다.

## 이 패키지가 지키는 것

**정렬을 대신 하지 않는다.** 시편들의 x 격자가 다르면 계산하지 않고 거부한다.
평균을 내려면 같은 x 에서 비교해야 하는데, 통계가 조용히 보간하면 **그 보간이
결과에 섞이고 아무도 모른다.** 정렬은 처리(`curve.resample`)의 일이다.

다만 **거부하고 끝내지 않는다.** 어디까지가 공통 구간인지 계산해 알려 준다 —
그 값이 있어야 사람이 레시피를 고칠 수 있다.

**맞추는 일은 따로, 드러나게 한다**(`align_grids`, 2026-09-18). 시편 열 개의 구간이
제각각일 때 레시피의 재샘플 끝을 하나씩 고쳐 다시 돌리는 것은 일이 된다 — 그래서
공통 구간의 균등 격자로 선형 보간해 주는 함수를 둔다. 통계(`curve_stats`)는 여전히
맞춰 주지 않는다: 부르는 쪽이 이 함수를 **일부러** 부르고, 돌려받은 문장을 근거에
적는다. 조용히 섞이는 것과 적어 두고 하는 것은 다르다.

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

#: 곡선의 x 폭이 나머지의 중앙값에 견주어 이보다 짧으면 「유난히 짧다」 로 표시한다.
#:
#: 인장에서 일찍 끊어진 시편이 그렇다 — 그 시편이 공통 구간의 끝을 정하면 나머지
#: 아홉의 뒤쪽이 통째로 잘린다. 자동으로 빼지는 않는다(이상치와 같은 규칙) — 표시하고
#: 빼는 것은 사람이 정한다. 0.5 는 「절반도 못 갔다」 다: 균일연신율의 시편 간 흩어짐은
#: 보통 10~20% 라 절반이면 재료 특성이 아니라 시험 사고 쪽이다.
SHORT_CURVE_RATIO = 0.5

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
class Alignment:
    """공통 구간의 균등 격자로 맞춘 곡선들. `note` 를 근거에 적는다."""

    grids: list[np.ndarray]
    values: list[np.ndarray]
    start: float
    end: float
    count: int
    changed: bool
    """실제로 보간했나. 이미 같은 격자였으면 거짓 — 그때 note 는 비어 있다."""
    shortest_index: int
    note: str


def align_grids(
    grids: list[np.ndarray], values: list[np.ndarray], *, count: int | None = None
) -> Alignment:
    """공통 구간 [max(시작), min(끝)] 의 균등 격자로 **선형 보간해** 맞춘다.

    `curve_stats` 가 거부하는 바로 그 경우를 위한 것이다. 격자가 이미 같으면 손대지
    않는다(`changed=False`). 점 수는 안 주면 가장 촘촘한 곡선의 점 수 — 줄이면 잰
    점이 사라지고, 늘려 봐야 새 정보는 없다.

    **측정 구간 밖으로는 한 점도 나가지 않는다.** 공통 구간은 모든 곡선이 실제로 잰
    구간의 교집합이라, 보간은 이웃한 두 측정점 사이에서만 일어난다(`resample` 과 같은
    규칙). 공통 구간이 비면(한 곡선이 끝나기 전에 다른 곡선이 시작하지 않으면) 거부한다.
    """
    if len(grids) < MIN_SAMPLES:
        raise StatisticsError(f"맞출 곡선이 {len(grids)}개뿐입니다.")
    if len(grids) != len(values):
        raise StatisticsError("x 와 y 의 곡선 수가 다릅니다.")
    for index, (grid, value) in enumerate(zip(grids, values, strict=True)):
        if len(grid) != len(value):
            raise StatisticsError(f"{index + 1}번째 곡선의 x 와 y 점 수가 다릅니다.")
        if len(grid) < 2 or not np.all(np.diff(grid) >= 0):
            raise StatisticsError(
                f"{index + 1}번째 곡선의 x 가 오름차순이 아닙니다 — "
                f"레시피에 '정렬·중복 제거' 단계가 있는지 보세요."
            )

    check = grid_check(grids)
    assert check.common_start is not None and check.common_end is not None
    assert check.shortest_index is not None
    if check.ok:
        return Alignment(
            grids=grids,
            values=values,
            start=check.common_start,
            end=check.common_end,
            count=len(grids[0]),
            changed=False,
            shortest_index=check.shortest_index,
            note="",
        )
    if check.common_start >= check.common_end:
        raise StatisticsError(
            f"공통 구간이 없습니다 — 한 곡선은 {check.common_start:.6g} 에서 시작하는데 "
            f"다른 곡선은 {check.common_end:.6g} 에서 끝납니다. 곡선을 보고 빼세요."
        )
    points = count or max(len(grid) for grid in grids)
    if points < 2:
        raise StatisticsError(f"점 수는 2 이상이어야 합니다: {points}")
    grid = np.linspace(check.common_start, check.common_end, points)
    # **같은 x 가 되풀이되는 곡선이 실제로 있다** — 진소성변형률은 탄성 구간에서 0 이 수백
    # 점 이어진다(clip). `np.interp` 는 x 가 늘어나기만 하면 되지만 되풀이 자리의 값은
    # 정의가 흐리니, 같은 x 는 y 의 평균 한 점으로 접고 보간한다.
    aligned = [
        np.interp(grid, *_collapse(one, value))
        for one, value in zip(grids, values, strict=True)
    ]
    return Alignment(
        grids=[grid.copy() for _ in grids],
        values=aligned,
        start=check.common_start,
        end=check.common_end,
        count=points,
        changed=True,
        shortest_index=check.shortest_index,
        note=(
            f"시편마다 x 구간이 달라 공통 구간 [{check.common_start:.6g}, "
            f"{check.common_end:.6g}] 의 {points}점 균등 격자로 선형 보간해 맞췄습니다 — "
            f"그 밖의 측정점은 대표 곡선에 안 들어갑니다."
        ),
    )


def _collapse(grid: np.ndarray, value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """같은 x 의 점들을 y 평균 한 점으로. x 는 이미 오름차순(같은 값 허용)이다."""
    unique, inverse = np.unique(grid, return_inverse=True)
    if len(unique) == len(grid):
        return grid, value
    summed = np.bincount(inverse, weights=value, minlength=len(unique))
    counts = np.bincount(inverse, minlength=len(unique))
    return unique, summed / counts


def short_curves(grids: list[np.ndarray], *, ratio: float = SHORT_CURVE_RATIO) -> list[int]:
    """x 폭이 나머지의 중앙값에 견주어 `ratio` 보다 짧은 곡선의 번호.

    **버리지 않는다** — 표시만 한다. 둘뿐이면 어느 쪽이 짧은지 말할 수 없어 빈 목록이다
    (이상치와 같은 이유, `MIN_FOR_SPREAD`).
    """
    if len(grids) < MIN_FOR_SPREAD:
        return []
    spans = [float(grid[-1]) - float(grid[0]) for grid in grids]
    found: list[int] = []
    for index, span in enumerate(spans):
        others = spans[:index] + spans[index + 1 :]
        typical = float(np.median(others))
        if typical > 0 and span < ratio * typical:
            found.append(index)
    return found


def typical_span(grids: list[np.ndarray], *, excluding: int | None = None) -> float:
    """나머지 곡선 x 폭의 중앙값 — 「보통 어디까지 가나」."""
    spans = [
        float(grid[-1]) - float(grid[0])
        for index, grid in enumerate(grids)
        if index != excluding
    ]
    return float(np.median(spans)) if spans else 0.0


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


# --- 대표 곡선을 무엇으로 — 평균 · 중앙값 · 상한 · 하한 (2026-09-29) ------------------------
#
# 카드를 만들 때 대표 곡선이 **늘 평균**이었다. 통계 화면은 평균·중앙값을 둘 다 내며 「어느
# 것을 쓸지는 피팅할 때 고르면 된다」 고 적어 두었는데, 정작 피팅에는 고를 자리가 없었다.
# 그리고 해석은 평균만 쓰지 않는다 — 강도 평가는 **하한**, 충돌 에너지·성형 하중은 **상한**
# 곡선으로 한 번 더 돌린다(2026-09-29 요청: 「상한치, 하한치를 뽑는 방법」).

#: 대표 곡선의 기준.
CURVE_BASES = ("mean", "median", "upper", "lower")

#: 상·하한을 내는 방법.
#:
#:     sd          점마다 평균 ± k·표준편차         흔히 쓰는 폭. k 는 사람이 고른다
#:     tolerance   점마다 평균 ± K(n)·표준편차      한쪽 공차 한계(B 기준 90%·95%)
#:     envelope    점마다 최댓값·최솟값(포락선)     잰 것의 끝. 서로 다른 시편의 점이 섞인다
#:     specimen    가장 높은·낮은 시편 하나의 곡선  한 시편의 모양을 그대로 지킨다
BOUND_METHODS = ("sd", "tolerance", "envelope", "specimen")

#: 공차 한계의 기본 — **B 기준**(MMPDS): 모집단의 90% 를 95% 신뢰로 덮는다.
TOLERANCE_COVERAGE = 0.90
TOLERANCE_CONFIDENCE = 0.95

#: 표준편차 배수의 상한. 그보다 넓히는 것은 통계가 아니라 여유율이다 — 그것은 해석 쪽이
#: 제 기준으로 곱한다.
MAX_SIGMA = 5.0


@dataclass(frozen=True)
class CurveBasis:
    """대표 곡선을 **무엇으로** 만들까. 비워 두면(기본값) 평균이다."""

    kind: str = "mean"
    method: str | None = None
    k: float | None = None
    """`sd` 의 표준편차 배수. **기본값이 없다** — 얼마나 벌릴지는 데이터가 못 정한다."""

    @property
    def bounded(self) -> bool:
        return self.kind in ("upper", "lower")


@dataclass(frozen=True)
class PickedCurve:
    """고른 대표 곡선. `label` 이 카드 근거와 화면에 그대로 선다."""

    points: list[tuple[float, float]]
    label: str
    notes: tuple[str, ...]
    specimen_index: int | None = None
    """`specimen` 이면 고른 시편의 자리. 부르는 쪽이 이름으로 되짚는다."""
    factor: float | None = None
    """`sd` 의 k, `tolerance` 의 K."""


def check_basis(basis: CurveBasis) -> None:
    """기준이 말이 되는가. **조용히 평균으로 떨어뜨리지 않는다** — 하한을 달라 했는데
    평균이 오면 그 카드는 이름만 하한이다."""
    if basis.kind not in CURVE_BASES:
        raise StatisticsError(f"모르는 기준입니다: {basis.kind} — {' · '.join(CURVE_BASES)}.")
    if not basis.bounded:
        if basis.method is not None or basis.k is not None:
            raise StatisticsError("평균·중앙값에는 방법(method)·배수(k)가 없습니다.")
        return
    if basis.method is None:
        raise StatisticsError(
            "상·하한은 방법을 함께 주세요 — sd(평균 ± k·표준편차) · tolerance(공차 한계) · "
            "envelope(포락선) · specimen(실제 시편)."
        )
    if basis.method not in BOUND_METHODS:
        raise StatisticsError(
            f"모르는 방법입니다: {basis.method} — {' · '.join(BOUND_METHODS)}."
        )
    if basis.method == "sd":
        if basis.k is None:
            raise StatisticsError(
                "표준편차 배수 k 를 주세요 — 얼마나 벌릴지는 데이터가 정하지 못합니다"
                "(1 · 2 · 3 이 흔합니다)."
            )
        if not 0 < basis.k <= MAX_SIGMA:
            raise StatisticsError(f"k 는 0 초과 {MAX_SIGMA:g} 이하입니다: {basis.k}")
    elif basis.k is not None:
        raise StatisticsError(f"'{basis.method}' 에는 배수 k 가 없습니다.")


def tolerance_factor(
    count: int,
    *,
    coverage: float = TOLERANCE_COVERAGE,
    confidence: float = TOLERANCE_CONFIDENCE,
) -> float:
    """한쪽 공차 한계의 K — 정규분포 가정(비중심 t 분포).

        K = t'(신뢰수준; 자유도 n-1, 비중심 d) / sqrt(n),   d = z_p * sqrt(n)

    B 기준(90%·95%)에서 n=3 이면 6.16, 5 면 3.41, 10 이면 2.36 이다. **표본이 적을수록
    넓다** — 세 개로 「모집단의 90%」 를 말하려면 그만큼 물러서야 한다. 그것이 정직한 답이다.
    """
    if count < 2:
        raise StatisticsError(f"공차 한계는 시편 2개부터입니다 (지금 {count}개).")
    # 무거운 모듈이라 쓸 때 부른다 — 통계를 import 하는 곳마다 scipy 를 싣지 않는다.
    from scipy import stats as distributions

    z = float(distributions.norm.ppf(coverage))
    t = float(distributions.nct.ppf(confidence, df=count - 1, nc=z * math.sqrt(count)))
    return t / math.sqrt(count)


def _share_inside(k: float) -> float:
    """정규분포에서 평균 - k·표준편차 위에(또는 + 아래에) 있는 비율 — Phi(k)."""
    return 0.5 * (1.0 + math.erf(k / math.sqrt(2.0)))


def pick_curve(grid: np.ndarray, values: list[np.ndarray], basis: CurveBasis) -> PickedCurve:
    """같은 격자로 맞춘 시편 곡선들에서 **기준대로** 대표 곡선 하나를 고른다.

    격자는 부르는 쪽이 이미 맞췄다(`curve_stats` 가 거부하지 않은 격자, 또는 `align_grids`).
    여기는 맞추지 않는다 — 조용히 섞이는 것을 막는 규칙이 이 패키지의 머리말이다.
    """
    check_basis(basis)
    count = len(values)
    if count == 0:
        raise StatisticsError("곡선이 없습니다.")
    stacked = np.vstack(values)
    if stacked.shape[1] != len(grid):
        raise StatisticsError("x 와 y 의 점 수가 다릅니다.")
    xs = [float(one) for one in grid]
    lower = basis.kind == "lower"
    side = "하한" if lower else "상한"
    toward = "낮은" if lower else "높은"
    sign = "-" if lower else "+"

    if basis.kind == "mean":
        return PickedCurve(
            points=list(zip(xs, (float(one) for one in stacked.mean(axis=0)), strict=True)),
            label="평균",
            notes=(),
        )
    if basis.kind == "median":
        middle = np.median(stacked, axis=0)
        return PickedCurve(
            points=list(zip(xs, (float(one) for one in middle), strict=True)),
            label="중앙값",
            notes=(f"점마다 시편 {count}개의 중앙값입니다 — 이상치 하나에 덜 끌려갑니다.",),
        )

    # ── 상·하한 ─────────────────────────────────────────────────────────────
    if count < MIN_SAMPLES:
        raise StatisticsError(
            f"시편이 {count}개라 {side}을 낼 수 없습니다 — 흩어짐을 모릅니다. 시편을 더 "
            "채택하거나 평균(그 시편의 곡선)을 쓰세요."
        )

    if basis.method == "envelope":
        edge = stacked.min(axis=0) if lower else stacked.max(axis=0)
        return PickedCurve(
            points=list(zip(xs, (float(one) for one in edge), strict=True)),
            label=f"{side} — 포락선(점마다 {'최솟값' if lower else '최댓값'})",
            notes=(
                f"점마다 시편 {count}개 중 가장 {toward} 값을 이었습니다 — 서로 다른 "
                "시편의 점이 섞이므로 한 시편의 모양은 아닙니다. 시편이 적으면 우연히 튄 "
                "하나가 곡선을 정합니다.",
            ),
        )

    if basis.method == "specimen":
        # **곡선 전체의 높이**로 줄 세운다(공통 구간 평균). 한 점의 값으로 고르면 그 점에서만
        # 낮고 나머지는 높은 시편이 뽑힌다.
        levels = stacked.mean(axis=1)
        index = int(np.argmin(levels) if lower else np.argmax(levels))
        return PickedCurve(
            points=list(zip(xs, (float(one) for one in stacked[index]), strict=True)),
            label=f"{side} — 가장 {toward} 시편",
            notes=(
                f"시편 {count}개 가운데 공통 구간 전체의 평균 높이가 가장 {toward} 시편의 "
                "곡선 그대로입니다 — 점마다 섞지 않아 한 시편의 모양을 지킵니다.",
            ),
            specimen_index=index,
        )

    # sd · tolerance — 점마다 평균 ± 배수·표준편차
    where = "위" if lower else "아래"
    if basis.method == "tolerance":
        if count < MIN_FOR_SPREAD:
            raise StatisticsError(
                f"공차 한계는 시편 {MIN_FOR_SPREAD}개부터 냅니다 (지금 {count}개) — 2개면 "
                f"K 가 {tolerance_factor(2):.1f} 이라 뜻이 없습니다. 평균 ± k·표준편차나 "
                "포락선을 쓰세요."
            )
        factor = tolerance_factor(count)
        label = (
            f"{side} — 공차 한계(B 기준 {TOLERANCE_COVERAGE:.0%}·{TOLERANCE_CONFIDENCE:.0%}, "
            f"K={factor:.3g})"
        )
        said = (
            f"점마다 평균 {sign} K·표준편차, K={factor:.3g}(시편 {count}개, 한쪽 공차 "
            f"한계)입니다 — 모집단의 {TOLERANCE_COVERAGE:.0%} 가 이 선 {where}에 있다고 "
            f"{TOLERANCE_CONFIDENCE:.0%} 신뢰로 말할 수 있습니다(정규분포 가정). 시편이 "
            "적을수록 K 가 커집니다."
        )
    else:
        assert basis.k is not None
        factor = basis.k
        label = f"{side} — 평균 {sign} {factor:g}σ"
        said = (
            f"점마다 평균 {sign} {factor:g}·표준편차(표본, n-1)입니다 — 정규분포라면 약 "
            f"{_share_inside(factor):.1%} 가 이 선 {where}에 있습니다. 시편이 적으면 "
            "표준편차 자체가 흔들립니다 — 통계적 허용값이 필요하면 공차 한계를 쓰세요."
        )
    notes = [said]
    if count == MIN_SAMPLES:
        notes.append("시편 2개로 낸 표준편차는 믿기 어렵습니다 — 폭이 우연에 크게 흔들립니다.")

    mean = stacked.mean(axis=0)
    sd = stacked.std(axis=0, ddof=1)
    picked = mean - factor * sd if lower else mean + factor * sd

    if lower:
        # **0 아래로 내려가는 하한은 뜻이 없다**(응력·강도는 양수다). 조용히 0 에 붙이면
        # 그럴듯한 곡선이 나오고, 그 곡선은 아무것도 말하지 않는다.
        crossed = np.nonzero((mean > 0) & (picked <= 0))[0]
        if crossed.size:
            at = int(crossed[0])
            raise StatisticsError(
                f"하한이 x={xs[at]:.4g} 에서 0 아래로 내려갑니다(평균 {float(mean[at]):.4g}, "
                f"표준편차 {float(sd[at]):.4g}, 배수 {factor:.3g}) — 표본이 적거나 흩어짐이 "
                "커서 이 방법으로는 뜻 있는 하한이 안 나옵니다. 배수를 줄이거나 포락선·실제 "
                "시편을 쓰세요."
            )

    # **평균은 오르는데 한계선이 내려가는 자리**를 말한다. 흩어짐이 커지는 구간(네킹 근처)에서
    # 생기고, 소성 표로 내보내면 표 정리가 「응력이 떨어진다」 로 거절한다(`export.prepare`).
    scale = float(np.max(np.abs(mean))) or 1.0
    rising = bool(np.all(np.diff(mean) >= -1e-9 * scale))
    drops = np.nonzero(np.diff(picked) < -1e-9 * scale)[0]
    if rising and drops.size:
        at = int(drops[0]) + 1
        notes.append(
            f"이 {side} 곡선은 x={xs[at]:.4g} 부터 앞 점보다 내려가는 자리가 있습니다 — 그 "
            "구간에서 시편 사이 흩어짐이 커지기 때문입니다. 소성 표로 내보낼 때 표 정리가 "
            "응력이 떨어지는 표를 거절하므로, 배수를 줄이거나 포락선·실제 시편을 쓰세요."
        )
    return PickedCurve(
        points=list(zip(xs, (float(one) for one in picked), strict=True)),
        label=label,
        notes=tuple(notes),
        factor=factor,
    )
