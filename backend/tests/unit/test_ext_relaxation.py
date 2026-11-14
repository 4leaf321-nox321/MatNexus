"""응력완화 → E(t) → 시간 영역 Prony → 점탄성 카드(확장 `relaxation`, 2026-10-12).

답을 아는 스펙트럼 E(t) = 1 + 2·e^(-t/10) + 1·e^(-t/1000) GPa 를 자릿수 τ 격자에 맞췄을 때:

    장기 · 순간 탄성률   E∞ = 1 GPa · E₀ = 4 GPa 가 돌아오는가
    카드                 탄성계수 = 순간 탄성률 — 점탄성 덱이 E 를 순간 값으로 읽고 gᵢ 를
                        곱한다. gᵢ 의 합이 1 - E∞/E₀ 인가
    유지 변형률          열이 있으면 그 평균, 없으면 조건 — 둘 다 없으면 멈춘다
"""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from matcore import cards, extensions
from matcore.groups import GroupError, Member
from matcore.processing import Frame, ProcessingError

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
cards.load_builtin()

prony_time = importlib.import_module(f"{extensions.PACKAGE}.relaxation.prony_time")

TIME = np.logspace(-1, 4, 80)
MODULUS = 1e9 + 2e9 * np.exp(-TIME / 10.0) + 1e9 * np.exp(-TIME / 1000.0)


def _member(label: str = "R1", temperature: float = 296.15) -> Member:
    return Member(
        label=label,
        columns={"time": TIME, "relaxation_modulus": MODULUS},
        values={"temperature": temperature},
    )


def test_답을_아는_스펙트럼에서_장기_순간_탄성률이_돌아온다() -> None:
    outcome = prony_time.relaxation_prony([_member()])
    assert outcome.values["equilibrium_pa"] == pytest.approx(1e9, rel=0.02)
    assert outcome.values["instantaneous_pa"] == pytest.approx(4e9, rel=0.02)
    assert outcome.values["normalized_rmse"] < 0.01
    assert outcome.values["reference_temperature_k"] == pytest.approx(296.15)
    assert any("가장 이른 측정" in one for one in outcome.warnings)


def test_카드의_탄성계수는_순간_탄성률이고_g_의_합은_1_빼기_E무한_E0() -> None:
    outcome = prony_time.relaxation_prony([_member()])
    blocks = prony_time.card_blocks(outcome.values, outcome.detail, outcome.warnings)
    instantaneous = outcome.values["instantaneous_pa"]
    assert blocks["elastic"]["values"] == {"youngs_modulus": instantaneous}
    rows = blocks["viscoelastic"]["rows"]
    total = sum(row["relative_modulus"] for row in rows)
    assert total == pytest.approx(1 - outcome.values["equilibrium_pa"] / instantaneous)
    assert all(row["relaxation_time_s"] > 0 and row["modulus_pa"] > 0 for row in rows)


def test_온도가_섞이면_묶지_않는다() -> None:
    """2026-11-15(VOC 52) — 전에는 옮기지 않은 채 한데 맞추고 경고만 달아 카드까지 냈다. 20 ·
    40 · 60 °C 를 넣으면 40 °C 로 적힌 카드가 그 온도의 참값과 1.72배 틀렸다(합성 실측)."""
    with pytest.raises(GroupError, match="섞여"):
        prony_time.relaxation_prony([_member("R1", 296.15), _member("R2", 323.15)])
    # 2 K 안은 같은 온도다 — 기록의 반올림 차이.
    near = prony_time.relaxation_prony([_member("R1", 296.15), _member("R2", 297.65)])
    assert near.values["reference_temperature_k"] == pytest.approx(296.9)


def test_관측_시간이_짧으면_멈춘다() -> None:
    short = Member(
        label="R1",
        columns={
            "time": np.linspace(1, 5, 20),
            "relaxation_modulus": np.linspace(2e9, 1.9e9, 20),
        },
    )
    with pytest.raises(GroupError, match="한 자릿수"):
        prony_time.relaxation_prony([short])


