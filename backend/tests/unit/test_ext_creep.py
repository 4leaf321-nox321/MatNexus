"""Garofalo 크리프 덱(확장 `creep`, 2026-10-08) — ANSYS `TB,CREEP` TBOPT 8.

무는 것:

    단위          C1 → 1/시간, C2 → 1/(덱의 응력 단위), C4 → Q/R(K)
                  — J/mol · kJ/mol · eV 를 옮긴다
    같은 꼴만      Darveaux 꼴(K/s/psi) · 전단 기준 · 앞인자 없는 벌은 까닭을 들고 멈춘다
    합치기         모델 글자만 다른 두 벌(같은 set_id)은 한 벌로 본다 — 문헌에 실재한다
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from matcore import cards, export, extensions
from matcore.export.systems import MM_N_TONNE, SI

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
cards.load_builtin()


def _deck(rows: list[dict[str, Any]]) -> export.Deck:
    return export.Deck(
        name="SAC387",
        solver_id=9,
        blocks={
            "elastic": {"values": {"youngs_modulus": 50e9, "poisson_ratio": 0.36}},
            "model_params": {"values": {"sets": 1, "models": "garofalo"}, "rows": rows},
        },
    )


def _rows(
    group: str, terms: list[tuple[str, float, str]], model: str = "garofalo"
) -> list[dict[str, Any]]:
    return [
        {"set": f"{model}/{group}", "group": group, "name": n, "value": v, "unit": u}
        for n, v, u in terms
    ]


def _tbdata(text: str) -> list[float]:
    line = next(one for one in text.splitlines() if one.startswith("TBDATA,"))
    return [float(one) for one in line.split(",")[2:]]


#: Pang 2004 SAC387 — ANSYS 꼴 그대로.
PANG = [("C1", 32000.0, "1/s"), ("C2", 0.037, "1/MPa"), ("C3", 5.1, "1"), ("C4", 6524.7, "K")]


def test_ANSYS_꼴은_단위계로_옮긴다() -> None:
    mm = export.render("ansys_creep", _deck(_rows("pang2004", PANG)), MM_N_TONNE)
    assert "TB,CREEP,MNX_MAT,1,4,8" in mm.text
    assert _tbdata(mm.text) == pytest.approx([32000.0, 0.037, 5.1, 6524.7])
    si = export.render("ansys_creep", _deck(_rows("pang2004", PANG)), SI)
    # C2·σ 는 무차원 — σ 가 Pa 면 C2 는 1/Pa.
    assert _tbdata(si.text) == pytest.approx([32000.0, 0.037e-6, 5.1, 6524.7])


def test_활성화_에너지를_Q_R_로_옮긴다() -> None:
    terms = [("A", 809000.0, "1/s"), ("alpha", 0.115, "1/MPa"), ("n", 5.02, "1")]
    for q, unit, expected in (
        (50.5, "kJ/mol", 50500.0 / 8.314462618),
        (71300.0, "J/mol", 71300.0 / 8.314462618),
        (0.548, "eV", 0.548 / 8.617333262e-5),
    ):
        made = export.render(
            "ansys_creep", _deck(_rows("x", [*terms, ("Q", q, unit)])), MM_N_TONNE
        )
        assert _tbdata(made.text)[3] == pytest.approx(expected)


def test_모델_글자만_다른_두_벌은_합친다() -> None:
    """Shirley 2009 — C1 만 모델 글자가 다른 벌로 들어왔다. 모델 글자에 `/` 도 들었다."""
    rows = _rows(
        "shirley2009",
        [
            ("C2 (= ANSYS a, alpha)", 1.15e-07, "1/Pa"),
            ("C3 (= ANSYS n)", 5.02, "1"),
            ("C4 (= ANSYS Q/R)", 10100.0, "K"),
        ],
        model="ANSYS generalized Garofalo (Eq. 7)",
    ) + _rows(
        "shirley2009",
        [("C1 (= ANSYS A)", 809000.0, "1/s")],
        model="eps_dot = C1[sinh(C2*sigma)]^C3 exp(-C4/T)",
    )
    made = export.render("ansys_creep", _deck(rows), MM_N_TONNE)
    # 1.15e-7 /Pa = 0.115 /MPa
    assert _tbdata(made.text) == pytest.approx([809000.0, 0.115, 5.02, 10100.0])


@pytest.mark.parametrize(
    ("group", "terms", "said"),
    [
        (
            "darveaux1992_tensile",
            [
                ("C1", 0.114, "K/s/(lbf/in^2)"),
                ("alpha", 751.0, "1"),
                ("n", 3.3, "1"),
                ("Q", 0.548, "eV"),
            ],
            "Darveaux",
        ),
        (
            "zhang2004_shear",
            [
                ("A", 1500.0, "1/s"),
                ("alpha", 0.19, "1/MPa"),
                ("n", 4.0, "1"),
                ("Q", 71300.0, "J/mol"),
            ],
            "전단 기준",
        ),
        (
            "hammad2017_25c",
            [("alpha", 0.034, "1/MPa"), ("n", 5.4, "1"), ("Q", 50.5, "kJ/mol")],
            "앞인자",
        ),
    ],
)
def test_같은_꼴이_아니면_까닭을_들고_멈춘다(
    group: str, terms: list[tuple[str, float, str]], said: str
) -> None:
    with pytest.raises(export.ExportError, match=said):
        export.render("ansys_creep", _deck(_rows(group, terms)), SI)
