"""ECAE 형식 — AEDT(.amat) · CST(.mtd) · Flotherm(FloXML) · ANSYS 전기(2026-10-02, ADR 0052).

여기서 무는 것은 **읽히기는 하는데 값이 다른** 종류다:

    단위    형식이 SI 를 정해 두었는데 mm·N·tonne 숫자가 들어간다(밀도 10¹² 배)
    표      주파수 표가 값 하나로 줄거나, 겹친 주파수가 솔버의 구간 선형 표를 깬다
    옮김    σ = 1/ρ 를 말없이 하거나, 형식 고유 단위(CST GPa · 1e-6/K · FloXML °C)를 빠뜨린다
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pytest

from matcore import cards, export
from matcore.export import ansys, electronics  # noqa: F401  (렌더러 등록)
from matcore.export.systems import MM_N_TONNE, SI

cards.load_builtin()

#: FR-4 계열 적층재 — 데이터시트처럼 1 MHz · 1 GHz · 10 GHz 의 Dk/Df.
LAMINATE: dict[str, Any] = {
    "electrical": {
        "values": {
            "relative_permittivity": 4.2,
            "relative_permittivity_frequency_hz": 1.0e6,
            "loss_tangent": 0.015,
            "loss_tangent_frequency_hz": 1.0e6,
            "resistivity": 1.0e14,
        },
        "rows": [
            {"frequency": 1.0e6, "relative_permittivity": 4.2, "loss_tangent": 0.015},
            {"frequency": 1.0e9, "relative_permittivity": 4.0, "loss_tangent": 0.018},
            {"frequency": 1.0e10, "relative_permittivity": 3.9, "loss_tangent": 0.02},
        ],
    },
    "thermal": {
        "values": {
            "thermal_conductivity": 0.3,
            "specific_heat": 1100.0,
            "thermal_expansion": 1.4e-5,
        }
    },
    "elastic": {
        "values": {"density": 1850.0, "youngs_modulus": 2.2e10, "poisson_ratio": 0.15}
    },
}

COPPER: dict[str, Any] = {
    "electrical": {
        "values": {
            "conductivity": 5.96e7,
            "conductivity_temperature_k": 293.15,
            "resistivity_temperature_coefficient": 0.00393,
        }
    },
    "thermal": {
        "values": {"thermal_conductivity": 401.0, "specific_heat": 385.0},
        "rows": [
            {"temperature": 293.15, "thermal_conductivity": 401.0},
            {"temperature": 373.15, "thermal_conductivity": 395.0},
        ],
    },
    "elastic": {"values": {"density": 8960.0}},
    "optical": {"values": {"emissivity": 0.05}},
}


def deck(blocks: dict[str, Any]) -> export.Deck:
    return export.Deck(name="TU_862", solver_id=42, blocks=blocks, provenance=("재료 TU-862",))


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()]


class Test단위는_형식이_정한다:
    def test_mm_계를_골라도_SI_로_나간다(self) -> None:
        """**밀도가 1.85e-9 로 나가면** AEDT 는 그것을 kg/m³ 로 읽는다 — 진공보다 가벼운
        기판."""
        for key in ("aedt", "cst", "flotherm"):
            text = export.render(key, deck(LAMINATE), MM_N_TONNE).text
            assert "1850" in text, key
            assert "e-09" not in text, key

    def test_파일_이름의_계도_형식이_정한다(self) -> None:
        aedt = export.renderer("aedt")
        assert export.effective_system(aedt, MM_N_TONNE) is SI
        assert (
            export.effective_system(export.renderer("ansys_thermal"), MM_N_TONNE) is MM_N_TONNE
        )


class TestAEDT:
    def test_주파수_표는_pwl_데이터셋이다(self) -> None:
        text = export.render("aedt", deck(LAMINATE), MM_N_TONNE).text
        got = lines(text)
        assert "permittivity='pwl($MNX42_permittivity,Freq)'" in got
        assert "dielectric_loss_tangent='pwl($MNX42_dielectric_loss_tangent,Freq)'" in got
        # 데이터셋 X 는 Hz — `Freq` 가 Hz 다(HFSS 의 공개 프로젝트 파일).
        assert "DimUnits[2: 'Hz', '']" in got
        assert "X('1000000', '1000000000', '1e+10')" in got
        assert "Y('4.2', '4', '3.9')" in got
        assert got[0] == "$begin 'TU_862'" and got[-1] == "$end 'TU_862'"
        assert "set('Electromagnetic', 'Thermal', 'Structural')" in got

    def test_저항률만_있으면_전도율로_옮기고_말한다(self) -> None:
        made = export.render("aedt", deck(LAMINATE), SI)
        assert "conductivity='1e-14'" in lines(made.text)
        assert any("σ = 1/ρ" in note for note in made.notes)

    def test_값_하나면_어느_주파수의_값인지_말한다(self) -> None:
        single = {
            "electrical": {
                "values": {
                    "relative_permittivity": 3.48,
                    "relative_permittivity_frequency_hz": 1.0e10,
                }
            }
        }
        made = export.render("aedt", deck(single), SI)
        assert "permittivity='3.48'" in lines(made.text)
        assert "RefDatasets" not in made.text
        assert made.notes == (
            "비유전율은 1e+10 Hz 의 값 하나로 실었습니다 — AEDT 는 모든 주파수에서 이 값을 "
            "씁니다.",
        )

    def test_비투자율을_모르면_적지_않는다(self) -> None:
        """1 을 지어 넣으면 잰 값처럼 보인다 — 안 적으면 AEDT 의 기본값(1)이 쓰인다."""
        assert "permeability" not in export.render("aedt", deck(LAMINATE), SI).text

    def test_전자기_값이_없으면_거절한다(self) -> None:
        only_tcr = {"electrical": {"values": {"resistivity_temperature_coefficient": 0.004}}}
        with pytest.raises(export.ExportError, match="전자기 값이 카드에 없습니다"):
            export.render("aedt", deck(only_tcr), SI)

    def test_겹친_주파수는_거절한다(self) -> None:
        """구간 선형 표는 x 가 늘기만 해야 한다 — 겹치면 어느 값이 이기는지 솔버마다 다르다."""
        twice = {
            "electrical": {
                "values": {"relative_permittivity": 4.0},
                "rows": [
                    {"frequency": 1.0e9, "relative_permittivity": 4.0},
                    {"frequency": 1.0e9, "relative_permittivity": 4.1},
                ],
            }
        }
        with pytest.raises(export.ExportError, match="같은 주파수"):
            export.render("aedt", deck(twice), SI)


class TestCST:
    def test_분산_맞춤_점과_형식_고유_단위(self) -> None:
        made = export.render("cst", deck(LAMINATE), MM_N_TONNE)
        got = lines(made.text)
        assert '.MaterialUnit "Frequency", "Hz"' in got
        assert '.DispersiveFittingFormatEps "Real_Tand"' in got
        assert '.AddDispersionFittingValueEps "1000000000", "4", "0.018", "1.0"' in got
        assert '.UseGeneralDispersionEps "True"' in got
        # 분산을 넘기면 상수 손실(TanD)은 안 적는다 — 둘이 다른 말을 하면 안 된다.
        assert not any(line.startswith(".TanD ") for line in got)
        # CST 의 영률은 kN/mm²(= GPa), 열팽창은 1e-6/K 로 적힌다(금 재료 파일 78 · 14).
        assert '.YoungsModulus "22"' in got
        assert '.ThermalExpansionRate "14"' in got
        assert '.Rho "1850"' in got
        assert got[-2:] == ["MatNexus 물성 카드", "재료 TU-862"]

    def test_표가_없으면_상수_손실과_그_주파수(self) -> None:
        single = {
            "electrical": {
                "values": {
                    "relative_permittivity": 3.48,
                    "loss_tangent": 0.0037,
                    "loss_tangent_frequency_hz": 1.0e10,
                }
            }
        }
        got = lines(export.render("cst", deck(single), SI).text)
        assert '.TanD "0.0037"' in got and '.TanDFreq "1e+10"' in got
        assert '.TanDGiven "True"' in got


class TestFlotherm:
    def test_온도_표는_싣지_않고_값_하나를_적고_말한다(self) -> None:
        """FloXML 곡선의 온도 단위를 공개 자료로 확인하지 못했다 — 열전도 온도 의존(`tref`)은
        켈빈인데(벤더 매크로가 °C + 273.15) 제어 곡선은 °C 로 보인다. 틀리면 곡선이 273 K
        밀린다. 처음에는 °C 로 적었다(2026-10-03 대조로 걷었다)."""
        made = export.render("flotherm", deck(COPPER), MM_N_TONNE)
        material = ET.fromstring(made.text).find("attributes/materials/isotropic_material_att")
        assert material is not None
        assert material.findtext("input_method") == "single_value"
        assert material.findtext("conductivity") == "401"
        assert material.find("conductivity_curve") is None
        assert material.findtext("density") == "8960"
        assert any("온도 표는 싣지 않았습니다" in note for note in made.notes)

    def test_저항률은_상수이고_TCR_은_싣지_않는다고_말한다(self) -> None:
        """저항률 계수가 상대값(1/K)인지 절대값(Ω·m/K)인지 모른다 — 구리에 상대값 0.00393 을
        절대값으로 읽히면 저항률이 10⁸ 배가 된다. 모르면 쓰지 않는다."""
        made = export.render("flotherm", deck(COPPER), SI)
        resistivity = ET.fromstring(made.text).find(
            "attributes/materials/isotropic_material_att/electrical_resistivity"
        )
        assert resistivity is not None
        assert resistivity.findtext("type") == "constant"
        assert resistivity.find("coeff") is None and resistivity.find("t_ref") is None
        assert float(resistivity.findtext("resistivity_value") or 0) == pytest.approx(
            1 / 5.96e7
        )
        assert any("ρ = 1/σ" in note for note in made.notes)
        assert any("저항온도계수는 싣지 않았습니다" in note for note in made.notes)

    def test_방사율은_표면으로_달린다(self) -> None:
        root = ET.fromstring(export.render("flotherm", deck(COPPER), SI).text)
        assert root.findtext("attributes/materials/isotropic_material_att/surface") == (
            "TU_862_surface"
        )
        assert root.findtext("attributes/surfaces/surface_att/emissivity") == "0.05"
        assert root.find("geometry") is not None

    def test_방사율이_0_1_밖이면_거절한다(self) -> None:
        """85 는 % 로 적은 것이다 — 그대로 내면 Flotherm 이 스키마로 거절하거나 85 로
        읽는다."""
        wrong = {**COPPER, "optical": {"values": {"emissivity": 85.0}}}
        with pytest.raises(export.ExportError, match="0~1"):
            export.render("flotherm", deck(wrong), SI)


class TestANSYS전기:
    def test_저항률은_SI_고정이고_전도율에서_옮긴다(self) -> None:
        made = export.render("ansys_electric", deck(COPPER), MM_N_TONNE)
        got = lines(made.text)
        assert "! Consistent units: kg, m, s, Pa" in got
        rsvx = next(line for line in got if line.startswith("MP,RSVX,MNX_MAT,"))
        assert float(rsvx.rsplit(",", 1)[1]) == pytest.approx(1 / 5.96e7)
        assert "MP,EMIS,MNX_MAT,5.000000000000E-02" in got
        assert any("저항온도계수는 싣지 않았습니다" in note for note in made.notes)


def test_블록만_요구하는_형식은_그_블록_이름을_요구한다() -> None:
    """값도 표도 안 적은 요구가 빈 목록이 되면 화면이 「 가 있어야 냅니다」 로 앞이 빈 말을
    한다 — 실서버 점검에서 AEDT · CST · ANSYS(전기)의 `requires` 가 비어 있었다(2026-10-02)."""
    for key in ("aedt", "cst", "ansys_electric"):
        assert export.requires_labels(key) == ("전기 · 전자기 물성",), key
