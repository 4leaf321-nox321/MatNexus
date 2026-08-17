"""반복 시편 통계 — **손으로 검산할 수 있는 값으로 확인한다.**

통계 코드는 "돌아간다" 로 아무것도 증명되지 않는다. 표준편차를 n 으로 나눠도
숫자는 나오고, 신뢰구간에 정규분포를 써도 숫자는 나온다. 둘 다 그럴듯해 보인다.

그래서 답을 아는 표본으로 확인한다. 그리고 **태도**를 시험한다 — 이상치를
버리지 않는지, 정렬을 대신 하지 않는지. 그쪽이 이 모듈의 값이다.
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import statistics as st


class Test스칼라통계:
    def test_손으로_검산한_값이_나온다(self) -> None:
        # [2, 4, 4, 4, 5, 5, 7, 9] — 교과서 예제
        stats = st.scalar_stats([2, 4, 4, 4, 5, 5, 7, 9])
        assert stats.count == 8
        assert stats.mean == pytest.approx(5.0)
        # **표본표준편차(n-1)** 다. 모표준편차(n)면 2.0 이 나온다 — 시편은 표본이므로
        # n-1 이 맞고, 둘의 차이는 표본이 작을수록 커진다.
        assert stats.sample_sd == pytest.approx(2.13809, rel=1e-4)
        assert stats.median == pytest.approx(4.5)

    def test_신뢰구간에_t분포를_쓴다(self) -> None:
        """**정규분포를 쓰면 구간이 실제보다 좁아진다.**

        n=3 이면 t=4.303 인데 정규분포는 1.96 이다. 시편이 3~10개인 이 도메인에서
        그 차이는 두 배가 넘는다 — "이 재료의 항복강도는 250±5" 가 실제로는
        250±11 인 셈이다.
        """
        stats = st.scalar_stats([100.0, 110.0, 120.0])
        # sd = 10, t(0.975, df=2) = 4.303, 반폭 = 4.303 * 10 / sqrt(3) = 24.84
        assert stats.ci95_low == pytest.approx(110 - 24.844, abs=0.01)
        assert stats.ci95_high == pytest.approx(110 + 24.844, abs=0.01)

    def test_평균이_0이면_변동계수를_내지_않는다(self) -> None:
        # 0 으로 나누면 inf 가 나오고 화면은 그것을 그대로 그린다.
        stats = st.scalar_stats([-5.0, 5.0])
        assert stats.coefficient_of_variation is None

    def test_표본이_모자라면_거절한다(self) -> None:
        with pytest.raises(st.StatisticsError, match="2건 이상"):
            st.scalar_stats([1.0])

    def test_너무_많으면_묶음을_의심하라고_한다(self) -> None:
        # 한 재료·방향에 시편 50개는 흔치 않다. 대개 묶음 키가 잘못된 것이다.
        with pytest.raises(st.StatisticsError, match="묶음이 잘못"):
            st.scalar_stats([1.0] * 51)


class Test이상치:
    """**버리지 않는다. 표시만 한다.**"""

    def test_중앙값_기준으로_잡는다(self) -> None:
        """평균 기준이면 이상치가 평균을 끌고 가 정작 그것이 안 걸린다."""
        found = st.outliers([205.0, 208.0, 203.0, 206.0, 150.0])
        assert [item.index for item in found] == [4]
        assert found[0].score is not None and found[0].score > 3.5

    def test_아무것도_버리지_않는다(self) -> None:
        # 반환값은 **후보 목록**이다. 입력은 그대로다.
        values = [205.0, 208.0, 203.0, 206.0, 150.0]
        st.outliers(values)
        assert len(values) == 5

    def test_두_개로는_판정하지_않는다(self) -> None:
        """**둘이 다르면 어느 쪽이 이상한지 알 방법이 없다.**

        65 도 같은 이유로 두 시편이 어긋나면 양쪽을 다 검토 대상으로 표시한다.
        여기서는 아예 후보를 내지 않는다 — 둘 중 하나를 고르면 그것이 곧 판정이다.
        """
        assert st.outliers([100.0, 500.0]) == []

    def test_흩어짐이_0이면_점수_없이_표시한다(self) -> None:
        """실제로 오는 경우다. 같은 파일을 여러 번 올리면 값이 정확히 같다.

        MAD 가 0 이라 z 가 무한대가 된다. 점수를 내지 않고 사실만 남긴다.
        """
        found = st.outliers([5.0, 5.0, 5.0, 5.0, 9.0])
        assert [item.index for item in found] == [4]
        assert found[0].score is None
        assert "사람이 봐야" in found[0].reason

    def test_임계값을_조절할_수_있다(self) -> None:
        mild = [10.0, 10.5, 11.0, 10.2, 12.5]
        assert st.outliers(mild, threshold=3.5) == []
        assert st.outliers(mild, threshold=1.5)


class Test격자:
    """**통계가 정렬을 대신 하지 않는다.**"""

    def test_같은_격자면_통과한다(self) -> None:
        grid = np.linspace(0, 0.3, 11)
        check = st.grid_check([grid, grid.copy(), grid.copy()])
        assert check.ok

    def test_다르면_거부하되_공통_구간을_알려_준다(self) -> None:
        """**거부만 하면 막다른 길이다.**

        재샘플 구간은 시편을 전부 봐야 나오므로 사람이 손으로 구할 수 없다.
        어디까지가 공통인지 계산해 줘야 레시피를 고칠 수 있다.
        """
        check = st.grid_check([np.linspace(0, 0.30, 11), np.linspace(0, 0.28, 11)])
        assert not check.ok
        assert check.common_start == pytest.approx(0.0)
        assert check.common_end == pytest.approx(0.28)
        assert check.shortest_index == 1
        assert "재샘플" in check.reason

    def test_격자가_다르면_곡선_통계를_안_낸다(self) -> None:
        # 여기서 조용히 보간하면 그 보간이 결과에 섞이고 나중에 알 수 없다.
        with pytest.raises(st.StatisticsError, match="정렬을 대신 하지 않습니다"):
            st.curve_stats(
                [np.linspace(0, 0.30, 11), np.linspace(0, 0.28, 11)],
                [np.zeros(11), np.zeros(11)],
            )


class Test곡선통계:
    def test_점마다_흩어짐을_낸다(self) -> None:
        grid = np.linspace(0, 1.0, 5)
        stats = st.curve_stats(
            [grid, grid.copy(), grid.copy()],
            [np.full(5, 10.0), np.full(5, 12.0), np.full(5, 14.0)],
        )
        assert len(stats.points) == 5
        assert stats.points[0].y.mean == pytest.approx(12.0)
        assert stats.points[0].y.sample_sd == pytest.approx(2.0)
        assert stats.points[0].y.count == 3

    def test_평균과_중앙값을_둘_다_낸다(self) -> None:
        """이상치가 있을 때 중앙값이 낫다. 어느 것을 쓸지는 쓰는 쪽이 고른다."""
        grid = np.linspace(0, 1.0, 3)
        stats = st.curve_stats(
            [grid, grid.copy(), grid.copy()],
            [np.full(3, 10.0), np.full(3, 11.0), np.full(3, 100.0)],
        )
        assert stats.mean_curve[0][1] == pytest.approx(40.333, abs=0.01)
        assert stats.median_curve[0][1] == pytest.approx(11.0)

    def test_어디까지_왜_냈는지_남는다(self) -> None:
        grid = np.linspace(0, 0.3, 7)
        stats = st.curve_stats([grid, grid.copy()], [np.zeros(7), np.zeros(7)])
        assert stats.notes
        assert "시편 2개" in stats.notes[0]
