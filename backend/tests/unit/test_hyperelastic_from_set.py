"""파라미터 벌 → 초탄성 블록(2026-10-08) — `matcore.cards.hyperelastic.from_parameter_set`.

문헌 벌의 항 이름은 출처마다 다르다(`C10` · `C1` · `mu`). 옮기는 규칙이 조용히 틀리면 고무
강성이 두 배 · 백만 배 틀린 덱이 오류 없이 돈다 — 그래서 받는 것과 안 받는 것을 못 박는다.
"""

from __future__ import annotations

import pytest

from matcore import export
from matcore.cards.hyperelastic import (
    HYPERELASTIC_ORDER,
    FromSet,
    from_parameter_set,
    stability,
)


def _ok(model: str, terms: dict[str, tuple[float, str]]) -> FromSet:
    made = from_parameter_set(model, terms)
    assert isinstance(made, FromSet), made
    return made


class Test큰_변형_안정성:
    """음의 고차 계수가 다 위험하지는 않다 — 경로마다 공칭 응력이 느는지 걷는다(2026-10-23).

    계수는 개발 DB 의 실측이다(Ecoflex 00-20 · Dragon Skin 10).
    """

    def test_압축_곡선으로_맞춘_Yeoh_는_인장_33_퍼센트에서_깨진다(self) -> None:
        found = stability({"c10": 18815.5, "c20": 18948.8, "c30": -41042.4})
        assert found is not None and not found.ok
        assert found.breaks["인장"] == pytest.approx(33.5, abs=0.6)
        assert found.breaks["등이축"] == pytest.approx(17.0, abs=0.6)
        assert set(found.weak) == {"인장", "압축", "등이축", "평면 전단"}
        assert found.describe().startswith("인장 33 % · 압축 29 %")

    def test_음수_계수여도_안정하면_통과한다(self) -> None:
        tension = stability({"c10": 21000.0, "c20": 897.4, "c30": -0.5306})
        dragon = stability({"c10": 24060.0, "c20": -170700.0, "c30": 2055000.0})
        assert tension is not None and tension.ok and tension.describe() == ""
        assert dragon is not None and dragon.ok

    def test_기본값_범위_밖에서만_깨지면_약하지_않다(self) -> None:
        """Mooney C01 < 0 — 압축 54 % 는 기본값 범위(50 %) 밖, 등이축 31 % 는 안."""
        found = stability({"c10": 21800.0, "c01": -7000.0})
        assert found is not None
        assert found.weak == ("등이축",) and "압축" in found.breaks

    def test_다항식_꼴이_아니면_모른다(self) -> None:
        assert stability({"mu": 1.0e5, "alpha": 2.0}) is None


def test_시험_모드는_칸_이름과_표기가_달라도_읽는다() -> None:
    from app.shared.hyperelastic_sets import mode_of

    assert mode_of({"mode": "tension"}) == "tension"
    assert mode_of({"deformation_mode": "uniaxial tension"}) == "tension"
    assert mode_of({"mode": "uniaxial_compression"}) == "compression"
    assert mode_of({"test_method": "uniaxial extension on Instron, 8 specimens"}) == "tension"
    assert mode_of({"mode": "equibiaxial tension"}) == "biaxial"
    assert mode_of({"mode": "inverse_fe_magnetic_bending"}) == "other"
    # 교정 전 값(`…_before_correction`)은 모드가 아니다.
    assert mode_of({"mode_before_correction": "uniaxial_tension"}) == ""


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


class Test2차_다항식:
    """3 · 5항 Mooney-Rivlin → 2차 다항식(2026-10-12). Cij 는 솔버마다 뜻이 같다."""

    def test_3항은_셋째_항이_C11_이든_C20_이든_받고_빠진_항은_0(self) -> None:
        c11 = _ok(
            "mooney_rivlin_3",
            {"C10": (367000.0, "Pa"), "C01": (-69000.0, "Pa"), "C11": (5000.0, "Pa")},
        )
        assert c11.family == "polynomial_2"
        assert c11.values == {
            "c10": 367000.0,
            "c01": -69000.0,
            "c11": 5000.0,
            "c20": 0.0,
            "c02": 0.0,
        }
        assert c11.note and "C20 · C02" in c11.note
        c20 = _ok(
            "mooney_rivlin_3",
            {"c10": (0.4, "MPa"), "c01": (0.1, "MPa"), "c20": (0.01, "MPa")},
        )
        assert c20.values["c20"] == pytest.approx(1e4) and c20.values["c11"] == 0.0

    def test_5항은_그대로(self) -> None:
        made = _ok(
            "mooney_rivlin_5",
            {
                name: (value, "Pa")
                for name, value in (
                    ("C10", 1e5),
                    ("C01", 2e4),
                    ("C20", 3e3),
                    ("C11", -4e3),
                    ("C02", 5e2),
                )
            },
        )
        assert made.values == {"c10": 1e5, "c01": 2e4, "c20": 3e3, "c11": -4e3, "c02": 5e2}
        assert made.note is None

    def test_표기에_없는_항이_섞이면_버리지_않고_거절한다(self) -> None:
        refused = from_parameter_set(
            "mooney_rivlin_3",
            {
                "C10": (1e5, "Pa"),
                "C01": (2e4, "Pa"),
                "C11": (1e3, "Pa"),
                "C20": (1e3, "Pa"),
            },
        )
        assert isinstance(refused, str) and "항 이름을 모릅니다" in refused

    def test_초기_전단탄성률이_0_이하면_거절한다(self) -> None:
        """문헌 실리콘 3항 벌(C10 = 21.8 kPa, C01 = -72.2 kPa) — 작은 변형에서 불안정하다."""
        refused = from_parameter_set(
            "mooney_rivlin_3",
            {"C10": (21800.0, "Pa"), "C01": (-72200.0, "Pa"), "C20": (12.6, "Pa")},
        )
        assert isinstance(refused, str) and "불안정" in refused
        assert isinstance(
            from_parameter_set("mooney_rivlin_2", {"C10": (1e4, "Pa"), "C01": (-2e4, "Pa")}),
            str,
        )
