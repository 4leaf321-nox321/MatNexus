"""확장 블록의 솔버 덱 — Hill48 · 온도 의존 · Johnson-Cook · 피로 S-N (2026-09-27).

`tests/unit/test_export_solvers.py` 와 같은 태도다 — **덱은 돌고 재료가 다른** 자리를 문다.
Radioss 는 OpenRadioss 로 실제로 돌려 맞췄다(`scripts/check_openradioss.py`): LAW43 의
Iyield0, LAW109 의 Tref·온도 표, LAW2 의 칸이 거기서 확인됐다.
"""

from __future__ import annotations

import importlib
import math
import pathlib
from typing import Any, ClassVar

import pytest

from matcore import cards, export, extensions
from matcore.export import ansys, bulk, dyna, radioss  # noqa: F401  (렌더러 등록)
from matcore.export.systems import MM_N_TONNE

EXTENSIONS = pathlib.Path(__file__).resolve().parents[2] / "extensions"
extensions.load(EXTENSIONS)
cards.load_builtin()

# **로더가 쓰는 이름으로** 가져온다 — 폴더를 직접 import 하면 블록이 두 번 등록된다.
hill_ratios = importlib.import_module(f"{extensions.PACKAGE}.anisotropy.deck").hill_ratios

CURVE = [(0.0, 350e6), (0.02, 455e6), (0.1, 560e6), (0.4, 700e6), (1.0, 790e6)]
STEEL = {"values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}}
TABLE = {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE]}
ANISOTROPY = {"values": {"r_0": 1.8, "r_45": 1.4, "r_90": 2.1}}
TEMPERATURE = {
    "values": {"temperature_count": 2, "reference_temperature": 293.15},
    "rows": [
        *(
            {"temperature": 473.15, "plastic_strain": x, "true_stress": y * 0.86}
            for x, y in CURVE
        ),
        *({"temperature": 293.15, "plastic_strain": x, "true_stress": y} for x, y in CURVE),
    ],
}


def mm(key: str, **blocks: Any) -> str:
    deck = export.Deck(name="DP600", solver_id=7, blocks=blocks, provenance=("시험",))
    return export.render(key, deck, MM_N_TONNE).text


def cols(line: str, *widths: int) -> list[str]:
    out, start = [], 0
    for width in widths:
        out.append(line[start : start + width].strip())
        start += width
    return out


def after(lines: list[str], label: str) -> str:
    index = next(
        i
        for i, line in enumerate(lines)
        if line.startswith(("#", "$")) and line[1:].split()[:1] == [label] and "=" not in line
    )
    return next(line for line in lines[index + 1 :] if not line.startswith(("#", "$")))


