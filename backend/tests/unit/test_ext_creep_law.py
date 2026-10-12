"""크리프 시험 → 최소 속도 → Norton · Garofalo → 덱(확장 `creep`, 2026-10-12).

답을 아는 합성 데이터로 잰다 — 식을 거꾸로 써서 만든 점에서 같은 상수가 돌아와야 한다:

    최소 속도    1차(감속) + 정상상태 + 3차(가속) 곡선에서 정상상태의 기울기
    Norton       A · n · Q 가 그대로(여러 온도), 한 온도면 Q 없이
    Garofalo     C1 · C2 · C3 · C4 가 그대로 — 멱법칙이 깨지는 높은 응력이 있을 때
    덱           TBOPT 10 의 A 를 MPa 계로 옮길 때 응력 단위가 n 제곱으로(10^(6n)) 들어간다
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import cards, export, extensions
from matcore.export.systems import MM_N_TONNE, SI
from matcore.groups import GroupError, Member
from matcore.processing import Frame

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
cards.load_builtin()

law = importlib.import_module(f"{extensions.PACKAGE}.creep.law")
creep_deck = importlib.import_module(f"{extensions.PACKAGE}.creep.deck")

R = law.GAS_CONSTANT


def test_최소_속도는_정상상태의_기울기다() -> None:
    """εc = 0.002(1 - e^(-t/50)) + 1e-6·t + 3차(t > 700 에서 가속)."""
    time = np.linspace(0.0, 1000.0, 501)
    creep = 0.002 * (1 - np.exp(-time / 50.0)) + 1e-6 * time
    creep += np.where(time > 700, 1e-9 * (time - 700) ** 2.5, 0.0)
    strain = 0.004 + creep
    result = law.creep_rate(Frame({"time": time, "strain": strain}, {}), {})
    scalars = {one.key: one.value for one in result.scalars}
    assert scalars["min_creep_rate"] == pytest.approx(1e-6, rel=0.03)
    assert scalars["creep_initial_strain"] == pytest.approx(0.004)
    assert result.frame.columns["creep_strain"][0] == 0.0


def _members(points: list[tuple[float, float, float]]) -> list[Member]:
    return [
        Member(
            label=f"T{index}",
            values={"applied_stress": sigma, "temperature": t, "min_creep_rate": rate},
        )
        for index, (sigma, t, rate) in enumerate(points)
    ]


def test_Norton_은_여러_온도에서_A_n_Q_를_되찾는다() -> None:
    a, n, q = 1e-30, 5.0, 80e3
    points = [
        (sigma, t, a * sigma**n * math.exp(-q / (R * t)))
        for sigma in (20e6, 40e6, 80e6)
        for t in (300.0, 350.0)
    ]
    outcome = law.creep_law(_members(points))
    assert outcome.values["norton_n"] == pytest.approx(n, rel=1e-6)
    assert outcome.values["norton_a"] == pytest.approx(a, rel=1e-6)
    assert outcome.values["activation_energy"] == pytest.approx(q, rel=1e-6)


def test_한_온도면_Q_없이_그_온도의_A() -> None:
    points = [(sigma, 300.0, 2e-30 * sigma**4) for sigma in (10e6, 30e6, 60e6)]
    outcome = law.creep_law(_members(points))
    assert "activation_energy" not in outcome.values
    assert outcome.values["norton_n"] == pytest.approx(4.0, rel=1e-6)
    assert any("Q 를 정하지 않았습니다" in one for one in outcome.warnings)


def test_Garofalo_는_멱법칙이_깨지는_곳에서_상수를_되찾는다() -> None:
    c1, c2, c3, c4 = 1e5, 2e-8, 4.0, 9000.0  # C2·σ 가 0.2~3 — 멱법칙이 깨진다
    points = [
        (sigma, t, c1 * math.sinh(c2 * sigma) ** c3 * math.exp(-c4 / t))
        for sigma in (10e6, 30e6, 60e6, 100e6, 150e6)
        for t in (300.0, 380.0)
    ]
    outcome = law.creep_law(_members(points))
    assert outcome.values["garofalo_c2"] == pytest.approx(c2, rel=0.03)
    assert outcome.values["garofalo_c3"] == pytest.approx(c3, rel=0.03)
    assert outcome.values["garofalo_c4"] == pytest.approx(c4, rel=0.01)
    blocks = law.card_blocks(outcome.values, outcome.detail, outcome.warnings)
    names = {(row["set"], row["name"]) for row in blocks["model_params"]["rows"]}
    assert (law.GAROFALO_SET, "C2") in names and (law.NORTON_SET, "A") in names


def test_멱법칙_데이터면_Garofalo_를_카드에_안_싣는다() -> None:
    points = [
        (sigma, t, 1e-30 * sigma**5 * math.exp(-9000.0 / t))
        for sigma in (10e6, 20e6, 40e6)
        for t in (300.0, 380.0)
    ]
    outcome = law.creep_law(_members(points))
    blocks = law.card_blocks(outcome.values, outcome.detail, outcome.warnings)
    assert {row["set"] for row in blocks["model_params"]["rows"]} == {law.NORTON_SET}
    assert any("멱법칙" in one for one in outcome.warnings)


def test_조건이_빠지면_누구인지_말한다() -> None:
    members = [Member(label="T1", values={"applied_stress": 1e7, "min_creep_rate": 1e-6})]
    with pytest.raises(GroupError, match="T1"):
        law.creep_law(members)


def _norton_deck(rows: list[dict[str, Any]]) -> export.Deck:
    return export.Deck(
        name="SAC",
        solver_id=3,
        blocks={
            "elastic": {"values": {"youngs_modulus": 50e9, "poisson_ratio": 0.35}},
            "model_params": {"rows": rows},
        },
    )


NORTON_ROWS = [
    {"group": law.NORTON_SET, "name": "A", "value": 1e-30, "unit": "1/(s.Pa^n)"},
    {"group": law.NORTON_SET, "name": "n", "value": 5.0, "unit": "1"},
    {"group": law.NORTON_SET, "name": "Q", "value": 80e3, "unit": "J/mol"},
]


def test_Norton_덱의_A_는_응력_단위가_n_제곱으로_옮겨진다() -> None:
    """MPa 계에서 σ 가 1e-6 배 → A 는 1e30 배(10^(6·5)). 응력 상수처럼 1e6 배로 옮기면
    크리프가 10²⁴ 배 틀린다."""
    _, si, with_q = creep_deck.norton(export.to_system(_norton_deck(NORTON_ROWS), SI))
    _, mm, _ = creep_deck.norton(export.to_system(_norton_deck(NORTON_ROWS), MM_N_TONNE))
    assert with_q and si[0] == pytest.approx(1e-30) and mm[0] == pytest.approx(1.0, rel=1e-9)
    assert mm[1] == 5.0 and mm[2] == pytest.approx(80e3 / R)
    # 같은 응력에서 같은 속도 — 계가 달라도 물리는 같다.
    sigma_pa = 50e6
    assert si[0] * sigma_pa**5 == pytest.approx(mm[0] * (sigma_pa * 1e-6) ** 5, rel=1e-9)


def test_Norton_덱은_TBOPT_10() -> None:
    text = export.render(
        "ansys_creep_norton", _norton_deck(NORTON_ROWS), MM_N_TONNE
    ).text.splitlines()
    assert "TB,CREEP,MNX_MAT,1,3,10" in text
    data = text[text.index("TB,CREEP,MNX_MAT,1,3,10") + 1].removeprefix("TBDATA,1,").split(",")
    assert [float(one) for one in data] == pytest.approx([1.0, 5.0, 80e3 / R])


def test_Norton_A_단위를_모르면_멈춘다() -> None:
    rows = [{**NORTON_ROWS[0], "unit": "1/s"}, *NORTON_ROWS[1:]]
    with pytest.raises(export.ExportError, match="n 제곱"):
        creep_deck.norton(export.to_system(_norton_deck(rows), MM_N_TONNE))


def test_Garofalo_덱은_묶음의_Garofalo_벌을_고른다() -> None:
    rows = [
        *NORTON_ROWS,
        {"group": law.GAROFALO_SET, "name": "C1", "value": 1e5, "unit": "1/s"},
        {"group": law.GAROFALO_SET, "name": "C2", "value": 2e-8, "unit": "1/Pa"},
        {"group": law.GAROFALO_SET, "name": "C3", "value": 4.0, "unit": "1"},
        {"group": law.GAROFALO_SET, "name": "C4", "value": 9000.0, "unit": "K"},
    ]
    where, constants = creep_deck.garofalo(export.to_system(_norton_deck(rows), MM_N_TONNE))
    assert where == law.GAROFALO_SET
    # C2 는 1/응력 — MPa 계에서 1e6 배.
    assert constants[1] == pytest.approx(2e-2)
