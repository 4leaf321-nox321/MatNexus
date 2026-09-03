"""표의 **점 수를 맞춘다** — 카드를 만들 때 한 번 걸어 굳힌다.

## 왜 앞 단계가 아니라 여기인가

장비마다 샘플링이 다르고 처리 구간도 시험마다 다르다. 앞에서 맞추려면 읽는 규칙에
「몇 점으로 낼까」 를 넣어야 하는데, 그 값은 **해석이 요구하는 것**이지 측정의 성질이
아니다. 다 만들어진 곡선을 가지고 마지막에 한 번 고르는 편이 맞다.

## 왜 내보낼 때가 아니라 카드에 굳히는가

카드는 자기 근거를 들고 있는 **불변 기록**이다. 내보낼 때마다 다시 뽑으면 같은 카드가
형식마다 다른 표를 내고, 「내가 받은 덱의 그 숫자」 를 되짚을 수 없게 된다. 만들 때 한
번 걸고 무엇을 썼는지(`source.resample`) 적어 둔다.

## 지어내지 않는다

**측정 구간 밖으로는 한 점도 나가지 않는다.** 늘리는 것은 외삽(`extend_table`)의 일이고
그것은 식으로 근거를 남긴다. 여기서 하는 일은 **있는 곡선 위에서 점을 고르는 것**뿐이라,
새 격자의 값은 이웃한 두 점 사이의 선형 보간으로만 나온다.

## 방법을 왜 여럿 두는가

곡선의 성격이 다르다. 항복 무릎처럼 **꺾이는 자리**가 값을 정하는 곡선은 그 근처에 점이
몰려야 하고, 로그 축으로 보는 곡선(점탄성 완화)은 로그 간격이 자연스럽다. 하나로 정해
두면 어느 한쪽이 늘 손해를 본다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np


class ResampleError(ValueError):
    """점을 다시 고를 수 없다. **부르는 쪽이 사람 말로 옮긴다.**"""


@dataclass(frozen=True)
class Method:
    key: str
    label: str
    help: str
    grid: Callable[[np.ndarray, np.ndarray, int], np.ndarray]
    """새 x 격자를 만든다. 값은 바깥에서 보간한다 — 방법마다 다시 쓰지 않는다."""


def _uniform(x: np.ndarray, y: np.ndarray, count: int) -> np.ndarray:
    return np.linspace(float(x[0]), float(x[-1]), count)


def _log(x: np.ndarray, y: np.ndarray, count: int) -> np.ndarray:
    """로그 간격. **0 이하에서는 로그를 못 쓴다.**

    소성 변형률은 0에서 시작하는 일이 흔하다. 0을 버리면 표의 첫 점이 사라지므로
    (솔버가 항복점을 그 줄에서 읽는다) **0은 그대로 두고 그 위부터 로그로** 나눈다.
    """
    low = float(x[0])
    high = float(x[-1])
    positive = x[x > 0]
    if positive.size == 0:
        raise ResampleError("값이 모두 0 이하라 로그 간격으로 나눌 수 없습니다.")
    start = float(positive[0]) if low <= 0 else low
    if start >= high:
        raise ResampleError("로그 간격으로 나눌 만큼 구간이 넓지 않습니다.")
    if low <= 0:
        # 첫 점(0)을 지키고 나머지를 로그로 나눈다. **나머지가 한 점뿐이면 로그로
        # 나눌 것이 없다** — geomspace(start, high, 1) 은 시작점 하나만 돌려줘서
        # 표의 끝(관측 최대)이 조용히 사라진다. 그때는 양 끝만 남긴다.
        if count <= 2:
            return np.asarray([low, high], dtype=np.float64)
        return np.concatenate(([low], np.geomspace(start, high, count - 1)))
    return np.geomspace(start, high, count)


def _keep_source(x: np.ndarray, y: np.ndarray, count: int) -> np.ndarray:
    """**원본 점을 하나도 안 버리고** 사이를 채운다.

    측정점을 지우면 「장비가 준 그 값」 이 표에서 사라진다 — 되짚을 때 곤란해진다.
    그래서 원본은 전부 남기고, **가장 벌어진 구간부터** 점을 하나씩 끼워 넣는다.
    원본이 이미 요청한 수보다 많으면 그대로 둔다(줄이지 않는다).
    """
    grid = [float(one) for one in x]
    while len(grid) < count:
        gaps = np.diff(np.asarray(grid, dtype=np.float64))
        widest = int(np.argmax(gaps))
        grid.insert(widest + 1, (grid[widest] + grid[widest + 1]) / 2)
    return np.asarray(grid, dtype=np.float64)


def _curvature(x: np.ndarray, y: np.ndarray, count: int) -> np.ndarray:
    """**기울기가 빨리 바뀌는 곳에 점을 몰아 준다.**

    항복 무릎처럼 꺾이는 자리를 등간격으로 뜨면 그 모서리가 뭉개진다 — 표를 읽는
    솔버는 두 점 사이를 직선으로 잇기 때문에, 꺾이는 자리의 점이 성기면 곡선이
    실제보다 완만해진다.

    굽은 정도(2차 차분)를 무게로 두고 **무게의 누적이 고르게** 되도록 나눈다.
    평평한 구간도 점을 아주 잃지는 않게 바닥값을 깐다 — 안 그러면 직선 구간이
    양 끝 두 점으로만 남아, 그 구간의 측정을 통째로 버린 표가 된다.
    """
    if x.size < 3:
        return _uniform(x, y, count)
    # 스케일을 없애고(변형률과 응력은 자릿수가 다르다) 굽은 정도를 잰다.
    span_x = float(x[-1] - x[0]) or 1.0
    span_y = float(np.max(y) - np.min(y)) or 1.0
    nx = (x - x[0]) / span_x
    ny = (y - np.min(y)) / span_y
    slope = np.gradient(ny, nx)
    bend = np.abs(np.gradient(slope, nx))
    # **꺾임은 한 점이 아니라 구역이다.** 2차 차분은 무릎에서 뾰족한 하나로 나오는데
    # 그대로 쓰면 그 한 점에 몰리고 무릎의 앞뒤가 빈다. 폭을 조금 준다.
    window = max(3, x.size // 20)
    bend = np.convolve(bend, np.ones(window) / window, mode="same")
    peak = float(np.max(bend)) or 1.0
    # 바닥값: **평평한 구간도 제 몫을 받는다.** 없으면 직선 구간이 양 끝 두 점으로만
    # 남아 그 구간의 측정을 통째로 버린 표가 된다. 무릎은 바닥값보다 세 배쯤 촘촘해진다.
    weight = bend / peak + 0.2
    # 누적 무게를 x 로 두고 등간격으로 되돌린다.
    cumulative = np.concatenate(
        ([0.0], np.cumsum((weight[1:] + weight[:-1]) / 2 * np.diff(nx)))
    )
    if cumulative[-1] <= 0:
        return _uniform(x, y, count)
    wanted = np.linspace(0.0, float(cumulative[-1]), count)
    return np.asarray(np.interp(wanted, cumulative, x), dtype=np.float64)


#: 고를 수 있는 방법. **화면이 이 목록을 그대로 보여 준다** — 새 방법을 더할 때
#: 화면을 안 고치도록.
METHODS: dict[str, Method] = {
    one.key: one
    for one in (
        Method(
            key="curvature",
            label="꺾이는 곳에 촘촘히",
            help=(
                "기울기가 빨리 바뀌는 자리(항복 무릎 등)에 점을 몰아 줍니다."
                " 모양을 가장 적은 점으로 지킵니다."
            ),
            grid=_curvature,
        ),
        Method(
            key="keep_source",
            label="측정점을 지키고 채우기",
            help=(
                "원본 점을 하나도 버리지 않고 벌어진 구간부터 채웁니다."
                " 원본이 이미 많으면 그대로 둡니다."
            ),
            grid=_keep_source,
        ),
        Method(
            key="log",
            label="로그 간격",
            help=(
                "자릿수가 다른 구간을 고르게 봅니다."
                " 값이 0에서 시작하면 그 점은 그대로 두고 나눕니다."
            ),
            grid=_log,
        ),
        Method(
            key="uniform",
            label="등간격",
            help="처음과 끝 사이를 같은 폭으로 나눕니다.",
            grid=_uniform,
        ),
    )
}

#: 안 고르면 이것. **모양을 지키는 것이 기본**이고, 나머지는 이유가 있을 때 고른다.
DEFAULT_METHOD = "curvature"

#: 표가 가질 수 있는 점 수의 상한. 솔버 덱이 커지는 것을 막는 값이 아니라
#: **실수를 막는 값**이다 — 0 하나 더 붙여 십만 점 표를 만들지 않게.
MAX_POINTS = 2000


def resample(
    points: Sequence[tuple[float, float]], *, method: str = DEFAULT_METHOD, count: int
) -> list[tuple[float, float]]:
    """`points` 를 `count` 개로 다시 고른다.

    **구간 밖으로 나가지 않는다.** 새 격자는 늘 `[x0, x마지막]` 안이고, 값은 그 위의
    선형 보간이다 — 없는 데이터를 만들지 않는다.

    :raises ResampleError: 점이 둘 미만이거나, x 가 늘어나지 않거나, 방법을 모를 때.
    """
    picked = METHODS.get(method)
    if picked is None:
        raise ResampleError(f"모르는 방법입니다: {method}")
    if count < 2:
        raise ResampleError("점은 둘 이상이어야 합니다.")
    if count > MAX_POINTS:
        raise ResampleError(f"점은 {MAX_POINTS}개까지입니다.")

    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] < 2:
        raise ResampleError("다시 고르려면 점이 둘 이상 있어야 합니다.")

    order = np.argsort(array[:, 0], kind="stable")
    x = array[order, 0]
    y = array[order, 1]
    # 같은 x 가 둘이면 보간이 무너진다. **뒤엣것을 남긴다** — 처리 결과에서 같은
    # 변형률이 두 번 나오는 것은 이어 붙인 자리이고, 뒤가 다음 구간의 시작이다.
    keep = np.concatenate((np.diff(x) > 0, [True]))
    x, y = x[keep], y[keep]
    if x.size < 2:
        raise ResampleError("서로 다른 x 값이 둘 이상 있어야 합니다.")

    grid = np.asarray(picked.grid(x, y, count), dtype=np.float64)
    # 방법이 무엇을 하든 **구간 밖은 잘라 낸다**. 방법 하나가 실수하면 그 카드만
    # 조용히 지어낸 값을 갖게 되므로, 마지막에 한 번 더 막는다.
    grid = np.clip(grid, x[0], x[-1])
    grid = np.unique(grid)
    return [(float(one), float(np.interp(one, x, y))) for one in grid]


def describe() -> list[dict[str, str]]:
    """화면에 보여 줄 목록. **차례가 곧 추천 순서다.**"""
    return [{"key": one.key, "label": one.label, "help": one.help} for one in METHODS.values()]
