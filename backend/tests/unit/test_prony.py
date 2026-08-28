"""Prony 적합 — **아는 계수로 만든 곡선에서 그 계수가 되돌아오는가.**

적합은 "수렴했다" 로 아무것도 증명되지 않는다. 틀린 계수도 수렴하고, 그 계수로
그린 곡선도 데이터를 지나간다. 그래서 **정답을 아는 곡선**을 만들어 검산한다.

합성: 3항 일반화 Maxwell 로 저장·손실을 만든다. 완화시간을 자릿수로 벌려 놓고
(0.01 · 1 · 100 s) 양쪽 평탄부가 다 보이도록 주파수를 넓게 잡는다.

**깨끗한 곡선과 잡음 섞은 곡선을 따로 둔다.** 계수를 되찾는지는 깨끗한 쪽이
보이고, 항 수를 고르는지는 잡음 쪽이라야 뜻이 있다 — 잔차가 기계 정밀도까지
내려가면 BIC 의 두 항이 부동소수 잡음에 묻혀 항 수를 못 고른다(실제로 그래서
4항을 골랐고, 그중 하나는 계수가 0.0013 Pa 인 빈 항이었다).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from matcore.prony import (
    PronyError,
    PronySeries,
    PronyTerm,
    choose_prony,
    fit_prony,
    storage_loss,
)

#: 합성 곡선의 정답.
TRUE = PronySeries(
    equilibrium_pa=5.0e6,
    terms=(
        PronyTerm(modulus_pa=2.0e8, relaxation_time_s=1.0e-2),
        PronyTerm(modulus_pa=8.0e8, relaxation_time_s=1.0e0),
        PronyTerm(modulus_pa=3.0e8, relaxation_time_s=1.0e2),
    ),
    normalized_rmse=0.0,
    bic=0.0,
)

#: 마스터커브다운 격자. **양쪽 평탄부가 보여야 한다** — τ 가 100 s 면 평형
#: 평탄부는 1/(2π·100) ≈ 1.6e-3 Hz 보다 한참 아래에서야 나온다.
FREQUENCY_HZ = np.logspace(-6, 4, 120)
STORAGE_PA, LOSS_PA = storage_loss(TRUE, FREQUENCY_HZ)

#: 잡음 섞은 것. 실제 DMA 에 잡음이 없을 리 없고, 없으면 BIC 가 일을 못 한다.
_NOISE = np.random.default_rng(20260821).normal(0.0, 0.003, size=(2, len(FREQUENCY_HZ)))
NOISY_STORAGE_PA = STORAGE_PA * (1.0 + _NOISE[0])
NOISY_LOSS_PA = LOSS_PA * (1.0 + _NOISE[1])


class Test되만들기:
    def test_계수로_곡선을_되만든다(self) -> None:
        """맞춘 것을 겹쳐 그릴 때 쓰는 길이다. 여기가 틀리면 적합도 틀린다."""
        storage, loss = storage_loss(TRUE, FREQUENCY_HZ)
        # ω→0 이면 저장은 평형값에 가고 손실은 0 에 간다.
        assert storage[0] == pytest.approx(TRUE.equilibrium_pa, rel=0.05)
        assert loss[0] < TRUE.equilibrium_pa
        # ω→∞ 면 저장은 순간 탄성률에 간다.
        assert storage[-1] == pytest.approx(TRUE.instantaneous_pa, rel=0.05)

    def test_순간_탄성률은_평형_더하기_전부다(self) -> None:
        assert TRUE.instantaneous_pa == pytest.approx(5.0e6 + 2.0e8 + 8.0e8 + 3.0e8)


class Test적합:
    def test_아는_계수를_되찾는다(self) -> None:
        """**항 수를 알려 주고 맞춘다.** 곡선이 겹치는지가 아니라 계수가 맞는지를 본다."""
        found = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3)
        taus = [term.relaxation_time_s for term in found.terms]
        moduli = [term.modulus_pa for term in found.terms]
        assert taus == pytest.approx([1.0e-2, 1.0e0, 1.0e2], rel=0.1)
        assert moduli == pytest.approx([2.0e8, 8.0e8, 3.0e8], rel=0.1)
        assert found.equilibrium_pa == pytest.approx(5.0e6, rel=0.2)

    def test_완화시간이_커지는_순서다(self) -> None:
        """정렬을 안 하면 같은 적합이 실행마다 다른 순서로 나오고, 그 계수를
        비교하려는 사람이 매번 손으로 정렬하게 된다."""
        found = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=4)
        taus = [term.relaxation_time_s for term in found.terms]
        assert taus == sorted(taus)

    def test_저장과_손실을_함께_맞춘다(self) -> None:
        """**하나만 맞추면 나머지가 틀린다.** 그 계수로 만든 카드는 해석에서
        감쇠를 엉뚱하게 준다."""
        found = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3)
        storage, loss = storage_loss(found, FREQUENCY_HZ)
        assert float(np.max(np.abs(storage - STORAGE_PA) / STORAGE_PA)) < 0.02
        peak = float(np.max(LOSS_PA))
        assert float(np.max(np.abs(loss - LOSS_PA))) / peak < 0.02

    def test_Abaqus_가_먹는_비율을_준다(self) -> None:
        """`*VISCOELASTIC` 은 절대 탄성률이 아니라 `gᵢ = Eᵢ/E₀` 를 받는다."""
        found = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3)
        ratios = found.relative_moduli
        assert len(ratios) == 3
        assert sum(ratios) < 1.0  # 평형 탄성률이 남아 있어야 한다
        assert all(0 < value < 1 for value in ratios)

    def test_점이_모자라면_거절한다(self) -> None:
        few = np.logspace(-1, 1, 4)
        storage, loss = storage_loss(TRUE, few)
        with pytest.raises(PronyError, match="최소 5점"):
            fit_prony(few, storage, loss, terms=3)

    def test_증가_순이_아니면_거절한다(self) -> None:
        reversed_hz = FREQUENCY_HZ[::-1]
        with pytest.raises(PronyError, match="증가 순"):
            fit_prony(reversed_hz, STORAGE_PA, LOSS_PA, terms=3)


class Test경계에붙은완화시간:
    def test_관측_밖을_외삽하면_말한다(self) -> None:
        """**데이터가 정하지 못한 값을 최적화가 갈 데까지 간 것이다.**

        완화시간 범위를 관측보다 훨씬 좁게 강제하면, 맞춘 τ 가 그 경계에 붙는다.
        실패는 아니지만 그 계수는 데이터가 뒷받침하지 않는다.
        """
        found = fit_prony(
            FREQUENCY_HZ,
            STORAGE_PA,
            LOSS_PA,
            terms=3,
            minimum_tau_s=0.5,
            maximum_tau_s=2.0,
        )
        assert found.at_bound, "경계에 붙었는데 말하지 않았다"

    def test_넉넉하면_안_붙는다(self) -> None:
        found = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3)
        assert not found.at_bound


class Test항수고르기:
    def test_후보를_전부_돌려준다(self) -> None:
        """고른 것만 주면 "3항이면 충분한데 왜 6항이지" 를 볼 수 없다."""
        best, everything = choose_prony(
            FREQUENCY_HZ, NOISY_STORAGE_PA, NOISY_LOSS_PA, candidates=(2, 3, 4, 5)
        )
        assert len(everything) == 4
        assert best in everything

    def test_BIC_가_가장_작은_것을_고른다(self) -> None:
        best, everything = choose_prony(
            FREQUENCY_HZ, NOISY_STORAGE_PA, NOISY_LOSS_PA, candidates=(2, 3, 4, 5)
        )
        assert best.bic == min(item.bic for item in everything)

    def test_3항짜리_곡선에서_3항을_고른다(self) -> None:
        """**항을 늘리면 잔차는 언제나 준다.** 그런데도 3항을 골라야 BIC 가
        제 일을 한 것이다."""
        best, _ = choose_prony(
            FREQUENCY_HZ, NOISY_STORAGE_PA, NOISY_LOSS_PA, candidates=(2, 3, 4, 5, 6)
        )
        assert len(best.terms) == 3

    def test_항을_늘리면_잔차는_준다(self) -> None:
        """BIC 가 왜 필요한지를 숫자로 박아 둔다."""
        _, everything = choose_prony(
            FREQUENCY_HZ, NOISY_STORAGE_PA, NOISY_LOSS_PA, candidates=(2, 3, 4, 5)
        )
        by_terms = sorted(everything, key=lambda item: len(item.terms))
        assert by_terms[0].normalized_rmse > by_terms[-1].normalized_rmse

    def test_일부가_실패해도_나머지를_쓴다(self) -> None:
        """8항이 안 됐다고 3항까지 못 쓰게 만들 이유가 없다."""
        best, everything = choose_prony(
            FREQUENCY_HZ, NOISY_STORAGE_PA, NOISY_LOSS_PA, candidates=(3, 40)
        )
        assert len(everything) >= 1
        assert len(best.terms) == 3

    def test_후보가_없으면_거절한다(self) -> None:
        with pytest.raises(PronyError, match="하나도 없습니다"):
            choose_prony(FREQUENCY_HZ, NOISY_STORAGE_PA, NOISY_LOSS_PA, candidates=())


class Test마스터커브와이어진다:
    def test_겹친_곡선을_그대로_먹는다(self) -> None:
        """2단계(마스터커브)의 출력이 3단계(Prony)의 입력이다. 사이에 손으로
        옮기는 단계가 있으면 그 자리에서 단위가 틀어진다."""
        from matcore.viscoelastic import Sweep, master_curve

        # 아는 Prony 곡선을 온도별 창으로 잘라 낸다(이동인자는 사람이 준다).
        window = np.logspace(-1, 1.3, 12)
        shifts = {273.15 + value: -0.8 * index for index, value in enumerate((0, 10, 20, 30))}
        sweeps = []
        for temperature_k, shift in shifts.items():
            storage, loss = storage_loss(TRUE, window * 10.0**-shift)
            sweeps.append(Sweep(temperature_k, window, storage, loss))

        curve = master_curve(
            sweeps,
            reference_temperature_k=273.15,
            method="manual",
            manual_shifts=shifts,
            points=90,
        )
        assert curve.loss_pa is not None
        found = fit_prony(curve.frequency_hz, curve.storage_pa, curve.loss_pa, terms=3)
        # 겹친 범위 안의 완화시간은 되찾아야 한다.
        taus = [term.relaxation_time_s for term in found.terms]
        assert min(taus) > 0
        assert math.isfinite(found.normalized_rmse)


class Test완화시간을_못_박기:
    """**시편 여럿의 계수를 평균 내려면 τ 가 공통이어야 한다.**

    τ 가 자유 변수이면 시편마다 다른 값으로 수렴하고 항 수도 BIC 가 따로 고른다.
    그러면 `E₁` 끼리 평균 낸다는 말 자체가 성립하지 않는다 — 서로 다른
    완화시간의 계수를 더하는 것이 된다.

    그래서 무는 자리를 「맞는다」 보다 **「준 τ 를 그대로 돌려준다」** 에 둔다.
    그게 평균이 뜻을 갖게 하는 조건이다.
    """

    TAUS = (1.0e-2, 1.0e0, 1.0e2)

    def test_준_완화시간을_그대로_돌려준다(self) -> None:
        """**이것이 평균의 전제다.** 하나라도 움직이면 축이 어긋난다."""
        fit = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3, fixed_taus_s=self.TAUS)
        got = [term.relaxation_time_s for term in fit.terms]
        assert got == pytest.approx(list(self.TAUS), rel=1e-12)

    def test_정답_τ_를_주면_계수를_되찾는다(self) -> None:
        """τ 를 맞게 줬으면 남은 것은 선형 문제다 — 정확히 맞아야 한다."""
        fit = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3, fixed_taus_s=self.TAUS)
        assert fit.equilibrium_pa == pytest.approx(TRUE.equilibrium_pa, rel=0.02)
        for got, want in zip(fit.terms, TRUE.terms, strict=True):
            assert got.modulus_pa == pytest.approx(want.modulus_pa, rel=0.02)

    def test_두_시편의_계수를_더할_수_있다(self) -> None:
        """**이 시험이 요점이다.** 서로 다른 곡선을 같은 축에 올렸는지 본다 —
        올라갔으면 항끼리 짝이 맞고, 그때만 평균이 성립한다."""
        first = fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3, fixed_taus_s=self.TAUS)
        second = fit_prony(
            FREQUENCY_HZ,
            NOISY_STORAGE_PA,
            NOISY_LOSS_PA,
            terms=3,
            fixed_taus_s=self.TAUS,
        )
        assert [one.relaxation_time_s for one in first.terms] == [
            one.relaxation_time_s for one in second.terms
        ]

    def test_경계_경고를_안_낸다(self) -> None:
        """τ 를 사람이 골랐으므로 「관측 밖으로 갔다」 는 말이 뜻이 없다."""
        fit = fit_prony(
            FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=3, fixed_taus_s=(1e-9, 1.0, 1e9)
        )
        assert fit.at_bound == ()

    def test_음수_완화시간은_거절한다(self) -> None:
        with pytest.raises(PronyError):
            fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=2, fixed_taus_s=(1.0, -1.0))

    def test_빈_목록은_거절한다(self) -> None:
        with pytest.raises(PronyError):
            fit_prony(FREQUENCY_HZ, STORAGE_PA, LOSS_PA, terms=1, fixed_taus_s=())

    def test_탄성률은_음수가_안_된다(self) -> None:
        """닫힌 해로 풀면 음의 탄성률이 나올 수 있다. 물리적으로 없는 값이다."""
        fit = fit_prony(
            FREQUENCY_HZ,
            NOISY_STORAGE_PA,
            NOISY_LOSS_PA,
            terms=5,
            fixed_taus_s=(1e-4, 1e-2, 1e0, 1e2, 1e4),
        )
        assert fit.equilibrium_pa > 0
        assert all(term.modulus_pa >= 0 for term in fit.terms)
