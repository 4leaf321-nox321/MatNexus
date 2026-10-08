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
from matcore.export.systems import MM_N_TONNE, SI

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


def large_card(text: str, keyword: str) -> list[list[str]]:
    """큰칸 카드의 논리 줄 — 물리 줄 둘(앞 8칸 + 16칸 넷)을 이어 8칸씩."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{keyword}*"))
    body = [line for line in lines[start:] if not line.startswith("$")]
    fields: list[str] = []
    for line in body:
        if not line.startswith((f"{keyword}*", "*")):
            break
        fields.extend(cols(line.ljust(72), 8, 16, 16, 16, 16)[1:])
    return [fields[at : at + 8] for at in range(0, len(fields), 8)]


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
        # `EXTRAPOLATION=` 은 Abaqus 2022 의 인자 — 그 전 판이 못 읽는다(2026-10-08 뺐다).
        assert lines[potential - 6] == "*PLASTIC, HARDENING=ISOTROPIC"
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
            "optistruct_hill",
        ):
            assert export.missing_for(alone, key), key

    def test_OptiStruct_PLASTIC_은_항복응력비와_응력이_먼저인_경화_표(self) -> None:
        """PLASTIC(2026) — 비 행은 `R11 R22 R33 R12 R31 R23 TEMP`, 경화 행은 `YIELD PLAS`
        (TABLES1 과 반대 차례). 응력과 변형률을 바꿔 적으면 덱은 돌고 재료가 다르다."""
        text = mm("optistruct_hill", elastic=STEEL, table=TABLE, anisotropy=ANISOTROPY)
        card = large_card(text, "PLASTIC")
        assert card[0][0] == "7"
        assert card[1][:2] == ["CRIT", "HILL"]
        ratios = hill_ratios(1.8, 1.4, 2.1)
        got = [float(one) for one in card[2][:7]]
        assert got[:4] == pytest.approx([1.0, ratios["R22"], ratios["R33"], ratios["R12"]])
        assert got[4:6] == [1.0, 1.0]  # R31 · R23 — 관례값
        assert got[6] > 0  # TEMP — 매뉴얼: 기본 없음, 0 보다 큼
        assert card[3][:2] == ["HARD", "ISOT"]
        hard = [(float(row[0]), float(row[1])) for row in card[4:]]
        assert hard == pytest.approx([(y / 1e6, x) for x, y in CURVE])  # (응력 MPa, 변형률)
        assert card[4][2] != "" and all(row[2] == "" for row in card[5:])  # TEMP 는 첫 줄만


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

    @pytest.mark.parametrize("key", ["optistruct_temperature", "nastran_temperature"])
    def test_표_번호는_재료_번호가_커도_8자리_안이고_겹치지_않는다(self, key: str) -> None:
        """Nastran 의 번호는 1억 미만이다. 전에는 온도별 표가 `재료 번호 * 100 + 10 + i` 라
        재료 번호(최대 7자리)가 크면 9자리가 됐다(2026-10-04 점검)."""
        deck = export.Deck(name="X", solver_id=9_999_999, blocks=self.BLOCKS)
        text = export.render(key, deck, MM_N_TONNE).text
        ids = []
        for line in text.splitlines():
            for name in ("TABLEST", "TABLES1", "TABLEM1"):
                if line.startswith(f"{name}*"):
                    ids.append(int(cols(line, 8, 16)[1]))
        assert ids and all(one < 100_000_000 for one in ids), ids
        assert len(ids) == len(set(ids)), ids

    def test_온도가_일곱이면_표_번호_자리가_모자라_말한다(self) -> None:
        rows = [
            {"temperature": 293.15 + 50 * step, "plastic_strain": x, "true_stress": y}
            for step in range(7)
            for x, y in CURVE
        ]
        seven = {
            "values": {"temperature_count": 7, "reference_temperature": 293.15},
            "rows": rows,
        }
        for key in ("optistruct_temperature", "nastran_temperature"):
            with pytest.raises(export.ExportError, match="6개까지"):
                mm(key, **{**self.BLOCKS, "temperature_table": seven})
        assert "*MAT_" in mm("dyna_temperature", **{**self.BLOCKS, "temperature_table": seven})

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
        "values": {"family": "johnson_cook_static", "label": "Johnson-Cook (준정적 항)"},
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

    # ── OptiStruct MATFAT · MSC MATFTG (2026-10-08) ──────────────────────────────────
    # 둘 다 **응력 범위** 절편(1 회)을 받는다 — 진폭 A 를 그대로 적으면 같은 응력에서 수명이
    # 2^(1/b) 배(b=-0.1 이면 1/1024)로 줄어 덱이 멀쩡해 보인다.

    SN: ClassVar[dict[str, Any]] = {
        "values": {
            "basquin_a": 1000e6,
            "basquin_b": -0.1,
            "tensile_strength": 680e6,
            "yield_strength": 430e6,
        },
        "rows": [
            {"stress_amplitude": 400e6, "cycles_to_failure": 1.0e4, "stress_ratio": -1.0},
            {"stress_amplitude": 250e6, "cycles_to_failure": 2.0e6, "stress_ratio": -1.0},
        ],
    }

    def test_MATFAT_는_범위_절편_2A_와_단위_이름(self) -> None:
        card = large_card(mm("optistruct_fatigue", sn_curve=self.SN), "MATFAT")
        assert card[0][:3] == ["7", "MPA", "MM"]  # UNIT 를 비우면 MPa — SI 덱이 10⁶ 배
        assert card[1][:3] == ["STATIC", "4.30000000E+02", "6.80000000E+02"]  # YS · UTS
        sn, sri1, b1, nc1, b2 = card[2][:5]
        assert sn == "SN"
        assert float(sri1) == pytest.approx(2000.0)  # 2A, MPa
        assert float(b1) == float(b2) == pytest.approx(-0.1)  # 한 직선
        assert float(nc1) == pytest.approx(2.0e6)  # 시험이 끝난 수명
        assert card[2][5:7] == ["", ""]  # FL · SE — 피로 한도를 지어 넣지 않는다

    def test_MATFAT_는_SI_로_내면_PA_다(self) -> None:
        deck = export.Deck(name="DP600", solver_id=7, blocks={"sn_curve": self.SN})
        text = export.render("optistruct_fatigue", deck, SI).text
        card = large_card(text, "MATFAT")
        assert card[0][:3] == ["7", "PA", "M"]
        assert float(card[2][1]) == pytest.approx(2000e6)

    def test_MATFTG_는_범위_절편과_시험_R(self) -> None:
        card = large_card(mm("nastran_fatigue", sn_curve=self.SN), "MATFTG")
        assert card[0][0] == "7"
        static = card[1]
        assert static[:3] == ["STATIC", "4.30000000E+02", "6.80000000E+02"]
        assert float(static[5]) == pytest.approx(-1.0)  # RR — 7번 칸
        sn = card[2]
        assert sn[0] == "SN"
        assert float(sn[1]) == pytest.approx(2000.0)
        assert float(sn[2]) == float(sn[4]) == pytest.approx(-0.1)

    def test_MATFTG_는_MPa_가_아니면_DTI_UNITS_를_말한다(self) -> None:
        """모델 전체 설정이라 재료 조각에는 안 넣는다 — 대신 덱 주석과 알림."""
        deck = export.Deck(name="DP600", solver_id=7, blocks={"sn_curve": self.SN})
        got = export.render("nastran_fatigue", deck, SI)
        assert "DTI,UNITS,1,PA" in got.text
        assert not any(line.startswith("DTI") for line in got.text.splitlines())
        assert any("DTI,UNITS,1,PA" in one for one in got.notes)
        assert "DTI" not in "".join(
            line
            for line in mm("nastran_fatigue", sn_curve=self.SN).splitlines()
            if not line.startswith("$")
        )

    def test_MATFTG_범위_밖은_솔버_전에_막는다(self) -> None:
        """UTS 100~4000 MPa(금속 피로만) · b1 은 -1 ~ -0.02."""
        weak = {**self.SN, "values": {**self.SN["values"], "tensile_strength": 60e6}}
        with pytest.raises(export.ExportError, match="100~4000"):
            mm("nastran_fatigue", sn_curve=weak)
        steep = {**self.SN, "values": {**self.SN["values"], "basquin_b": -0.01}}
        with pytest.raises(export.ExportError, match="b1"):
            mm("nastran_fatigue", sn_curve=steep)
        # OptiStruct 는 범위를 적지 않는다 — 같은 카드를 낸다.
        assert "MATFAT*" in mm("optistruct_fatigue", sn_curve=weak)

    def test_인장강도가_없으면_목록에서_막힌다(self) -> None:
        bare = {"values": {"basquin_a": 1000e6, "basquin_b": -0.1}, "rows": []}
        deck = export.Deck(name="DP600", solver_id=7, blocks={"sn_curve": bare})
        formats = export.available_formats(deck)
        assert "dyna_fatigue" in formats
        assert "optistruct_fatigue" not in formats
        assert "nastran_fatigue" not in formats
