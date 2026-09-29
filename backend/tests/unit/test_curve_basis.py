"""대표 곡선의 기준 — 평균 · 중앙값 · 상한 · 하한(2026-09-29).

카드를 만들 때 대표 곡선이 늘 평균이었다. 해석은 강도 평가에 하한, 충돌 에너지·성형 하중에
상한 곡선을 쓴다. 무는 것:

    한계가 옳은 쪽으로 벌어진다      하한이 평균 위로 가면 그 카드는 이름만 하한이다
    공차 계수가 표와 같다            MMPDS B 기준 — n=3 6.155 · 5 3.407 · 10 2.355
    포락선·시편이 기준대로 고른다     포락선은 점마다, 시편은 곡선 전체의 높이로
    뜻 없는 한계는 거절한다          0 아래 하한 · 시편 1개 · 방법 없는 상한
    내려가는 한계선을 미리 말한다     내보낼 때 거절될 표를 카드 만들기 전에 안다
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import statistics as st

GRID = np.linspace(0.0, 0.1, 11)
LOW = 300e6 + 400e6 * GRID
MID = 320e6 + 420e6 * GRID
HIGH = 340e6 + 440e6 * GRID


def _ys(picked: st.PickedCurve) -> np.ndarray:
    return np.asarray([y for _, y in picked.points])


def _pick(values: list[np.ndarray], **basis: object) -> st.PickedCurve:
    return st.pick_curve(GRID, values, st.CurveBasis(**basis))  # type: ignore[arg-type]


class Test평균과_중앙값:
    def test_기준을_안_주면_평균이다(self) -> None:
        picked = _pick([LOW, MID, HIGH])
        assert picked.label == "평균"
        assert np.allclose(_ys(picked), (LOW + MID + HIGH) / 3)

    def test_중앙값은_가운데_시편의_값이다(self) -> None:
        picked = _pick([HIGH, LOW, MID], kind="median")
        assert picked.label == "중앙값"
        assert np.allclose(_ys(picked), MID)


class Test표준편차_배수:
    def test_하한은_평균에서_k_표준편차_아래다(self) -> None:
        stacked = np.vstack([LOW, MID, HIGH])
        picked = _pick([LOW, MID, HIGH], kind="lower", method="sd", k=2)
        expected = stacked.mean(axis=0) - 2 * stacked.std(axis=0, ddof=1)
        assert np.allclose(_ys(picked), expected)
        assert picked.label == "하한 — 평균 - 2σ"
        assert picked.factor == 2
        assert all(_ys(picked) < stacked.mean(axis=0))

    def test_상한은_위로_벌어진다(self) -> None:
        stacked = np.vstack([LOW, MID, HIGH])
        picked = _pick([LOW, MID, HIGH], kind="upper", method="sd", k=1)
        expected = stacked.mean(axis=0) + stacked.std(axis=0, ddof=1)
        assert np.allclose(_ys(picked), expected)
        assert picked.label == "상한 — 평균 + 1σ"

    @pytest.mark.parametrize("k", [None, 0.0, 5.5])
    def test_배수가_없거나_범위_밖이면_거절한다(self, k: float | None) -> None:
        """**배수에 기본값이 없다** — 얼마나 벌릴지는 데이터가 못 정한다."""
        with pytest.raises(st.StatisticsError):
            _pick([LOW, MID, HIGH], kind="lower", method="sd", k=k)


class Test공차한계:
    @pytest.mark.parametrize(("count", "expected"), [(3, 6.155), (5, 3.407), (10, 2.355)])
    def test_계수가_B_기준_표와_같다(self, count: int, expected: float) -> None:
        assert st.tolerance_factor(count) == pytest.approx(expected, abs=5e-4)

    def test_하한에_시편_수의_계수를_쓴다(self) -> None:
        values = [LOW, MID, HIGH, (LOW + MID) / 2, (MID + HIGH) / 2]
        stacked = np.vstack(values)
        picked = _pick(values, kind="lower", method="tolerance")
        factor = st.tolerance_factor(5)
        assert picked.factor == pytest.approx(factor)
        assert np.allclose(
            _ys(picked), stacked.mean(axis=0) - factor * stacked.std(axis=0, ddof=1)
        )
        assert "공차 한계" in picked.label

    def test_시편_2개면_거절한다(self) -> None:
        with pytest.raises(st.StatisticsError, match="3개부터"):
            _pick([LOW, HIGH], kind="lower", method="tolerance")


class Test포락선과_실제_시편:
    def test_포락선은_점마다_가장_낮은_값을_잇는다(self) -> None:
        # 두 곡선이 가운데서 엇갈린다 — 포락선은 앞쪽은 한 시편, 뒤쪽은 다른 시편이다.
        rising = 300e6 + 800e6 * GRID
        flat = 340e6 + 200e6 * GRID
        picked = _pick([rising, flat], kind="lower", method="envelope")
        assert np.allclose(_ys(picked), np.minimum(rising, flat))
        assert picked.label == "하한 — 포락선(점마다 최솟값)"

    def test_시편은_곡선_전체의_높이로_고른다(self) -> None:
        """첫 점만 보고 고르면 앞에서만 낮고 뒤에서 높은 시편이 뽑힌다."""
        early_low = 290e6 + 900e6 * GRID  # 첫 점이 가장 낮지만 전체로는 높다
        overall_low = 300e6 + 300e6 * GRID
        picked = _pick([early_low, overall_low, HIGH], kind="lower", method="specimen")
        assert picked.specimen_index == 1
        assert np.allclose(_ys(picked), overall_low)

        highest = _pick([early_low, overall_low, HIGH], kind="upper", method="specimen")
        assert highest.specimen_index == 2


class Test뜻_없는_한계는_거절하고_위험은_말한다:
    def test_시편_1개면_상하한이_없다(self) -> None:
        with pytest.raises(st.StatisticsError, match="흩어짐을 모릅니다"):
            _pick([MID], kind="upper", method="envelope")
        # 평균·중앙값은 그 시편의 곡선 그대로다.
        assert np.allclose(_ys(_pick([MID])), MID)

    @pytest.mark.parametrize(
        "basis",
        [
            {"kind": "lower"},
            {"kind": "lower", "method": "guess"},
            {"kind": "mean", "method": "sd", "k": 1},
            {"kind": "lower", "method": "envelope", "k": 2},
            {"kind": "worst"},
        ],
    )
    def test_말이_안_되는_기준은_거절한다(self, basis: dict[str, object]) -> None:
        with pytest.raises(st.StatisticsError):
            _pick([LOW, MID, HIGH], **basis)

    def test_0_아래로_내려가는_하한은_거절한다(self) -> None:
        """조용히 0 에 붙이면 그럴듯한 곡선이 나오고, 그 곡선은 아무것도 말하지 않는다."""
        wide = [100e6 + 0 * GRID, 500e6 + 0 * GRID, 900e6 + 0 * GRID]
        with pytest.raises(st.StatisticsError, match="0 아래로"):
            _pick(wide, kind="lower", method="sd", k=2)

    def test_흩어짐이_커지며_내려가는_하한을_말한다(self) -> None:
        """평균은 오르는데 하한이 내려가면, 내보낼 때 표 정리가 거절한다 — 미리 말한다."""
        grid = np.linspace(0.0, 1.0, 11)
        values = [300e6 + 100e6 * grid, 300e6 + 200e6 * grid, 300e6 + 300e6 * grid]
        picked = st.pick_curve(grid, values, st.CurveBasis(kind="lower", method="sd", k=3))
        assert any("내려가는 자리" in note for note in picked.notes)

        # 포락선은 단조가 지켜진다 — 같은 곡선들에서 말할 것이 없다.
        envelope = st.pick_curve(grid, values, st.CurveBasis(kind="lower", method="envelope"))
        assert not any("내려가는 자리" in note for note in envelope.notes)
