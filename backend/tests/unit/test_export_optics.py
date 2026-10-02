"""광학 형식 — Zemax AGF · CODE V 사설 유리 · n,k 표(2026-10-02, ADR 0052).

**파장 단위가 형식마다 다르다**(AGF µm · CODE V nm · n,k 표 µm). 카드는 m 로 든다 — 옮기기를
빠뜨리면 587.6 nm 가 5.876e-07 µm 로 적히고, 읽는 쪽은 그것을 파장 범위 밖으로 버린다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from matcore import cards, dispersion, export
from matcore.export import optics  # noqa: F401  (렌더러 등록)
from matcore.export.systems import MM_N_TONNE, SI

cards.load_builtin()


def pmma(wavelength_um: float) -> float:
    """PMMA 의 Sellmeier 식(Szczurowski 2013) — 시험용 「잰 값」."""
    l2 = wavelength_um**2
    return math.sqrt(
        1
        + 0.99654 * l2 / (l2 - 0.00787)
        + 0.18964 * l2 / (l2 - 0.02191)
        + 0.00411 * l2 / (l2 - 3.85727)
    )


WAVELENGTHS_UM = [0.4358, 0.4861, 0.5461, 0.5876, 0.6563, 0.7065, 0.8521, 1.014]
ROWS = [
    {"wavelength": at * 1e-6, "refractive_index": round(pmma(at), 5)} for at in WAVELENGTHS_UM
]
ROWS[3]["extinction_coefficient"] = 1e-8

PMMA: dict[str, Any] = {
    "optical": {
        "values": {
            "refractive_index": ROWS[0]["refractive_index"],
            "refractive_index_wavelength_m": ROWS[0]["wavelength"],
        },
        "rows": ROWS,
    },
    "thermal": {"values": {"thermal_expansion": 7.0e-5}},
    "elastic": {"values": {"density": 1190.0}},
}


def deck(blocks: dict[str, Any]) -> export.Deck:
    return export.Deck(name="PMMA_OPT", solver_id=3, blocks=blocks, provenance=("재료 PMMA",))


def fields(text: str, label: str) -> list[str]:
    return next(line for line in text.splitlines() if line.startswith(f"{label} ")).split()[1:]


class TestZemaxAGF:
    def test_계수가_잰_굴절률을_되살린다(self) -> None:
        """**AGF 를 다시 읽어** 식으로 굴절률을 셈해 본다 — 카탈로그 굴절률은 소수 다섯째
        자리를 다툰다. 잰 값이 다섯 자리로 반올림돼 있어 그만큼은 벗어난다."""
        text = export.render("zemax_agf", deck(PMMA), MM_N_TONNE).text
        name, formula, _mil, nd, vd = fields(text, "NM")
        assert (name, formula) == ("PMMA_OPT", "1")
        coefficients = tuple(float(one) for one in fields(text, "CD"))
        for row in ROWS:
            at = row["wavelength"] * 1e6
            got = dispersion.schott_index(coefficients, at)  # type: ignore[arg-type]
            assert got == pytest.approx(row["refractive_index"], abs=1e-5)
        assert float(nd) == pytest.approx(pmma(dispersion.LINE_D), abs=1e-5)
        assert float(vd) == pytest.approx(58.0, abs=0.1)

    def test_파장은_µm_이고_밀도_열팽창은_카탈로그_단위다(self) -> None:
        text = export.render("zemax_agf", deck(PMMA), MM_N_TONNE).text
        assert fields(text, "LD") == ["0.4358", "1.014"]
        tce, _, grams, _, _ = fields(text, "ED")
        assert float(tce) == pytest.approx(70.0)  # 1e-6/K
        assert float(grams) == pytest.approx(1.19)  # g/cm³

    def test_소광계수는_내부_투과율로_적고_두께를_말한다(self) -> None:
        made = export.render("zemax_agf", deck(PMMA), SI)
        at, transmittance, thickness = fields(made.text, "IT")
        assert at == "0.5876" and thickness == "10"
        expected = math.exp(-4 * math.pi * 1e-8 * 0.01 / 0.5876e-6)
        assert float(transmittance) == pytest.approx(expected, abs=1e-6)
        assert any("10 mm 의 내부 투과율" in note for note in made.notes)

    def test_맞춘_결과를_늘_말한다(self) -> None:
        made = export.render("zemax_agf", deck(PMMA), SI)
        assert made.notes[0].startswith("Schott 식(항 6개)을 파장 8점")

    def test_점이_셋보다_적으면_못_낸다(self) -> None:
        few = {"optical": {"values": {"refractive_index": 1.49}, "rows": ROWS[:2]}}
        assert export.missing_for(deck(few), "zemax_agf")


class TestCODEV:
    def test_파장은_nm_이고_굴절률을_그대로_넘긴다(self) -> None:
        text = export.render("codev_prv", deck(PMMA), MM_N_TONNE).text
        got = text.splitlines()
        assert got[1:3] == ["PRV", "PWL 435.8 486.1 546.1 587.6 656.3 706.5 852.1 1014"]
        # CODE V 는 이름의 `_` 를 「유리_카탈로그」 로 읽는다 — 영숫자만 남긴다(ray-optics 의
        # CODE V 리더로 확인: `_` 가 있으면 그 사설 유리를 못 찾는다).
        assert got[3].startswith("'PMMAOPT' 1.501")
        assert got[-1] == "END"

    def test_파장을_모르는_굴절률은_거절한다(self) -> None:
        bare = {"optical": {"values": {"refractive_index": 1.49}}}
        with pytest.raises(export.ExportError, match="파장이 카드에 없습니다"):
            export.render("codev_prv", deck(bare), SI)

    def test_값_하나면_분산이_없다고_말한다(self) -> None:
        one = {
            "optical": {
                "values": {
                    "refractive_index": 1.5168,
                    "refractive_index_wavelength_m": 5.876e-7,
                }
            }
        }
        made = export.render("codev_prv", deck(one), SI)
        assert "PWL 587.6" in made.text
        assert any("분산이 없는 재료" in note for note in made.notes)


class TestNK표:
    def test_세_열이고_빠진_k_는_0_으로_적고_말한다(self) -> None:
        made = export.render("nk_table", deck(PMMA), MM_N_TONNE)
        got = [line.split("\t") for line in made.text.splitlines()]
        assert got[0] == ["0.4358", str(ROWS[0]["refractive_index"]), "0"]
        assert got[3][2] == "1e-08"
        assert len(got) == len(ROWS)
        assert made.notes == (
            "소광계수가 없는 파장 7개는 k = 0(흡수 없음)으로 적었습니다 — 이 표는 세 열을 "
            "요구합니다.",
        )
