"""Anand 점소성 덱(확장 `anand`, 2026-10-08) — ANSYS `TB,RATE,,,,ANAND`.

무는 것:

    차례          TBDATA 1~9 = s0 · Q/R · A · ξ · m · h0 · ŝ · n · a (ANSYS 이론 안내서 표 4.3)
    단위          항마다 다른 단위를 덱 단위계로 옮긴다 — mm·N·tonne 면 MPa 그대로, SI 면 Pa
    거절          9항이 다 있는 벌이 없거나 둘이거나, 항의 단위가 그 차원이 아니면 멈춘다
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from matcore import cards, export, extensions
from matcore.export.systems import MM_N_TONNE, SI

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
cards.load_builtin()

#: Basit 2015 의 SAC405 — 카탈로그에 이 꼴로 들어 있다(항마다 단위).
SAC405: list[tuple[str, float, str]] = [
    ("a", 1.77, "1"),
    ("A", 3175.0, "1/s"),
    ("h0", 183000.0, "MPa"),
    ("m", 0.263, "1"),
    ("n", 0.011, "1"),
    ("Q/R", 9580.0, "K"),
    ("s_hat", 31.3, "MPa"),
    ("s0", 23.65, "MPa"),
    ("xi", 4.0, "1"),
]


def _deck(rows: list[dict[str, Any]]) -> export.Deck:
    return export.Deck(
        name="SAC405",
        solver_id=7,
        blocks={
            "elastic": {"values": {"youngs_modulus": 45e9, "poisson_ratio": 0.36}},
            "model_params": {"values": {"sets": 1, "models": "anand"}, "rows": rows},
        },
    )


def _rows(
    set_name: str = "anand/basit2015", terms: list[tuple[str, float, str]] = SAC405
) -> list[dict[str, Any]]:
    return [{"set": set_name, "name": n, "value": v, "unit": u} for n, v, u in terms]


def _tbdata(text: str) -> list[float]:
    values: list[float] = []
    for line in text.splitlines():
        if line.startswith("TBDATA,"):
            values.extend(float(one) for one in line.split(",")[2:])
    return values


def test_차례와_단위계() -> None:
    mm = export.render("ansys_anand", _deck(_rows()), MM_N_TONNE)
    assert "TB,RATE,MNX_MAT,,,ANAND" in mm.text
    # s0, Q/R, A, xi, m, h0, s_hat, n, a — 응력은 MPa 그대로.
    assert _tbdata(mm.text) == pytest.approx(
        [23.65, 9580.0, 3175.0, 4.0, 0.263, 183000.0, 31.3, 0.011, 1.77]
    )
    si = export.render("ansys_anand", _deck(_rows()), SI)
    assert _tbdata(si.text) == pytest.approx(
        [23.65e6, 9580.0, 3175.0, 4.0, 0.263, 183000.0e6, 31.3e6, 0.011, 1.77]
    )
    assert "s0, h0, s_hat in Pa" in si.text


def test_9항이_다_있는_벌이_없으면_빠진_항을_대고_멈춘다() -> None:
    with pytest.raises(export.ExportError, match="빠진 항: xi"):
        # 줄 수는 9 라 형식 판정은 지나간다 — 항 하나가 다른 이름(xi 대신 zeta)이다.
        export.render(
            "ansys_anand", _deck(_rows(terms=[*SAC405[:-1], ("zeta", 4.0, "1")])), SI
        )


def test_벌이_둘이면_고르지_않는다() -> None:
    rows = _rows("anand/one") + _rows("anand/two")
    with pytest.raises(export.ExportError, match="2개"):
        export.render("ansys_anand", _deck(rows), SI)


def test_응력_항의_단위가_무차원이면_멈춘다() -> None:
    """문헌 값의 단위 칸이 「1」 로 오면 MPa 를 Pa 로 읽어 백만 배 틀린 솔더가 오류 없이
    돈다."""
    broken = [(n, v, "1" if n == "s0" else u) for n, v, u in SAC405]
    with pytest.raises(export.ExportError, match="s0 의 단위"):
        export.render("ansys_anand", _deck(_rows(terms=broken)), SI)
