"""덱의 **단위계** — 값과 선언이 함께 움직이는가.

단위계가 섞인 덱은 조용히 1000배 틀린 답을 낸다. 그래서 이 파일이 보는 것은
두 가지다.

  1. 값이 정확히 그 계로 바뀌는가
  2. 덱이 **자기 계를 말하는가** — 값만 바뀌고 선언이 안 바뀌면 최악이다.
     받는 사람은 덱을 읽고 SI 라고 믿는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from matcore import cards, export
from matcore.export.systems import MM_N_TONNE, SI

cards.load_builtin()

#: 강판 한 장. 전부 SI 로 적는다.
DECK = export.Deck(
    name="SECC",
    solver_id=1,
    blocks={
        "elastic": {
            "values": {
                "youngs_modulus": 206e9,  # 206 GPa
                "poisson_ratio": 0.3,
                "density": 7850.0,  # kg/m3
            }
        },
        "table": {
            "rows": [
                {"plastic_strain": 0.0, "true_stress": 400e6},
                {"plastic_strain": 0.02, "true_stress": 450e6},
                {"plastic_strain": 0.05, "true_stress": 500e6},
            ]
        },
    },
)


def values(deck: export.Deck) -> dict[str, Any]:
    return deck.values("elastic")


class Test값이바뀐다:
    def test_SI_는_그대로다(self) -> None:
        """**고르지 않으면 전과 같은 것이 나가야 한다.**"""
        moved = export.to_system(DECK, SI)
        assert values(moved)["youngs_modulus"] == pytest.approx(206e9)
        assert values(moved)["density"] == pytest.approx(7850.0)

    def test_mm_계로_바뀐다(self) -> None:
        moved = export.to_system(DECK, MM_N_TONNE)
        # 206 GPa = 206000 MPa
        assert values(moved)["youngs_modulus"] == pytest.approx(206000.0)
        # 7850 kg/m3 = 7.85e-9 tonne/mm3
        assert values(moved)["density"] == pytest.approx(7.85e-9)
        # 400 MPa
        assert moved.rows("table")[0]["true_stress"] == pytest.approx(400.0)

    def test_무차원은_안_건드린다(self) -> None:
        """푸아송비와 변형률은 어느 계에서나 같은 숫자다. 여기에 인수가 끼면
        0.3 이 3e5 가 되는데, 솔버는 그것도 받아서 돈다."""
        moved = export.to_system(DECK, MM_N_TONNE)
        assert values(moved)["poisson_ratio"] == pytest.approx(0.3)
        assert moved.rows("table")[1]["plastic_strain"] == pytest.approx(0.02)

    def test_온도는_오프셋이_없다(self) -> None:
        """절대온도는 두 계가 같다. 섭씨로 바꾸면 솔버가 절대온도로 읽어
        273 만큼 어긋난다 — 그 덱은 상온 해석을 절대영도 근처에서 돈다."""
        deck = export.Deck(
            name="T",
            solver_id=1,
            blocks={"thermal": {"values": {"reference_temperature": 298.15}}},
        )
        moved = export.to_system(deck, MM_N_TONNE)
        assert moved.values("thermal")["reference_temperature"] == pytest.approx(298.15)


class Test덱이_자기_계를_말한다:
    def test_선언이_값을_따라간다(self) -> None:
        """**값만 바뀌고 선언이 안 바뀌면 최악이다.** 받는 사람은 덱을 읽고
        SI 라고 믿는다 — 숫자가 그럴듯해서 검산도 안 한다."""
        si = export.render("abaqus", DECK, SI).text
        mm = export.render("abaqus", DECK, MM_N_TONNE).text
        assert "kg, m, s, Pa" in si
        assert "tonne, mm, s, MPa" in mm
        assert "2.060000000000E+11" in si
        assert "2.060000000000E+05" in mm

    def test_솔버_단위_블록도_따라간다(self) -> None:
        """OpenRadioss 는 단위 블록이 있다 — **솔버가 그것을 그대로 믿는다.**"""
        mm = export.render("openradioss", DECK, MM_N_TONNE).text
        assert "MNX_TONNE_MM_S" in mm
        assert "tonne               mm                  s" in mm
        assert "MNX_KG_M_S" not in mm

    def test_기본은_SI_다(self) -> None:
        assert export.render("abaqus", DECK).text == export.render("abaqus", DECK, SI).text


class Test모르면_말한다:
    """처음에는 멈추게 했는데 **실제 카드가 바로 걸렸다.** 경화식 블록은
    `values` 가 열려 있다 — 식마다 다른 파라미터가 들어오므로 선언에 다 적을
    수가 없다. 그리고 그 블록은 애초에 덱에 안 실린다.

    그래서 그대로 두되 **이름을 덱에 적는다.** 조용히 남는 것과 적혀서 남는
    것은 다르다.
    """

    OPEN = export.Deck(
        name="X",
        solver_id=1,
        blocks={
            "elastic": {
                "values": {
                    "youngs_modulus": 206e9,
                    "poisson_ratio": 0.3,
                    "density": 7850.0,
                    "없는칸": 1.0,
                }
            },
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 400e6},
                    {"plastic_strain": 0.02, "true_stress": 450e6},
                    {"plastic_strain": 0.05, "true_stress": 500e6},
                ]
            },
        },
    )

    def test_안_바꾸고_그대로_둔다(self) -> None:
        moved = export.to_system(self.OPEN, MM_N_TONNE)
        assert moved.values("elastic")["없는칸"] == 1.0
        # 선언된 것은 바뀐다 — 하나가 열려 있다고 전부를 포기하지 않는다.
        assert moved.values("elastic")["density"] == pytest.approx(7.85e-9)

    def test_덱에_적는다(self) -> None:
        """**조용히 남기지 않는다.** 덱만 받은 사람이 그 숫자를 의심할 수
        있어야 한다."""
        text = export.render("abaqus", self.OPEN, MM_N_TONNE).text
        assert "없는칸" in text
        assert "SI 로 남긴 값" in text

    def test_SI_로는_아무_말도_안_한다(self) -> None:
        """SI 는 바꿀 것이 없다. 여기까지 적으면 전과 다른 덱이 나간다."""
        assert "SI 로 남긴 값" not in export.render("abaqus", self.OPEN, SI).text

    def test_선언은_됐는데_기호가_없으면_멈춘다(self) -> None:
        """그건 표의 구멍이지 데이터의 성질이 아니다."""
        crippled = export.systems.UnitSystem(
            key="x", label="X", mass="kg", length="m", time="s", symbols={"1": "1"}
        )
        with pytest.raises(export.ExportError) as caught:
            export.to_system(DECK, crippled)
        assert "Pa" in str(caught.value)


class Test행이_자기_단위를_들면:
    def test_그것이_이긴다(self) -> None:
        """경화식 파라미터는 식마다 단위가 다르다 — Voce 의 `b` 는 무차원이고
        `q` 는 Pa 다. 열 선언 하나로는 못 적어서 행이 들고 온다."""
        deck = export.Deck(
            name="X",
            solver_id=1,
            blocks={
                "hardening": {
                    "rows": [
                        {"name": "q", "value": 300e6, "si_unit": "Pa"},
                        {"name": "b", "value": 12.0, "si_unit": "1"},
                    ]
                }
            },
        )
        rows = export.to_system(deck, MM_N_TONNE).rows("hardening")
        assert rows[0]["value"] == pytest.approx(300.0)  # 300 MPa
        assert rows[1]["value"] == pytest.approx(12.0)  # 무차원 그대로


class Test고르기:
    def test_key_로_고른다(self) -> None:
        assert export.systems.get("mm_n_tonne") is MM_N_TONNE
        assert export.systems.get("si") is SI

    def test_안_고르면_SI_다(self) -> None:
        assert export.systems.get(None) is SI
        assert export.systems.get("") is SI

    def test_모르는_key_는_거절한다(self) -> None:
        with pytest.raises(KeyError):
            export.systems.get("mks")
