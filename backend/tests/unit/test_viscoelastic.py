"""시간-온도 중첩 — **답을 아는 곡선으로 검산한다.**

수치 코드는 "돌아간다" 로 아무것도 증명되지 않는다. 부호를 뒤집어도 곡선은
나오고, 그것도 그럴듯하게 생겼다. 그래서 **아는 WLF 계수로 스윕을 만들어**
그 계수가 되돌아오는지 본다.

합성: 마스터커브를 로그 주파수의 시그모이드로 두고(유리 상태 3 GPa → 고무 상태
3 MPa), c1=17.44 · c2=51.6 K · 기준 20 °C 인 WLF 로 각 온도의 창을 잘라 낸다.
그러면 각 온도의 이동인자를 손으로 계산할 수 있다.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from matcore.viscoelastic import (
    GAS_CONSTANT,
    Sweep,
    ViscoelasticError,
    fit_arrhenius,
    fit_wlf,
    master_curve,
    observed_shift,
)

#: 합성 곡선의 정답.
#:
#: **보편값(17.44 / 51.6)을 안 쓴다.** 그 값이면 10 K 걸음마다 4.2 자릿수씩
#: 밀리는데 실측 창은 2.3 자릿수뿐이라, 이웃끼리도 안 겹친다. 실파일이 실제로
#: 보인 것은 6단 온도로 총 11 자릿수 — 걸음당 2 자릿수 남짓이다. 그 결에 맞춘다.
C1_TRUE = 8.0
C2_TRUE = 200.0
REFERENCE_K = 293.15  # 20 °C
GLASSY_PA = 3.0e9
RUBBERY_PA = 3.0e6

#: 실측 격자를 흉내 낸다 — TA DMA850 은 한 온도에서 0.1~20 Hz 를 훑었다.
WINDOW_HZ = np.logspace(-1, np.log10(20.0), 12)


def wlf_log_shift(temperature_k: float) -> float:
    delta = temperature_k - REFERENCE_K
    return -C1_TRUE * delta / (C2_TRUE + delta)


def master_storage(log_frequency: np.ndarray) -> np.ndarray:
    """기준 온도에서의 저장 탄성률. 로그 주파수의 시그모이드."""
    fraction = 1.0 / (1.0 + np.power(10.0, -(log_frequency + 2.0)))
    storage: np.ndarray = np.power(
        10.0, np.log10(RUBBERY_PA) + fraction * (np.log10(GLASSY_PA) - np.log10(RUBBERY_PA))
    )
    return storage


def synthetic(temperature_c: float) -> Sweep:
    """그 온도에서 실제로 잰 것처럼 창을 잘라 낸다.

    환산 주파수가 `ω·a_T` 이므로, 온도 T 에서 `ω` 로 잰 값은 마스터커브의
    `log10(ω) + log10(a_T)` 자리 값이다.
    """
    temperature_k = temperature_c + 273.15
    shifted = np.log10(WINDOW_HZ) + wlf_log_shift(temperature_k)
    storage = master_storage(shifted)
    return Sweep(
        temperature_k=temperature_k,
        frequency_hz=WINDOW_HZ,
        storage_pa=storage,
        loss_pa=storage * 0.05,
    )


#: 실측과 같은 온도 격자(-40 °C 부터 10 K 걸음). 기준은 20 °C.
SWEEPS = [synthetic(value) for value in (-40, -30, -20, -10, 0, 10, 20)]


class Test관측이동인자:
    """**모델을 가정하지 않고 실제로 겹쳐 본 값이다.** WLF 도 이것을 목표로 맞춘다."""

    def test_아는_이동인자를_되찾는다(self) -> None:
        reference = next(s for s in SWEEPS if s.temperature_k == REFERENCE_K)
        source = next(s for s in SWEEPS if abs(s.temperature_k - 273.15) < 1e-6)  # 0 °C
        shift, rmse = observed_shift(reference, source)
        assert shift == pytest.approx(wlf_log_shift(source.temperature_k), abs=0.02)
        # 같은 마스터커브에서 잘라 냈으니 겹침 잔차가 거의 0 이어야 한다.
        assert rmse < 0.01

    def test_안_겹치면_지어내지_않고_실패한다(self) -> None:
        """**이 시험이 이 모듈의 태도다.** 억지로 늘여 붙이면 근거 없는 구간이
        마스터커브에 들어가고, 그 위에서 Prony 를 맞추게 된다."""
        # 찾는 범위(±12 자릿수) 밖으로 밀어 둔다. 안 그러면 최적화가 억지로
        # 겹칠 자리를 찾아내고, 그 값은 아무 뜻이 없다.
        far = Sweep(
            temperature_k=500.0,
            frequency_hz=WINDOW_HZ * 1e15,
            storage_pa=np.full_like(WINDOW_HZ, 1.0e6),
        )
        reference = next(s for s in SWEEPS if s.temperature_k == REFERENCE_K)
        with pytest.raises(ViscoelasticError, match="겹치는"):
            observed_shift(reference, far)


class TestWLF:
    def test_아는_계수를_되찾는다(self) -> None:
        _, c1, c2 = fit_wlf(SWEEPS, REFERENCE_K)
        assert c1 == pytest.approx(C1_TRUE, rel=0.05)
        assert c2 == pytest.approx(C2_TRUE, rel=0.05)

    def test_기준_온도의_이동인자는_0_이다(self) -> None:
        shifts, _, _ = fit_wlf(SWEEPS, REFERENCE_K)
        reference = next(s for s in shifts if s.temperature_k == REFERENCE_K)
        assert reference.log10_a_t == pytest.approx(0.0, abs=1e-9)
        assert reference.source == "reference"

    def test_관측값을_함께_남긴다(self) -> None:
        """맞춘 값만 남기면 **모델이 이 재료에 안 맞는다는 사실이 사라진다.**"""
        shifts, _, _ = fit_wlf(SWEEPS, REFERENCE_K)
        fitted = [s for s in shifts if s.source == "fitted"]
        assert all(s.observed_log10_a_t is not None for s in fitted)
        assert all(s.residual is not None for s in fitted)
        # 같은 WLF 로 만든 곡선이니 잔차가 작아야 한다.
        assert max(abs(s.residual or 0) for s in fitted) < 0.1

    def test_온도가_둘이면_거절한다(self) -> None:
        """계수가 둘인데 점이 둘이면 **언제나 정확히 맞는다** — 맞았다는 뜻이 아니다."""
        with pytest.raises(ViscoelasticError, match="최소 3개 온도"):
            fit_wlf(SWEEPS[:2], SWEEPS[1].temperature_k)

    def test_기준_온도가_없으면_거절한다(self) -> None:
        with pytest.raises(ViscoelasticError, match="잰 온도에 없습니다"):
            fit_wlf(SWEEPS, 350.0)


class TestArrhenius:
    def test_아는_활성화에너지를_되찾는다(self) -> None:
        """Arrhenius 로 만든 곡선을 Arrhenius 로 되찾는다."""
        # 실측 결에 맞춘다 — 걸음마다 2 자릿수를 넘지 않아야 이웃이 겹친다.
        energy_true = 60_000.0  # J/mol
        slope = energy_true / (math.log(10.0) * GAS_CONSTANT)
        sweeps = []
        for temperature_c in (-40, -20, 0, 20):
            temperature_k = temperature_c + 273.15
            shift = slope * (1.0 / temperature_k - 1.0 / REFERENCE_K)
            moved = np.log10(WINDOW_HZ) + shift
            sweeps.append(
                Sweep(
                    temperature_k,
                    WINDOW_HZ,
                    master_storage(moved),
                    master_storage(moved) * 0.05,
                )
            )
        _, energy = fit_arrhenius(sweeps, REFERENCE_K)
        assert energy == pytest.approx(energy_true, rel=0.05)

    def test_양수가_아닌_에너지는_거절한다(self) -> None:
        """부호가 뒤집혔다는 것은 온도가 올라갈수록 느려진다는 뜻이다."""
        sweeps = []
        for temperature_c in (-40, -20, 0, 20):
            temperature_k = temperature_c + 273.15
            shift = -wlf_log_shift(temperature_k)  # 일부러 뒤집는다
            moved = np.log10(WINDOW_HZ) + shift
            sweeps.append(Sweep(temperature_k, WINDOW_HZ, master_storage(moved)))
        with pytest.raises(ViscoelasticError):
            fit_arrhenius(sweeps, REFERENCE_K)


class Test마스터커브:
    def test_잰_창보다_훨씬_넓어진다(self) -> None:
        """**이게 겹치는 이유 전부다.** 한 온도에서는 0.1~20 Hz 뿐이다."""
        curve = master_curve(SWEEPS, reference_temperature_k=REFERENCE_K)
        decades = math.log10(curve.frequency_hz[-1] / curve.frequency_hz[0])
        window_decades = math.log10(WINDOW_HZ[-1] / WINDOW_HZ[0])
        # 이 합성 상수(c1=8·c2=200, 온도 7단)에서 실측된 값은 5.7 자릿수다 —
        # 창 2.3 자릿수의 2.5배. 실파일은 6단으로 11 자릿수를 벌었다.
        assert decades > window_decades * 2, f"{decades:.2f} 자릿수뿐"

    def test_아는_마스터커브를_되찾는다(self) -> None:
        """겹친 결과가 원래 곡선과 같아야 한다. **부호를 뒤집으면 여기서 깨진다.**"""
        curve = master_curve(SWEEPS, reference_temperature_k=REFERENCE_K, points=120)
        expected = master_storage(np.log10(curve.frequency_hz))
        relative = np.abs(curve.storage_pa - expected) / expected
        assert float(np.max(relative)) < 0.02

    def test_손실_탄성률도_함께_겹친다(self) -> None:
        curve = master_curve(SWEEPS, reference_temperature_k=REFERENCE_K)
        assert curve.loss_pa is not None
        assert len(curve.loss_pa) == len(curve.storage_pa)

    def test_계수와_근거를_남긴다(self) -> None:
        curve = master_curve(SWEEPS, reference_temperature_k=REFERENCE_K)
        assert curve.parameters["c1"] == pytest.approx(C1_TRUE, rel=0.05)
        assert curve.method == "wlf"
        assert any("WLF" in note for note in curve.notes)

    def test_사람이_준_이동인자를_그대로_쓴다(self) -> None:
        """장비가 계산해 준 이동인자를 넣는 자리다."""
        factors = {sweep.temperature_k: wlf_log_shift(sweep.temperature_k) for sweep in SWEEPS}
        curve = master_curve(
            SWEEPS,
            reference_temperature_k=REFERENCE_K,
            method="manual",
            manual_shifts=factors,
        )
        expected = master_storage(np.log10(curve.frequency_hz))
        assert float(np.max(np.abs(curve.storage_pa - expected) / expected)) < 0.02

    def test_안_넓어지면_말한다(self) -> None:
        """**실측으로 걸렸다.** 강판(SECC) DMA 파일을 넣었더니 여섯 온도의 저장
        탄성률이 전부 같아서 이동인자가 0 으로 나왔다. 마스터커브는 그려지고
        계수도 나오는데(c1≈0) 아무 뜻이 없다.

        이 경고가 없으면 그 곡선 위에서 Prony 를 맞추고 해석에 넣게 된다.
        """
        flat = [
            Sweep(
                temperature_k=value + 273.15,
                frequency_hz=WINDOW_HZ,
                storage_pa=np.full_like(WINDOW_HZ, 2.0e11),
            )
            for value in (-40, -30, -20, -10, 0, 10, 20)
        ]
        curve = master_curve(
            flat,
            reference_temperature_k=REFERENCE_K,
            method="manual",
            manual_shifts={s.temperature_k: 0.0 for s in flat},
        )
        assert any("안 늘었습니다" in note for note in curve.notes), curve.notes

    def test_모르는_방법은_거절한다(self) -> None:
        with pytest.raises(ViscoelasticError, match="모르는 방법"):
            master_curve(SWEEPS, reference_temperature_k=REFERENCE_K, method="magic")
