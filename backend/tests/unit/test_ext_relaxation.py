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


def test_온도가_섞이면_말한다() -> None:
    outcome = prony_time.relaxation_prony([_member("R1", 296.15), _member("R2", 323.15)])
    assert any("섞여" in one for one in outcome.warnings)


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
