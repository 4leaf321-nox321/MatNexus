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


def test_사실상_0_인_기울기는_내지_않는다() -> None:
    """VOC 43(2026-11-14) — 응력이 양자화된 곡선에서 5.7e-5 Pa(R² 1.0)가 탄성률로 저장됐다.
    인장 `_fit_line` 과 같은 eps 바닥으로 막는다."""
    strain = np.linspace(0.001, 0.003, 50)
    stress = 2.0e8 + 5e-4 * strain  # 200 MPa 에서 5e-4 Pa 기울기 — 부동소수로는 오른다
    with pytest.raises(slopes.SlopeError, match="사실상 0"):
        slopes.measure(strain, stress, method="regression", low=0.001, high=0.003)


def test_빈_칸이_섞여도_응력_띠는_그_점을_빼고_잰다() -> None:
    """2026-11-14 검토 — 응력 띠는 구간을 연속 번호로 잡아 그 사이의 빈 칸(NaN)이 회귀에 들어가
    「예상 못 한 오류(LinAlgError)」 가 됐다. 현 · 회귀는 같은 곡선을 재는데 응력 띠만 못 쟀다.
    최대 응력 찾기도 첫 NaN 을 최대로 쳐 곡선을 거기서 잘랐다."""
    strain, stress = _linear()
    strain = strain.copy()
    stress = stress.copy()
    strain[40] = np.nan  # 띠(10~40 %) 안의 변형률 빈 칸
    stress[10] = np.nan  # 띠 아래의 응력 빈 칸 — 최대 응력 찾기를 흔든다
    for method in ("stress_window", "regression"):
        found = slopes.measure(strain, stress, method=method, high=0.005)
        assert found.value == pytest.approx(E, rel=1e-6), method
    assert slopes.rising(strain, stress) == len(stress)


def test_접선은_끝_점이_빈_칸이어도_창을_다_본다() -> None:
    """2026-11-14 검토 — 창 자리를 첫 · 끝 변형률로 잡아, 최대 응력 50% 자리의 변형률이
    빈 칸이면 격자가 `[처음, NaN, …]` 이 되어 토우 안의 창 하나만 보고 그 기울기를 냈다
    (조용히 틀림)."""
    strain = np.linspace(0, 0.02, 401)
    toe = 0.002
    stress = np.where(strain < toe, E * strain**2 / (2 * toe), E * (strain - toe / 2))
    limit = int(np.flatnonzero(stress <= 0.5 * stress.max())[-1]) + 1
    strain[limit - 1] = np.nan
    found = slopes.measure(strain, stress, method="tangent", tangent_width=0.002)
    assert found.value == pytest.approx(E, rel=0.01)
    assert found.low >= toe * 0.9


@pytest.mark.parametrize(
    "method", ["chord", "secant", "regression", "stress_window", "tangent"]
)
def test_변형률이_다_빈_칸이면_까닭을_말한다(method: str) -> None:
    """2026-11-14 검토 — 현 · 할선이 빈 배열을 보간하다 ValueError 로 터졌다(「예상 못 한
    오류」). 다섯 방법이 같은 말로 멈춘다."""
    _, stress = _linear()
    strain = np.full_like(stress, np.nan)
    with pytest.raises(slopes.SlopeError, match="숫자인 점이 0개"):
        slopes.measure(strain, stress, method=method)


def _toe_then_line(points: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """토우(최대의 5 % 까지) → 직선(60 % 까지) → 휘어 100 MPa 로. 참 E = 3 GPa."""
    true_e, peak = 3.0e9, 100.0e6
    strain = np.linspace(0, 0.08, points)
    toe = 0.05 * peak / true_e * 2
    line = np.where(strain < toe, true_e * strain**2 / (2 * toe), true_e * (strain - toe / 2))
    knee = 0.6 * peak
    over = np.maximum(line - knee, 0.0)
    stress = np.where(line < knee, line, knee + (peak - knee) * np.tanh(over / (peak - knee)))
    return strain, stress


class Test응력_띠는_튄_점_하나에_안_끌려간다:
    """2026-11-14(VOC 43 후속) — 「처음 닿음」 을 한 점으로 판정해, 위 끝 문턱 앞에서 한 점이
    튀면 구간이 거기서 끊기고 그 점이 기울기를 끌어올렸다."""

    def test_위_끝_문턱_앞에서_튄_점(self) -> None:
        strain, stress = _toe_then_line(500)
        clean = slopes.measure(strain, stress, method="stress_window")
        peak = float(stress.max())
        at = int(np.flatnonzero(stress >= 0.25 * peak)[0])
        spiked = stress.copy()
        spiked[at] += 0.2 * peak  # 25 % 자리에서 45 % 로 — 위 끝(40 %)을 넘는다
        found = slopes.measure(strain, spiked, method="stress_window")
        assert found.points > 0.9 * clean.points  # 구간이 거기서 끊기지 않는다
        assert found.value == pytest.approx(clean.value, rel=0.05)

    def test_오르는_곡선은_값이_그대로다(self) -> None:
        strain, stress = _toe_then_line(500)
        peak = float(stress.max())
        first = int(np.flatnonzero(stress >= 0.1 * peak)[0])
        last = int(np.flatnonzero(stress >= 0.4 * peak)[0])
        found = slopes.measure(strain, stress, method="stress_window")
        assert found.indices == (first, last + 1)

    def test_연속이_없는_곡선_끝에서는_한_점_도달로(self) -> None:
        values = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        assert slopes.first_reach(values, 4.0) == 4
        assert slopes.first_reach(values, 5.0) is None
        assert slopes.first_reach(np.array([0, 9, 0, 2, 2, 2, 2, 2.0]), 2.0) == 3


class Test접선은_잡음이_위로_튄_창을_고르지_않는다:
    """2026-11-14(VOC 44 후속, ADR 0088) — 가장 가파른 창 하나의 기울기를 내, 잡음이 있으면 늘
    위로 튄 창이 뽑혔다(D790 기본 창에서 잡음 0.25 % 에 +15 %)."""

    def test_잡음이_있어도_참값_근처(self) -> None:
        strain, stress = _toe_then_line(1000)
        rng = np.random.default_rng(7)
        errors = []
        for _ in range(40):
            noisy = stress + rng.normal(0, 0.0025 * stress.max(), len(stress))
            found = slopes.measure(strain, noisy, method="tangent", tangent_width=0.001)
            errors.append(found.value / 3.0e9 - 1)
        assert abs(float(np.median(errors))) < 0.02  # 전에는 +15 %
        assert max(abs(one) for one in errors) < 0.08  # 묶인 창이 하나뿐이던 꼬리(+30 % 이상)

    def test_잡음이_없으면_직선_구간의_값이고_구간은_직선_전체(self) -> None:
        strain, stress = _toe_then_line(1000)
        found = slopes.measure(strain, stress, method="tangent", tangent_width=0.001)
        assert found.value == pytest.approx(3.0e9, rel=1e-3)
        assert found.points >= 3 * 12  # 창 하나(12~13점)가 아니라 묶인 구간

    def test_튄_점_하나가_든_창에_안_끌려간다(self) -> None:
        strain, stress = _toe_then_line(1000)
        rng = np.random.default_rng(3)
        noisy = stress + rng.normal(0, 0.001 * stress.max(), len(stress))
        at = int(np.flatnonzero(stress >= 0.3 * stress.max())[0])
        noisy[at] += 0.1 * stress.max()
        found = slopes.measure(strain, noisy, method="tangent", tangent_width=0.001)
        assert found.value == pytest.approx(3.0e9, rel=0.05)  # 전에는 +69 %