class TestHill48:
    def test_항복응력비는_Lankford_식이다(self) -> None:
        """Abaqus 이방 항복 문서의 식 — 압연 방향이 R11 = 1."""
        ratios = hill_ratios(1.8, 1.4, 2.1)
        assert ratios["R11"] == 1.0
        assert ratios["R22"] == pytest.approx(math.sqrt(2.1 * 2.8 / (1.8 * 3.1)))
        assert ratios["R33"] == pytest.approx(math.sqrt(2.1 * 2.8 / 3.9))
        assert ratios["R12"] == pytest.approx(math.sqrt(3 * 2.1 * 2.8 / (3.8 * 3.9)))
        # 등방이면 전부 1 — 식이 뒤바뀌면 여기서 먼저 어긋난다.
        assert all(value == pytest.approx(1.0) for value in hill_ratios(1, 1, 1).values())

    def test_Abaqus_는_PLASTIC_바로_뒤에_POTENTIAL(self) -> None:
        lines = mm(
            "abaqus_hill", elastic=STEEL, table=TABLE, anisotropy=ANISOTROPY
        ).splitlines()
        potential = lines.index("*POTENTIAL")
        assert lines[potential - 6] == "*PLASTIC, HARDENING=ISOTROPIC, EXTRAPOLATION=CONSTANT"
        assert float(lines[potential + 1].split(",")[1]) == pytest.approx(
            hill_ratios(1.8, 1.4, 2.1)["R22"]
        )

    def test_ANSYS_는_TB_HILL(self) -> None:
        text = mm("ansys_hill", elastic=STEEL, table=TABLE, anisotropy=ANISOTROPY)
        assert "TB,HILL,MNX_MAT" in text and "TB,PLASTIC,MNX_MAT" in text

    def test_LS_DYNA_036_은_M2_와_r_셋(self) -> None:
        lines = mm("dyna_hill", elastic=STEEL, table=TABLE, anisotropy=ANISOTROPY).splitlines()
        card2 = after(lines, "m")
        assert [float(one) for one in cols(card2, 10, 10, 10, 10)] == [2.0, 1.8, 1.4, 2.1]
        assert cols(card2, 10, 10, 10, 10, 10)[4] == "7"  # LCID
        # 필수 카드 다섯 — 4a·5·6 이 0 으로 차 있다.
        assert after(lines, "aopt") == f"{0:>10}" * 8

    def test_Radioss_LAW43_은_Iyield0_1(self) -> None:
        """기본 0 은 곡선을 평균 항복응력으로 읽어 압연 방향 응력이 1.3% 높았다
        (OpenRadioss 로 돌려 확인)."""
        lines = mm(
            "openradioss_hill", elastic=STEEL, table=TABLE, anisotropy=ANISOTROPY
        ).splitlines()
        row = after(lines, "r00")
        assert cols(row, 20, 20, 20, 20, 10) == [
            "1.800000000E+00",
            "1.400000000E+00",
            "2.100000000E+00",
            "",
            "1",
        ]

    def test_MSC_MATEP_Aniso_줄(self) -> None:
        lines = mm(
            "nastran_hill", elastic=STEEL, table=TABLE, anisotropy=ANISOTROPY
        ).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("MATEP*"))
        first = cols(lines[start], 8, 16, 16, 16, 16)
        assert first[1:5] == ["7", "TABLE", "", "70"]
        assert cols(lines[start + 1], 8, 16)[1] == "HILL"
        aniso = cols(lines[start + 2], 8, 16, 16, 16, 16)
        assert aniso[1:4] == ["Aniso", "", "1.00000000E+00"]

    def test_짝_없이는_못_낸다(self) -> None:
        alone = export.Deck(name="X", solver_id=1, blocks={"anisotropy": ANISOTROPY})
        for key in (
            "abaqus_hill",
            "ansys_hill",
            "dyna_hill",
            "openradioss_hill",
            "nastran_hill",
        ):
            assert export.missing_for(alone, key), key


