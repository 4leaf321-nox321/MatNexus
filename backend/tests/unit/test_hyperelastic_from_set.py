"""파라미터 벌 → 초탄성 블록(2026-10-08) — `matcore.cards.hyperelastic.from_parameter_set`.

문헌 벌의 항 이름은 출처마다 다르다(`C10` · `C1` · `mu`). 옮기는 규칙이 조용히 틀리면 고무
강성이 두 배 · 백만 배 틀린 덱이 오류 없이 돈다 — 그래서 받는 것과 안 받는 것을 못 박는다.
"""

from __future__ import annotations

import pytest

from matcore import export
from matcore.cards.hyperelastic import HYPERELASTIC_ORDER, FromSet, from_parameter_set


def _ok(model: str, terms: dict[str, tuple[float, str]]) -> FromSet:
    made = from_parameter_set(model, terms)
    assert isinstance(made, FromSet), made
    return made


def test_계수_차례가_덱과_같다() -> None:
    assert HYPERELASTIC_ORDER == export.HYPERELASTIC_PARAMETERS


def test_원래_표기도_옮긴다() -> None:
    """Mooney 의 C1 · C2, Yeoh 의 C1 · C2 · C3 는 식마다 뜻이 정해져 있다."""
    assert _ok("mooney_rivlin_2", {"C1": (180000.0, "Pa"), "C2": (11700.0, "Pa")}).values == {
        "c10": 180000.0,
        "c01": 11700.0,
    }
    assert _ok(
        "yeoh_3", {"C1": (1000.0, "Pa"), "C2": (13100.0, "Pa"), "C3": (20.56, "Pa")}
    ).values == {"c10": 1000.0, "c20": 13100.0, "c30": 20.56}


def test_Neo_Hookean_은_mu_를_반으로_C1_은_안_받는다() -> None:
    """C1 은 출처마다 μ 이기도 μ/2 이기도 하다 — 옮기면 둘 중 하나는 강성이 두 배로 틀린다."""
    made = _ok("neo_hookean", {"mu": (22640.0, "Pa")})
    assert made.family == "neo_hookean" and made.values == {"c10": pytest.approx(11320.0)}
    refused = from_parameter_set("neo_hookean", {"C1": (25965.0, "Pa")})
    assert isinstance(refused, str) and "C1" in refused


def test_2항_Yeoh_는_C30_을_0_으로() -> None:
    made = _ok("yeoh_2", {"C10": (243000.0, "Pa"), "C20": (-4000.0, "Pa")})
    assert made.family == "yeoh" and made.values["c30"] == 0.0
    assert made.note and "C30 = 0" in made.note


def test_단위를_SI_로_옮기고_응력이_아니면_멈춘다() -> None:
    assert _ok("mooney_rivlin_2", {"C10": (0.6, "MPa"), "C01": (0.15, "MPa")}).values == {
        "c10": pytest.approx(0.6e6),
        "c01": pytest.approx(0.15e6),
    }
    refused = from_parameter_set("mooney_rivlin_2", {"C10": (0.6, "1"), "C01": (0.15, "1")})
    assert isinstance(refused, str) and "응력 단위" in refused


def test_덱이_받는_식이_아니면_까닭을_말한다() -> None:
    refused = from_parameter_set("ogden_N3", {"mu1": (1.0, "Pa")})
    assert isinstance(refused, str) and "ogden_N3" in refused
