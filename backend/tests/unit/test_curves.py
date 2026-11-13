"""곡선 직렬화와 표시용 축약."""

from __future__ import annotations

import math
from typing import ClassVar

import pytest

from matcore import curves
from matcore.parsers import Channel


def _channels(n: int = 100) -> list[Channel]:
    return [
        Channel("displacement", "변위", "m", tuple(i * 0.001 for i in range(n))),
        Channel("force", "하중", "N", tuple(float(i * i) for i in range(n)), source_unit="N"),
    ]


class TestParquet:
    def test_필요한_열만_읽는다(self) -> None:
        """Parquet 을 쓰는 이유가 이것이다 — 차트는 보통 두 열만 본다."""
        data = curves.to_parquet(_channels())
        assert curves.column_names(data) == ["displacement", "force"]
        only = curves.read_columns(data, ["force"])
        assert list(only) == ["force"]
        assert len(only["force"]) == 100

    def test_결측을_보존한다(self) -> None:
        """센서가 놓친 구간을 0 으로 채우면 곡선이 원점으로 떨어진다."""
        channels = [
            Channel("a", "A", "m", (1.0, None, 3.0)),
            Channel("b", "B", "N", (4.0, 5.0, None)),
        ]
        read = curves.read_columns(curves.to_parquet(channels))
        assert read["a"] == [1.0, None, 3.0]
        assert read["b"] == [4.0, 5.0, None]

    def test_채널_길이가_다르면_거절한다(self) -> None:
        bad = [
            Channel("a", "A", "m", (1.0, 2.0)),
            Channel("b", "B", "N", (1.0,)),
        ]
        with pytest.raises(ValueError, match="길이"):
            curves.to_parquet(bad)


class TestDownsample:
    def test_처음과_끝을_남긴다(self) -> None:
        xs = list(range(1000))
        ys = [float(x * x) for x in xs]
        points = curves.downsample(xs, ys, max_points=50)
        assert points[0] == (0.0, 0.0)
        assert points[-1] == (999.0, 998001.0)
        assert len(points) <= 50

    def test_같은_점을_두_번_넣지_않는다(self) -> None:
        """점 수가 max_points 에 가까우면 빈 버킷이 생긴다. 거기서 직전 점을
        재사용하면 개수는 맞는데 실제 점은 하나 적은 결과가 나온다.

        실측: 18행을 10점으로 줄일 때 같은 점이 두 번 들어갔다.
        """
        xs = list(range(18))
        ys = [float(x) for x in xs]
        points = curves.downsample(xs, ys, max_points=10)
        assert len(points) == len(set(points))

    def test_뾰족한_점을_지킨다(self) -> None:
        """일정 간격으로 솎으면 국소 최대가 사라진다. 인장 곡선에서 항복점과
        최대하중이 정확히 그 뾰족한 곳이다."""
        xs = list(range(200))
        ys = [math.sin(x / 10) for x in xs]
        ys[137] = 99.0  # 다른 어떤 점보다도 뾰족한 점

        points = curves.downsample(xs, ys, max_points=20)
        assert any(y == 99.0 for _, y in points)

        # 같은 개수로 일정 간격 솎기를 하면 놓친다
        stride = ys[:: len(ys) // 20]
        assert 99.0 not in stride

    def test_결측은_이어_그리지_않고_뺀다(self) -> None:
        """곡선 중간의 구멍을 이으면 없는 데이터를 있는 것처럼 보여 준다."""
        xs: list[float | None] = [0.0, 1.0, None, 3.0]
        ys: list[float | None] = [0.0, None, 2.0, 3.0]
        assert curves.downsample(xs, ys, max_points=10) == [(0.0, 0.0), (3.0, 3.0)]

    def test_점이_적으면_그대로_준다(self) -> None:
        xs = [0.0, 1.0, 2.0]
        ys = [0.0, 1.0, 4.0]
        assert curves.downsample(xs, ys, max_points=100) == [
            (0.0, 0.0),
            (1.0, 1.0),
            (2.0, 4.0),
        ]


Columns = dict[str, list[float | None]]


class Test값_지문:
    """**SI 값으로 같은 측정을 알아본다**(2026-11-14, VOC 54) — 원본 SHA 는 형식만 달라도
    다르다."""

    BASE: ClassVar[Columns] = {
        "force": [0.0, 1234.5, 2469.0],
        "displacement": [0.0, 0.001, 0.002],
    }

    def test_열_차례와_적은_자릿수는_상관없다(self) -> None:
        again = {
            "displacement": [0.0, 0.0010000000000000002, 0.002],
            "force": [0.0, 1234.50000000001, 2469.0],
        }
        assert curves.fingerprint(self.BASE) == curves.fingerprint(again)

    def test_단위만_다른_사본은_SI_로_같다(self) -> None:
        # kN 으로 적힌 파일도 읽을 때 N 으로 바뀌어 같은 값이 된다 — 그 SI 값끼리 견준다.
        in_kn = [float(value or 0.0) * 1e-3 for value in self.BASE["force"]]
        back: Columns = {**self.BASE, "force": [value * 1e3 for value in in_kn]}
        assert curves.fingerprint(self.BASE) == curves.fingerprint(back)

    def test_값이_하나라도_다르면_다르다(self) -> None:
        other: Columns = {**self.BASE, "force": [0.0, 1234.6, 2469.0]}
        assert curves.fingerprint(self.BASE) != curves.fingerprint(other)

    def test_빈_칸은_빈_칸끼리만_같다(self) -> None:
        holed: Columns = {**self.BASE, "force": [0.0, None, 2469.0]}
        nan: Columns = {**self.BASE, "force": [0.0, float("nan"), 2469.0]}
        assert curves.fingerprint(holed) == curves.fingerprint(nan)
        assert curves.fingerprint(holed) != curves.fingerprint(self.BASE)

    def test_열이_없으면_지문도_없다(self) -> None:
        assert curves.fingerprint({}) is None