class Test온도_의존:
    BLOCKS: ClassVar[dict[str, Any]] = {
        "elastic": STEEL,
        "table": TABLE,
        "temperature_table": TEMPERATURE,
    }

    def test_ANSYS_TBTEMP_는_온도_오름차순(self) -> None:
        lines = mm("ansys_temperature", **self.BLOCKS).splitlines()
        temps = [float(line.split(",")[1]) for line in lines if line.startswith("TBTEMP")]
        assert temps == [293.15, 473.15]
        assert "TB,PLASTIC,MNX_MAT,2,5,MISO" in lines

    def test_LS_DYNA_255_표의_값은_온도다(self) -> None:
        lines = mm("dyna_temperature", **self.BLOCKS).splitlines()
        table = lines.index("*DEFINE_TABLE")
        assert lines[table + 4 : table + 6] == [f"{293.15:>20.12E}", f"{473.15:>20.12E}"]
        card2 = after(lines, "tabidc")
        assert cols(card2, 10, 10) == ["7", "7"]

    def test_LS_DYNA_는_온도별_탄성이_있으면_E_가_곡선(self) -> None:
        elastic = {
            **STEEL,
            "rows": [
                {"temperature": 293.15, "youngs_modulus": 210e9, "poisson_ratio": 0.3},
                {"temperature": 473.15, "youngs_modulus": 198e9, "poisson_ratio": 0.3},
            ],
        }
        lines = mm("dyna_temperature", **{**self.BLOCKS, "elastic": elastic}).splitlines()
        card1 = after(lines, "mid")
        assert float(cols(card1, 10, 10, 10)[2]) == -790.0  # |E| = 곡선 790

    def test_OptiStruct_는_TYPSTRN_1_과_TABLEST(self) -> None:
        lines = mm("optistruct_temperature", **self.BLOCKS).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("MATS1*"))
        assert cols(lines[start], 8, 16, 16, 16)[1:4] == ["7", "70", "PLASTIC"]
        # LIMIT1 은 비운다 — 온도마다 항복이 다르다.
        assert cols(lines[start + 1], 8, 16, 16, 16) == ["*", "1", "1", ""]
        assert cols(lines[start + 2], 8, 16) == ["*", "1"]  # TYPSTRN
        assert any(line.startswith("TABLEST*70") for line in lines)

    def test_MSC_는_MATEP_MATTEP_이고_MATS1_이_없다(self) -> None:
        text = mm("nastran_temperature", **self.BLOCKS)
        assert "MATS1*" not in text
        lines = text.splitlines()
        mattep = cols(
            next(line for line in lines if line.startswith("MATTEP*")), 8, 16, 16, 16, 16
        )
        assert mattep[1:5] == ["7", "", "", "70"]  # T(FID) = 5번 칸
        tables = [line for line in lines if line.startswith("TABLES1*")]
        assert all(cols(line, 8, 16, 16)[2] == "2" for line in tables)  # TYPE=2 소성변형률

    def test_Radioss_LAW109_Tref_와_온도_표(self) -> None:
        lines = mm("openradioss_temperature", **self.BLOCKS).splitlines()
        assert cols(after(lines, "Cp"), 20, 20, 20, 20)[2] == "2.931500000E+02"
        index = lines.index("/TABLE/1/702")
        assert lines[index + 3] == f"{2:>10}"
        rows = [line for line in lines[index + 5 : index + 7]]
        assert [cols(row, 10, 10, 20)[::2] for row in rows] == [
            ["710", "2.931500000E+02"],
            ["711", "4.731500000E+02"],
        ]


class TestJohnson_Cook:
    HARDENING: ClassVar[dict[str, Any]] = {
        "values": {"label": "JC"},
        "rows": [
            {"name": "a", "value": 350e6, "si_unit": "Pa"},
            {"name": "b", "value": 600e6, "si_unit": "Pa"},
            {"name": "n", "value": 0.4, "si_unit": "1"},
        ],
    }

    def test_LAW2_칸(self) -> None:
        lines = mm(
            "openradioss_johnson_cook", elastic=STEEL, table=TABLE, hardening=self.HARDENING
        ).splitlines()
        assert cols(after(lines, "E"), 20, 20, 10, 10) == [
            "2.100000000E+05",
            "3.000000000E-01",
            "0",
            "1",
        ]
        assert cols(after(lines, "a"), 20, 20, 20) == [
            "3.500000000E+02",
            "6.000000000E+02",
            "4.000000000E-01",
        ]
        # 온도항 줄은 비운다 — T_melt 가 비면 1e20 이 되어 T* 가 0 에 머문다.
        assert after(lines, "m") == ""


class Test피로:
    def test_MAT_ADD_FATIGUE_는_식과_진폭(self) -> None:
        sn = {"values": {"basquin_a": 1000e6, "basquin_b": -0.1}, "rows": []}
        lines = mm("dyna_fatigue", sn_curve=sn).splitlines()
        row = after(lines, "mid")
        got = cols(row, 10, 10, 10, 10, 10, 10, 10, 10)
        assert got[:3] == ["7", "-3", "0"]
        assert float(got[3]) == pytest.approx(1000.0)  # MPa
        assert float(got[4]) == pytest.approx(-0.1)
        assert got[7] == "1"  # SNTYPE — 기본은 범위(0)라 늘 적는다
