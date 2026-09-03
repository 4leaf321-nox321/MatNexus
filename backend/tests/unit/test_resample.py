"""점 수 맞추기 — **지어내지 않고, 모양을 지킨다.**

이 계산이 틀리면 카드의 표가 조용히 달라진다. 값이 바뀌는 자리라 무는 것이 넷이다.

    구간 밖으로 안 나간다      늘리는 것은 외삽의 일이고 근거가 따로 있다
    측정점을 지키는 방법은 지킨다   「장비가 준 그 값」 이 표에서 사라지면 곤란하다
    꺾이는 곳에 점이 몰린다     등간격으로 뜨면 항복 무릎이 뭉개진다
    0에서 시작해도 로그가 된다   소성 변형률은 0에서 시작하는 일이 흔하다
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import resample


def line(count: int = 21) -> list[tuple[float, float]]:
    return [(x, 2.0 * x) for x in np.linspace(0.0, 0.2, count)]


def knee() -> list[tuple[float, float]]:
    """항복 무릎 — 앞은 가파르고 뒤는 완만하다."""
    xs = np.linspace(0.0, 0.2, 201)
    ys = np.where(xs < 0.02, 3000.0 * xs, 60.0 + 200.0 * (xs - 0.02))
    return [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)]


class Test구간_밖으로_안_나간다:
    def test_처음과_끝이_그대로다(self) -> None:
        """**늘리는 것은 외삽의 일이다.** 여기서 한 점이라도 밖으로 나가면 그 카드는
        근거 없이 지어낸 값을 갖게 된다."""
        for method in resample.METHODS:
            got = resample.resample(line(), method=method, count=8)
            assert got[0][0] >= 0.0
            assert got[-1][0] <= 0.2 + 1e-12

    def test_값은_곡선_위에_있다(self) -> None:
        got = resample.resample(line(), method="uniform", count=9)
        for x, y in got:
            assert y == pytest.approx(2.0 * x, rel=1e-9, abs=1e-12)


class Test방법마다_하는_일:
    def test_등간격은_고르게_나눈다(self) -> None:
        got = resample.resample(line(), method="uniform", count=5)
        assert [round(x, 3) for x, _ in got] == [0.0, 0.05, 0.1, 0.15, 0.2]

    def test_측정점을_지키는_방법은_원본을_다_남긴다(self) -> None:
        source = [(0.0, 0.0), (0.01, 30.0), (0.2, 100.0)]
        got = resample.resample(source, method="keep_source", count=6)
        kept = {round(x, 6) for x, _ in got}
        assert {0.0, 0.01, 0.2} <= kept
        assert len(got) == 6

    def test_원본이_더_많으면_줄이지_않는다(self) -> None:
        # **버리면 「장비가 준 그 값」 이 표에서 사라진다.** 요청보다 많은 것은
        # 손해가 아니다.
        got = resample.resample(line(21), method="keep_source", count=5)
        assert len(got) == 21

    def test_꺾이는_곳에_점이_몰린다(self) -> None:
        # 등간격으로 뜨면 무릎이 뭉개진다 — 솔버는 두 점 사이를 직선으로 잇는다.
        picked = resample.resample(knee(), method="curvature", count=12)
        even = resample.resample(knee(), method="uniform", count=12)
        near_knee = sum(1 for x, _ in picked if 0.005 <= x <= 0.035)
        assert near_knee > sum(1 for x, _ in even if 0.005 <= x <= 0.035)

    def test_평평한_구간도_점을_아주_잃지는_않는다(self) -> None:
        # 무게에 바닥값이 없으면 직선 구간이 양 끝 두 점으로만 남는다 — 그 구간의
        # 측정을 통째로 버린 표가 된다.
        picked = resample.resample(knee(), method="curvature", count=12)
        assert sum(1 for x, _ in picked if x > 0.05) >= 3

    def test_로그_두_점이면_양_끝만_남는다(self) -> None:
        """count=2 에 0 이 섞이면 로그로 나눌 「나머지」 가 한 점뿐이다 — geomspace 가
        시작점 하나만 돌려줘서 **표의 끝(관측 최대)이 조용히 사라졌다.** 관측 범위가
        [0, 0.2] 인 표가 [0, 0.001] 로 줄어드는데 숫자는 그럴듯해 보인다."""
        got = resample.resample(line(), method="log", count=2)
        assert [x for x, _ in got] == [0.0, 0.2]

    def test_0에서_시작해도_로그로_나눈다(self) -> None:
        # 소성 변형률은 0에서 시작하는 일이 흔하다. **첫 점을 버리면 솔버가 항복점을
        # 읽는 줄이 사라진다.**
        got = resample.resample(line(), method="log", count=6)
        assert got[0][0] == 0.0
        assert len(got) == 6


class Test거절해야_할_것:
    def test_모르는_방법(self) -> None:
        with pytest.raises(resample.ResampleError):
            resample.resample(line(), method="없는방법", count=5)

    def test_점이_둘_미만(self) -> None:
        with pytest.raises(resample.ResampleError):
            resample.resample([(0.0, 0.0)], method="uniform", count=5)

    def test_너무_많은_점(self) -> None:
        """**실수를 막는 값이다** — 0 하나 더 붙여 십만 점 표를 만들지 않게."""
        with pytest.raises(resample.ResampleError):
            resample.resample(line(), method="uniform", count=resample.MAX_POINTS + 1)

    def test_같은_x_가_겹쳐도_무너지지_않는다(self) -> None:
        # 처리 결과에서 같은 변형률이 두 번 나오는 것은 구간을 이어 붙인 자리다.
        source = [(0.0, 0.0), (0.1, 50.0), (0.1, 51.0), (0.2, 100.0)]
        got = resample.resample(source, method="uniform", count=5)
        assert len(got) == 5
        assert [x for x, _ in got] == sorted(x for x, _ in got)