def test_유지_변형률은_열이_먼저_없으면_조건() -> None:
    time = np.linspace(0, 100, 11)
    stress = np.linspace(10e6, 8e6, 11)
    with_column = prony_time.relaxation_modulus(
        Frame({"time": time, "stress": stress, "strain": np.full(11, 0.005)}, {}),
        {"held_strain": 0.004},
    )
    assert with_column.frame.columns["relaxation_modulus"][0] == pytest.approx(10e6 / 0.005)
    assert any("5% 넘게" in one for one in with_column.notes)
    stated = prony_time.relaxation_modulus(
        Frame({"time": time, "stress": stress}, {}), {"held_strain": 0.004}
    )
    assert stated.frame.columns["relaxation_modulus"][0] == pytest.approx(10e6 / 0.004)
    scalars = {one.key: one.value for one in stated.scalars}
    assert scalars["relaxed_fraction"] == pytest.approx(0.2)
    with pytest.raises(ProcessingError, match="유지 변형률"):
        prony_time.relaxation_modulus(Frame({"time": time, "stress": stress}, {}), {})


class Test순간_탄성률은_첫_측정_안으로_묶는다:
    """VOC 52(2026-11-14) — τ 격자가 10^⌊log t_min⌋ 부터라, 첫 측정이 0.95 s 면 E₀ 1145 GPa,
    1.0 s 면 2.19 GPa(539배)였다. 측정 전에 풀린 빠른 항(τ 0.3 s)이 있는 스펙트럼으로 본다."""

    @staticmethod
    def _fast(start: float) -> Member:
        time = np.logspace(np.log10(start), 4, 80)
        modulus = (
            1e9
            + 2e9 * np.exp(-time / 10.0)
            + 1e9 * np.exp(-time / 1000.0)
            + 3e9 * np.exp(-time / 0.3)
        )
        return Member(label="R1", columns={"time": time, "relaxation_modulus": modulus})

    def test_가장_짧은_τ_는_첫_측정_시각이다(self) -> None:
        assert prony_time.taus(0.95, 1e4)[0] == pytest.approx(0.95)
        assert prony_time.taus(1.0, 1e4)[0] == pytest.approx(1.0)
        assert min(prony_time.taus(0.15, 100.0)) >= 0.15

    def test_첫_측정_시각이_조금_달라도_E0_가_뛰지_않는다(self) -> None:
        early = prony_time.relaxation_prony([self._fast(0.95)]).values
        late = prony_time.relaxation_prony([self._fast(1.0)]).values
        assert early["instantaneous_pa"] == pytest.approx(late["instantaneous_pa"], rel=0.1)
        for values in (early, late):
            assert values["instantaneous_ratio"] <= np.e + 1e-9

    def test_외삽_배수가_크면_경고하고_카드에_시간_범위를_싣는다(self) -> None:
        # 첫 측정 무렵에 크게 풀리는 항(τ 1.5 s · 20 GPa) — E₀ 의 큰 몫이 측정 앞에 있다.
        time = np.logspace(np.log10(0.95), 4, 80)
        modulus = 1e9 + 2e9 * np.exp(-time / 10.0) + 20e9 * np.exp(-time / 1.5)
        member = Member(label="R1", columns={"time": time, "relaxation_modulus": modulus})
        outcome = prony_time.relaxation_prony([member])
        ratio = outcome.values["instantaneous_ratio"]
        assert ratio > 1.5
        assert any("강성의" in one and "외삽" in one for one in outcome.warnings)
        blocks = prony_time.card_blocks(outcome.values, outcome.detail, outcome.warnings)
        values = blocks["viscoelastic"]["values"]
        assert values["time_min_s"] == pytest.approx(0.95)
        assert values["time_max_s"] == pytest.approx(1e4)
        assert values["instantaneous_ratio"] == pytest.approx(ratio)

    def test_빠른_항이_없으면_경고하지_않는다(self) -> None:
        outcome = prony_time.relaxation_prony([_member()])
        assert outcome.values["instantaneous_ratio"] < 1.5
        assert not any("강성의" in one for one in outcome.warnings)
