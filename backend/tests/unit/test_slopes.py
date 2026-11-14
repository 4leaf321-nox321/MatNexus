"""탄성률을 재는 다섯 방법(`matcore.slopes`, 2026-10-16).

같은 곡선에서 방법마다 값이 갈린다 — 어느 쪽이 옳은지는 규격이 정한다. 여기서는 **답을 아는
곡선**에서 각 방법이 제 정의대로 재는지 본다.
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import slopes

E = 2.0e9


def _linear(top: float = 0.01, points: int = 201) -> tuple[np.ndarray, np.ndarray]:
    strain = np.linspace(0, top, points)
    return strain, E * strain


def test_직선이면_다섯_방법이_같다() -> None:
    strain, stress = _linear()
    for method in slopes.METHODS:
        found = slopes.measure(strain, stress, method=method, high=0.005, tangent_width=0.002)
        assert found.value == pytest.approx(E, rel=1e-6), method


def test_현은_두_변형률의_응력을_잇는다() -> None:
    strain = np.linspace(0, 0.01, 101)
    stress = E * strain - 1e11 * strain**2
    found = slopes.measure(strain, stress, method="chord", low=0.0005, high=0.0025)
    expected = ((E * 0.0025 - 1e11 * 0.0025**2) - (E * 0.0005 - 1e11 * 0.0005**2)) / 0.002
    assert found.value == pytest.approx(expected)
    assert found.r2 is None and found.points == 2


def test_할선은_원점에서() -> None:
    strain = np.linspace(0, 0.2, 201)
    stress = 1e6 * np.sqrt(strain)
    found = slopes.measure(strain, stress, method="secant", high=0.1)
    assert found.value == pytest.approx(1e6 * np.sqrt(0.1) / 0.1, rel=1e-3)


def test_떨어지는_꼬리는_안_본다() -> None:
    """파단 뒤 떨어지는 구간이 응력 띠에 섞이면 엉뚱한 기울기가 나온다."""
    strain, stress = _linear()
    tail_strain = np.linspace(0.0101, 0.02, 50)
    tail_stress = np.linspace(E * 0.01, E * 0.002, 50)
    found = slopes.measure(
        np.concatenate([strain, tail_strain]),
        np.concatenate([stress, tail_stress]),
        method="stress_window",
    )
    assert found.value == pytest.approx(E, rel=1e-6)
    assert found.indices[1] <= len(strain)


def test_접선은_가장_가파른_처음_직선() -> None:
    strain = np.linspace(0, 0.02, 401)
    toe = 0.002
    stress = np.where(strain < toe, E * strain**2 / (2 * toe), E * (strain - toe / 2))
    found = slopes.measure(strain, stress, method="tangent", tangent_width=0.002)
    assert found.value == pytest.approx(E, rel=0.01)
    assert found.low >= toe * 0.9


def test_못_재면_까닭을_말한다() -> None:
    strain, stress = _linear(top=0.001)
    with pytest.raises(slopes.SlopeError, match="안 갑니다"):
        slopes.measure(strain, stress, method="chord", high=0.0025)
    with pytest.raises(slopes.SlopeError, match="점이"):
        slopes.measure(strain[:2], stress[:2], method="regression")
    with pytest.raises(slopes.SlopeError, match="모르는 방법"):
        slopes.measure(strain, stress, method="guess")
    with pytest.raises(slopes.SlopeError, match="창"):
        slopes.measure(strain, stress, method="tangent", tangent_width=1e-9)


class Test응력_띠는_첫_도달_사이_전부:
    """VOC 43(2026-11-14) — 띠 안의 「처음 이어진 구간」 만 쓰던 것이 잡음에 끊겼다."""

    def test_잡음이_띠_경계를_넘나들어도_잰다(self) -> None:
        # 칩 굽힘처럼 — 응력 60 MPa 까지 400점, 잡음 σ 0.2 MPa. 전에는 200번 중 117번 못 쟀다.
        strain = np.linspace(0, 0.02, 400)
        for seed in range(200):
            noise = np.random.default_rng(seed).normal(0.0, 0.2e6, strain.size)
            stress = 3.0e9 * strain + noise
            found = slopes.measure(strain, stress, method="stress_window")
            assert found.value == pytest.approx(3.0e9, rel=0.03), seed
            assert found.points >= 100, seed  # 10 % ~ 40 % 사이 점이 전부 들어간다

    def test_구간은_아래_끝_첫_도달부터_위_끝_첫_도달까지(self) -> None:
        strain, stress = _linear()
        found = slopes.measure(strain, stress, method="stress_window")
        peak = float(np.max(stress))
        first = int(np.flatnonzero(stress >= 0.1 * peak)[0])
        last = int(np.flatnonzero(stress >= 0.4 * peak)[0])
        assert found.indices == (first, last + 1)
        assert found.points == last - first + 1

    def test_응력이_안_변하면_R2_1_로_내지_않는다(self) -> None:
        # 응력이 계단처럼 양자화돼 구간 안에서 한 값이면 — 전에는 ≈0 기울기가 R² 1.0 이었다.
        strain = np.linspace(0, 0.01, 101)
        stress = np.where(strain < 0.003, 0.0, 1.0e6)
        stress[-1] = 2.0e6
        with pytest.raises(slopes.SlopeError, match="변하지 않습니다"):
            slopes.measure(strain, stress, method="regression", low=0.004, high=0.009)

    def test_회귀는_다섯_점_이상(self) -> None:
        strain, stress = _linear(points=201)  # 점 간격 5e-5
        with pytest.raises(slopes.SlopeError, match="5개 이상"):
            slopes.measure(strain, stress, method="regression", low=0.00099, high=0.00116)
        found = slopes.measure(strain, stress, method="regression", low=0.00099, high=0.00121)
        assert found.points == 5
