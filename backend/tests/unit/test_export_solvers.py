"""솔버 · 물성 모델 — ANSYS · Nastran · OptiStruct · Radioss 렌더러(2026-09-27).

**여기서 무는 것은 전부 「덱은 돌고 재료가 다른」 종류다.** 솔버는 칸이 밀리거나 규약이
바뀐 값을 오류로 알려 주지 않는다:

    칸       고정폭 필드가 한 칸 밀리면 다른 값이 된다(Radioss VP · fct_IDp, 큰칸 벌크)
    규약     같은 기호가 솔버마다 다르다(Ogden μ · Perzyna m · MATHP D1 · MAT1 순간/장기)
    변환     소성 → 전체 변형률, 절대 Gᵢ ↔ 비율 gᵢ, MATT4 는 곱한다
    단위     mm·N·tonne 로 내면 숫자가 그 계여야 한다

칸 폭은 각 솔버의 매뉴얼·파서 형식으로 대조했다 — Radioss 는 OpenRadioss 의 CFG 형식
문자열, LS-DYNA 는 R13·R17 매뉴얼, Nastran 은 MSC QRG 2025.1, OptiStruct 는 Altair
Reference Guide, ANSYS 는 2024 R2 도움말.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

# 모듈을 읽으면 렌더러가 등록된다.
import matcore.export.ansys
import matcore.export.bulk
import matcore.export.dyna
import matcore.export.radioss  # noqa: F401
from matcore import cards, export
from matcore.export import Deck, ExportError, render
from matcore.export.systems import MM_N_TONNE

cards.load_builtin()

STEEL = {"values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}}
CURVE = [(0.0, 350e6), (0.02, 455e6), (0.1, 560e6), (0.4, 700e6), (1.0, 790e6)]
TABLE = {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE]}
RUBBER = {"values": {"poisson_ratio": 0.4995, "density": 1100.0}}
POLYMER = {"values": {"youngs_modulus": 2.8e9, "poisson_ratio": 0.4, "density": 1200.0}}
PRONY = {
    "values": {"reference_temperature_k": 296.15},
    "rows": [
        {"relative_modulus": 0.3, "relaxation_time_s": 0.01},
        {"relative_modulus": 0.25, "relaxation_time_s": 0.1},
    ],
}


def rates(*speeds: float, factor: float = 1.1) -> dict[str, Any]:
    rows: list[dict[str, float]] = []
    for index, rate in enumerate(speeds):
        rows.extend(
            {"strain_rate": rate, "plastic_strain": x, "true_stress": y * factor**index}
            for x, y in CURVE
        )
    return {
        "values": {
            "rate_count": len(speeds),
            "reference_rate": speeds[0],
            "model": "cowper_symonds",
            "cs_d": 1.0e7,
            "cs_p": 5.0,
        },
        "rows": rows,
    }


def hyper(family: str, **params: float) -> dict[str, Any]:
    return {
        "values": {"family": family},
        "rows": [
            {"name": key, "value": value, "si_unit": "1" if key == "alpha" else "Pa"}
            for key, value in params.items()
        ],
    }


def deck(**blocks: Any) -> Deck:
    return Deck(name="DP600_MD", solver_id=101, blocks=blocks, provenance=("시험 3건",))


def mm(key: str, **blocks: Any) -> str:
    """mm·N·tonne 로 낸 덱 — 예제 덱(`시뮬레이션 인풋 덱/예제`)과 같은 계다."""
    return render(key, deck(**blocks), MM_N_TONNE).text


def cols(line: str, *widths: int) -> list[str]:
    """고정폭 줄을 칸으로 자른다 — 솔버가 읽는 방식 그대로."""
    out, start = [], 0
    for width in widths:
        out.append(line[start : start + width].strip())
        start += width
    return out


def label_at(lines: list[str], label: str) -> int:
    """칸 이름 주석 줄(`#   E   nu …`)의 자리 — 첫 칸 이름으로 찾는다. 설명 주석
    (`# mu_1 = 2*C10`)은 건너뛴다."""
    return next(
        index
        for index, line in enumerate(lines)
        if line.startswith("#") and line[1:].split()[:1] == [label] and "=" not in line
    )


def after(lines: list[str], label: str) -> str:
    """칸 이름 주석 `label` 다음의 첫 값 줄."""
    return next(
        line for line in lines[label_at(lines, label) + 1 :] if not line.startswith("#")
    )


class Test모델이_솔버마다_있다:
    """사용자가 요청한 표 — **솔버마다 물성 모델별로 따로 낸다.** 빠진 칸은 이유가 있다."""

    EXPECTED: ClassVar[dict[str, tuple[str, ...]]] = {
        "ansys": ("elastic", "plastic", "rate", "viscoelastic", "hyperelastic", "thermal"),
        "dyna": ("elastic", "", "rate", "viscoelastic", "hyperelastic", "thermal"),
        # Nastran 은 속도 의존이 없다 — SOL 400 MATEP 의 TABL3D 는 칸은 매뉴얼에 있으나 속도
        # 사이 보간과 「등가 변형률 속도」 가 전체인지 소성인지 적혀 있지 않다(2026-10-08).
        "nastran": ("elastic", "plastic", "viscoelastic", "hyperelastic", "thermal"),
        "optistruct": (
            "elastic",
            "plastic",
            "rate",
            "viscoelastic",
            "hyperelastic",
            "thermal",
        ),
        "openradioss": ("elastic", "", "rate", "viscoelastic", "hyperelastic", "thermal"),
    }

    def test_표가_다_찼다(self) -> None:
        keys = {item.key for item in export.list_renderers()}
        for solver, models in self.EXPECTED.items():
            for model in models:
                key = f"{solver}_{model}" if model else solver
                assert key in keys, key

    def test_이름이_솔버_모델_꼴이다(self) -> None:
        """「ANSYS (선형)」 처럼 — 메뉴가 괄호 앞으로 솔버를 묶는다."""
        for item in export.list_renderers():
            if item.key == "json":
                continue
            assert item.label.endswith(")") and " (" in item.label, item.label


class TestANSYS:
    def test_소성_표는_소성변형률_응력_차례다(self) -> None:
        text = mm("ansys_plastic", elastic=STEEL, table=TABLE)
        lines = text.splitlines()
        assert "MNX_MAT = 101" in lines
        assert "MP,EX,MNX_MAT,2.100000000000E+05" in lines  # MPa
        assert "MP,DENS,MNX_MAT,7.850000000000E-09" in lines  # tonne/mm3
        assert "TB,PLASTIC,MNX_MAT,1,5,MISO" in lines
        assert "TBPT,DEFI,2.000000000000E-02,4.550000000000E+02" in lines

    def test_온도표는_한_명령에_값_하나다(self) -> None:
        """MPTEMP·MPDATA 는 **둘째 칸부터의 0 을 무시한다** — 한 명령에 여럿을 적으면 0 인
        값이 이전 값으로 남는다. 하나씩 적고, 먼저 지운다."""
        elastic = {
            **STEEL,
            "rows": [
                {"temperature": 473.15, "youngs_modulus": 198e9, "poisson_ratio": 0.3},
                {"temperature": 293.15, "youngs_modulus": 210e9, "poisson_ratio": 0.3},
            ],
        }
        lines = mm("ansys_elastic", elastic=elastic).splitlines()
        assert "MPDELE,EX,MNX_MAT" in lines
        # 온도 순으로 — 카드 행 차례가 뒤바뀌어 있어도.
        assert lines.index("MPTEMP,1,2.931500000000E+02") < lines.index(
            "MPTEMP,2,4.731500000000E+02"
        )
        assert "MPDATA,EX,MNX_MAT,2,1.980000000000E+05" in lines
        assert not any(line.count(",") > 4 for line in lines if line.startswith("MPDATA"))

    def test_Perzyna_는_m_이_먼저다(self) -> None:
        """**m 과 1/m 을 뒤바꾸면** 10% 인 속도 효과가 엄청나게 커진다. m = 1/p, gamma = D."""
        text = mm("ansys_rate", elastic=STEEL, table=TABLE, rate_table=rates(0.001, 100.0))
        assert "TB,RATE,MNX_MAT,,,PERZYNA" in text
        assert "TBDATA,1,2.000000000000E-01,1.000000000000E+07" in text

    def test_Perzyna_는_p_가_1_이상이어야_한다(self) -> None:
        table = rates(0.001, 100.0)
        table["values"]["cs_p"] = 0.5
        with pytest.raises(ExportError, match="p ≥ 1"):
            mm("ansys_rate", elastic=STEEL, table=TABLE, rate_table=table)

    def test_Prony_는_여섯_값씩_자리를_적어_잇는다(self) -> None:
        rows = [{"relative_modulus": 0.1, "relaxation_time_s": float(10**n)} for n in range(4)]
        lines = mm(
            "ansys_viscoelastic", elastic=POLYMER, viscoelastic={"rows": rows}
        ).splitlines()
        assert "TB,PRONY,MNX_MAT,1,4,SHEAR" in lines
        data = [line for line in lines if line.startswith("TBDATA")]
        assert [line.split(",")[1] for line in data] == ["1", "7"]
        # EX 는 순간 탄성률 그대로다 — ANSYS 는 늘 그렇게 읽는다.
        assert "MP,EX,MNX_MAT,2.800000000000E+03" in lines

    def test_초탄성_규약을_옮긴다(self) -> None:
        """NEO 의 μ 는 2·C10, Ogden 의 μ 는 2μ/α(ANSYS 는 G = Σμα/2)."""
        neo = mm(
            "ansys_hyperelastic", elastic=RUBBER, hyperelastic=hyper("neo_hookean", c10=0.6e6)
        )
        assert "TBDATA,1,1.200000000000E+00," in neo
        ogden = mm(
            "ansys_hyperelastic",
            elastic=RUBBER,
            hyperelastic=hyper("ogden_1", mu=1.5e6, alpha=3.0),
        )
        assert "TB,HYPER,MNX_MAT,1,1,OGDEN" in ogden
        assert "TBDATA,1,1.000000000000E+00,3.000000000000E+00," in ogden

    def test_열팽창은_ALPX_고_기준온도를_지어내지_않는다(self) -> None:
        """ALPX 는 할선 계수(카드의 값과 같은 뜻), CTEX 는 순간 계수다."""
        thermal = {"values": {"thermal_expansion": 1.2e-5, "thermal_conductivity": 45.0}}
        text = mm("ansys_elastic", elastic=STEEL, thermal=thermal)
        assert "MP,ALPX,MNX_MAT,1.200000000000E-05" in text
        assert "CTEX" not in text
        assert "MP,REFT" not in text
        with_zero = {"values": {**thermal["values"], "thermal_expansion_temperature": 293.15}}
        assert "MP,REFT,MNX_MAT,2.931500000000E+02" in mm(
            "ansys_elastic", elastic=STEEL, thermal=with_zero
        )


def large(line: str) -> list[str]:
    """큰칸 벌크 한 줄 — 앞 8칸 + 16칸 넷."""
    return cols(line, 8, 16, 16, 16, 16)


class TestNastran계열:
    @pytest.mark.parametrize("solver", ["nastran", "optistruct"])
    def test_큰칸이고_잇는_줄은_별로_시작한다(self, solver: str) -> None:
        lines = [
            line
            for line in mm(f"{solver}_plastic", elastic=STEEL, table=TABLE).splitlines()
            if not line.startswith("$")
        ]
        assert all(len(line) <= 72 for line in lines)
        assert lines[0].startswith("MAT1*")
        assert all(line.startswith(("MAT1*", "MATS1*", "TABLES1*", "*")) for line in lines)

    @pytest.mark.parametrize("solver", ["nastran", "optistruct"])
    def test_TABLES1_은_전체_변형률이고_둘째_점이_항복점이다(self, solver: str) -> None:
        """소성 → 전체: ε = εₚ + σ/E, 원점을 앞에. 둘째 점이 MAT1 의 탄성 기울기 위에 서야
        초기 강성이 두 번 정의되지 않는다(예제 덱의 0.0016667)."""
        lines = mm(f"{solver}_plastic", elastic=STEEL, table=TABLE).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("TABLES1*"))
        values = [
            float(one)
            for line in lines[start + 2 :]
            for one in large(line)[1:]
            if one and one != "ENDT"
        ]
        pairs = list(zip(values[::2], values[1::2], strict=True))
        assert pairs[0] == (0.0, 0.0)
        assert pairs[1] == pytest.approx((350.0 / 210000.0, 350.0))
        assert pairs[2] == pytest.approx((0.02 + 455.0 / 210000.0, 455.0))
        mats1 = [line for line in lines if line.startswith(("MATS1*",))]
        assert large(mats1[0])[1:4] == ["101", "1010", "PLASTIC"]

    def test_OptiStruct_속도_의존은_TABLEMD_에_응력_변형률_속도_차례다(self) -> None:
        """TABLEMD 는 점마다 잇는 줄 하나 — Y(응력) · X1(소성변형률) · X2(속도). 칸 하나를
        밀면 변형률이 속도로 읽히고 경고가 안 난다. 차례는 X2 오름차순, 그 안에서 X1."""
        lines = mm("optistruct_rate", elastic=STEEL, rate_table=rates(0.001, 1.0, 100.0))
        lines_ = lines.splitlines()
        start = next(i for i, line in enumerate(lines_) if line.startswith("TABLEMD*"))
        assert large(lines_[start])[1:5] == ["1010", "", "2", "1"]  # TID · 빈칸 · NDEP · FLAT
        points = [
            tuple(float(one) for one in large(line)[1:4])
            for line in lines_[start + 2 :: 2]
            if line.startswith("*") and large(line)[1]
        ]
        # 가장 느린 곡선이 속도 0 에도 — 암시적 해석은 속도 0 곡선을 요구한다.
        assert [rate for _, _, rate in points] == [0.0] * 5 + [0.001] * 5 + [1.0] * 5 + [
            100.0
        ] * 5
        assert points[0] == pytest.approx((350.0, 0.0, 0.0))
        assert points[5] == pytest.approx((350.0, 0.0, 0.001))
        assert points[11] == pytest.approx((455.0 * 1.1, 0.02, 1.0))
        assert points[-1] == pytest.approx((790.0 * 1.1**2, 1.0, 100.0))

    def test_OptiStruct_속도_의존의_MATS1_은_소성변형률과_소성변형률_속도다(self) -> None:
        """TYPSTRN=1(표가 소성변형률) · TYPSTRT=1(소성변형률 속도)은 잇는 줄 2 · 3번 칸.
        TYPSTRN 을 비우면 0(전체 변형률)인데 TABLEMD 와 함께면 무시된다고 매뉴얼이 적는다
        — 그 빈칸이 나중에 다른 뜻으로 읽히지 않게 적어 둔다. LIMIT1 은 비운다."""
        lines = mm(
            "optistruct_rate", elastic=STEEL, rate_table=rates(0.001, 100.0)
        ).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("MATS1*"))
        assert large(lines[start])[1:5] == ["101", "1010", "PLASTIC", ""]
        assert large(lines[start + 1])[1:4] == ["1", "1", ""]  # YF · HR · LIMIT1
        assert large(lines[start + 2])[1:3] == ["1", "1"]  # TYPSTRN · TYPSTRT
        assert "TABLES1" not in "\n".join(lines)

    def test_OptiStruct_속도_의존은_속도_0_이_있으면_겹쳐_적지_않고_음수는_거절한다(
        self,
    ) -> None:
        text = mm("optistruct_rate", elastic=STEEL, rate_table=rates(0.0, 100.0))
        zeros = [
            line
            for line in text.splitlines()
            if line.startswith("*") and large(line)[3:4] == ["0.00000000E+00"]
        ]
        assert len(zeros) == 5
        with pytest.raises(ExportError, match="음수"):
            mm("optistruct_rate", elastic=STEEL, rate_table=rates(-1.0, 100.0))

    def test_MATT1_의_자리는_E_3_NU_5_다(self) -> None:
        """하나 밀면 G 의 표가 NU 로 들어가 포아송비가 20만이 되는데 경고가 안 난다."""
        elastic = {
            **STEEL,
            "rows": [
                {"temperature": 293.15, "youngs_modulus": 210e9, "poisson_ratio": 0.3},
                {"temperature": 473.15, "youngs_modulus": 198e9, "poisson_ratio": 0.3},
            ],
        }
        lines = mm("nastran_elastic", elastic=elastic).splitlines()
        matt1 = large(next(line for line in lines if line.startswith("MATT1*")))
        assert matt1[1:5] == ["101", "1011", "", "1012"]

    def test_MATT4_는_곱하므로_비율을_싣는다(self) -> None:
        """절대값을 넣으면 K * K(T) 가 된다 — 덱만 봐서는 티가 안 난다."""
        thermal = {
            "values": {"thermal_conductivity": 50.0},
            "rows": [
                {"temperature": 293.15, "thermal_conductivity": 50.0},
                {"temperature": 473.15, "thermal_conductivity": 40.0},
            ],
        }
        lines = mm("optistruct_thermal", elastic=STEEL, thermal=thermal).splitlines()
        assert large(lines[lines.index(next(x for x in lines if x.startswith("MAT4*")))])[
            2
        ] == ("5.00000000E+01")
        table = next(i for i, line in enumerate(lines) if line.startswith("TABLEM1*"))
        assert large(lines[table + 2])[1:5] == [
            "2.93150000E+02",
            "1.00000000E+00",
            "4.73150000E+02",
            "8.00000000E-01",
        ]

    def test_MAT4_는_밀도_없이는_목록에서_막힌다(self) -> None:
        """MSC 는 RHO 를 비우면 1.0 으로 본다 — 열용량이 조용히 틀린다. **메뉴에서 미리**
        막는다: 렌더러 안에서 거절하면 「가능」 을 보고 눌렀다가 422 를 본다."""
        thermal = {"values": {"thermal_conductivity": 45.0, "specific_heat": 460.0}}
        for solver in ("nastran", "optistruct"):
            assert f"{solver}_thermal" not in export.available_formats(deck(thermal=thermal))
            assert f"{solver}_thermal" in export.available_formats(
                deck(thermal=thermal, elastic=STEEL)
            )

    def test_점탄성_MAT1_은_MSC_순간_OptiStruct_장기다(self) -> None:
        """같은 카드인데 **짝 MAT1 을 반대로 읽는다.** MSC 는 순간 E₀ 그대로, OptiStruct 는
        장기 G∞ 와 — 체적이 순간 K₀ 로 남도록 맞춘 — E′."""
        msc = mm("nastran_viscoelastic", elastic=POLYMER, viscoelastic=PRONY).splitlines()
        mat1 = large(next(line for line in msc if line.startswith("MAT1*")))
        assert float(mat1[2]) == pytest.approx(2800.0)
        assert "ISO1" in large(next(line for line in msc if line.startswith("MATVE*")))
        # Gᵢ 는 절대값: g·G₀ = 0.3 * 1000
        assert any(large(line)[1] == "3.00000000E+02" for line in msc if line.startswith("*"))

        os = mm("optistruct_viscoelastic", elastic=POLYMER, viscoelastic=PRONY).splitlines()
        mat1 = large(next(line for line in os if line.startswith("MAT1*")))
        youngs, shear = float(mat1[2]), float(mat1[3])
        assert shear == pytest.approx(0.45 * 1000.0)  # G∞ = (1 - 0.55)·G₀
        bulk = youngs * shear / (3.0 * (3.0 * shear - youngs))
        assert bulk == pytest.approx(2800.0 / (3.0 * (1.0 - 0.8)), rel=1e-6)  # K₀
        # gᵢ 는 비율 그대로 — 첫 줄 뒤쪽 반에 gD1·tD1.
        matve = next(i for i, line in enumerate(os) if line.startswith("MATVE*"))
        assert large(os[matve + 1])[1:3] == ["3.00000000E-01", "1.00000000E-02"]

    def test_OptiStruct_는_다섯_항을_넘으면_UPRN_이다(self) -> None:
        rows = [
            {"relative_modulus": 0.05, "relaxation_time_s": float(10**n)} for n in range(6)
        ]
        text = mm("optistruct_viscoelastic", elastic=POLYMER, viscoelastic={"rows": rows})
        assert "UPRN" in text and "PRONY  " not in text

    def test_MATHP_Yeoh_는_NA_3_을_셋째_칸에(self) -> None:
        lines = mm(
            "nastran_hyperelastic",
            elastic=RUBBER,
            hyperelastic=hyper("yeoh", c10=0.5e6, c20=-0.01e6, c30=0.001e6),
        ).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("MATHP*"))
        assert large(lines[start + 2])[1:4] == ["", "3", "1"]
        assert large(lines[start + 4])[1] == "-1.00000000E-02"  # A20, 3번 줄
        assert large(lines[start + 6])[1] == "1.00000000E-03"  # A30, 4번 줄

    def test_MATHP_의_D1_은_K_의_절반이다(self) -> None:
        """Abaqus·ANSYS 의 D1 = 2/K 와 **같은 기호, 역수**다."""
        lines = mm(
            "nastran_hyperelastic",
            elastic=RUBBER,
            hyperelastic=hyper("mooney_rivlin", c10=0.6e6, c01=0.15e6),
        ).splitlines()
        mathp = large(next(line for line in lines if line.startswith("MATHP*")))
        shear = 2.0 * (0.6 + 0.15)
        bulk = 2.0 * shear * 1.4995 / (3.0 * (1.0 - 2.0 * 0.4995))
        assert float(mathp[4]) == pytest.approx(bulk / 2.0)

    def test_Ogden_은_OptiStruct_가_그대로_받고_MSC_는_거부한다(self) -> None:
        """OptiStruct MATHE 의 Ogden 은 2μ/α² 규약(G = Σμ) — 카드의 μ 와 같다."""
        rubber = hyper("ogden_1", mu=1.5e6, alpha=3.0)
        lines = mm("optistruct_hyperelastic", elastic=RUBBER, hyperelastic=rubber).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("MATHE*"))
        assert large(lines[start])[2:4] == ["OGDEN", "1"]
        assert large(lines[start + 2])[1:3] == ["1.50000000E+00", "3.00000000E+00"]
        with pytest.raises(ExportError, match="Ogden"):
            mm("nastran_hyperelastic", elastic=RUBBER, hyperelastic=rubber)


def _bulk_from_deck(key: str, text: str) -> float:
    """덱이 말하는 초기 체적 탄성률 K — 솔버마다 칸과 뜻이 다르다."""
    lines = text.splitlines()
    if key == "abaqus_hyperelastic":
        at = next(i for i, line in enumerate(lines) if line.startswith("*HYPERELASTIC"))
        return 2.0 / float(lines[at + 1].split(",")[-1])  # D1 = 2/K
    if key == "ansys_hyperelastic":
        tbdata = next(line for line in lines if line.startswith("TBDATA"))
        return 2.0 / float(tbdata.split(",")[-1])  # d = 2/K
    mathp = large(next(line for line in lines if line.startswith("MATHP*")))
    return 2.0 * float(mathp[4])  # MSC D1 = K/2


class Test초탄성_체적:
    """**같은 카드는 솔버가 달라도 같은 체적 거동이다.** 전에는 Abaqus · ANSYS 만 ν 를 버리고
    늘 D = 0(완전 비압축)이라, 같은 고무가 한쪽에서는 하이브리드 요소를 요구하고 다른 쪽에서는
    ν = 0.4995 의 고무였다(2026-10-03 공개 덱 대조 — 공개 Abaqus 고무 덱이 모두 D1 을
    적었다)."""

    MR: ClassVar[dict[str, Any]] = hyper("mooney_rivlin", c10=0.6e6, c01=0.15e6)

    def test_Abaqus_ANSYS_Nastran_이_같은_K_를_적는다(self) -> None:
        shear = 2.0 * (0.6 + 0.15)  # MPa — mm·N·tonne
        bulk = 2.0 * shear * 1.4995 / (3.0 * (1.0 - 2.0 * 0.4995))
        for key in ("abaqus_hyperelastic", "ansys_hyperelastic", "nastran_hyperelastic"):
            text = mm(key, elastic=RUBBER, hyperelastic=self.MR)
            assert _bulk_from_deck(key, text) == pytest.approx(bulk, rel=1e-9), key

    @pytest.mark.parametrize("key", ["abaqus_hyperelastic", "ansys_hyperelastic"])
    def test_Ogden_의_K_는_카드의_μ_에서(self, key: str) -> None:
        """ANSYS 는 μ₁ 을 2μ/α 로 옮겨 적지만 K 는 카드의 μ(= 초기 전단탄성률)에서 나온다."""
        rubber = hyper("ogden_1", mu=1.5e6, alpha=3.0)
        bulk = 2.0 * 1.5 * 1.4995 / (3.0 * (1.0 - 2.0 * 0.4995))
        text = mm(key, elastic=RUBBER, hyperelastic=rubber)
        assert _bulk_from_deck(key, text) == pytest.approx(bulk, rel=1e-9)

    @pytest.mark.parametrize("key", ["abaqus_hyperelastic", "ansys_hyperelastic"])
    def test_ν_가_없거나_0_5_면_완전_비압축이고_그렇다고_말한다(self, key: str) -> None:
        for elastic in ({"values": {"density": 1100.0}}, {"values": {"poisson_ratio": 0.5}}):
            made = render(key, deck(elastic=elastic, hyperelastic=self.MR), MM_N_TONNE)
            assert "fully incompressible" in made.text
            assert any("0 으로 두었습니다" in note for note in made.notes)

    @pytest.mark.parametrize("key", ["abaqus_hyperelastic", "ansys_hyperelastic"])
    def test_ν_가_범위_밖이면_거절하고_낮으면_말한다(self, key: str) -> None:
        with pytest.raises(ExportError, match=r"0\.5 이하"):
            mm(key, elastic={"values": {"poisson_ratio": 0.6}}, hyperelastic=self.MR)
        low = render(
            key, deck(elastic={"values": {"poisson_ratio": 0.3}}, hyperelastic=self.MR)
        )
        assert any("고무치고 낮습니다" in note for note in low.notes)


class TestRadioss:
    def test_LAW36_의_fct_IDp_줄과_VP_자리(self) -> None:
        """파서가 `fct_IDp` 줄을 무조건 읽는다 — 빼면 곡선 번호가 압력 함수 자리로 간다.
        VP 는 91~100열이다(81~90 은 빈 칸)."""
        lines = mm(
            "openradioss_rate", elastic=STEEL, rate_table=rates(0.001, 100.0)
        ).splitlines()
        head = after(lines, "N_funct")
        assert cols(head, 10, 10, 20, 20, 20, 10, 10) == ["2", "2", "", "", "", "", "1"]
        assert after(lines, "fct_IDp") == f"{0:>10}"
        assert cols(after(lines, "fct_ID1"), 10, 10) == ["10101", "10102"]
        assert cols(after(lines, "Eps_dot_1"), 20, 20) == [
            "1.000000000E-03",
            "1.000000000E+02",
        ]

    def test_여섯_속도면_다섯씩_끊고_셋이_차례로_선다(self) -> None:
        text = mm(
            "openradioss_rate",
            elastic=STEEL,
            rate_table=rates(0.001, 0.01, 0.1, 1.0, 10.0, 100.0, factor=1.02),
        )
        lines = text.splitlines()
        start = label_at(lines, "fct_ID1")
        ids, more = lines[start + 1], lines[start + 2]
        assert len(cols(ids, *(10,) * 5)) == 5 and more.strip() == "10106"
        assert lines[start + 3].startswith("#") and "Fscale_1" in lines[start + 3]

    def test_단위는_Mg_이고_단일_곡선_덱도_fct_IDp_가_있다(self) -> None:
        lines = mm("openradioss", elastic=STEEL, table=TABLE).splitlines()
        assert f"{'Mg':>20}{'mm':>20}{'s':>20}" in lines
        assert after(lines, "fct_IDp") == f"{0:>10}"
        assert after(lines, "fct_ID1").strip() == "101"

    def test_HEAT_MAT_은_제목_줄이_없고_둘째_줄이_있다(self) -> None:
        thermal = {"values": {"specific_heat": 460.0, "thermal_conductivity": 45.0}}
        lines = mm("openradioss_thermal", elastic=STEEL, thermal=thermal).splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("/HEAT/MAT"))
        # 바로 다음 값 줄이 T0·RHOCP 줄이다 — 이름 줄이 끼면 값이 한 줄씩 밀린다.
        body = [line for line in lines[start + 1 :] if not line.startswith("#")]
        assert "E+" in body[0]
        assert body[1] == "" and body[2] == "/END"

    def test_LAW1(self) -> None:
        lines = mm("openradioss_elastic", elastic=STEEL).splitlines()
        assert "/MAT/LAW1/101/1" in lines
        assert cols(after(lines, "E"), 20, 20) == [
            "2.100000000E+05",
            "3.000000000E-01",
        ]

    def test_LAW42_Mooney_는_두_Ogden_항이고_μ·α_는_두_장씩(self) -> None:
        lines = mm(
            "openradioss_hyperelastic",
            elastic=RUBBER,
            hyperelastic=hyper("mooney_rivlin", c10=0.6e6, c01=0.15e6),
        ).splitlines()
        start = label_at(lines, "mu_1")
        assert cols(lines[start + 1], 20, 20) == ["1.200000000E+00", "-3.000000000E-01"]
        # 둘째 장(μ₆~μ₁₀)이 빠지면 α 줄이 그 자리로 먹힌다.
        assert lines[start + 3].startswith("#") and "alpha_1" in lines[start + 3]
        assert cols(lines[start + 4], 20, 20) == ["2.000000000E+00", "-2.000000000E+00"]

    def test_LAW42_는_Yeoh_를_안_낸다(self) -> None:
        with pytest.raises(ExportError, match="Yeoh"):
            mm(
                "openradioss_hyperelastic",
                elastic=RUBBER,
                hyperelastic=hyper("yeoh", c10=0.5e6, c20=0.0, c30=0.0),
            )

    def test_점탄성은_μ_가_장기이고_ν_가_K0_를_맞춘다(self) -> None:
        """LAW42 의 μ 는 장기(G∞)이고 Gᵢ 가 그 위에 더해진다. 체적은 μ·ν 로 만들어지므로
        카드의 ν 를 그대로 두면 체적까지 장기 전단을 따라 무르게 된다."""
        lines = mm(
            "openradioss_viscoelastic", elastic=POLYMER, viscoelastic=PRONY
        ).splitlines()
        nu = float(cols(after(lines, "nu"), 20)[0])
        mu = float(cols(after(lines, "mu_1"), 20)[0])
        assert mu == pytest.approx(450.0)
        bulk = mu * 2.0 * (1.0 + nu) / (3.0 * (1.0 - 2.0 * nu))
        assert bulk == pytest.approx(2800.0 / (3.0 * (1.0 - 0.8)), rel=1e-6)
        assert cols(after(lines, "G_1"), 20, 20) == [
            "3.000000000E+02",
            "2.500000000E+02",
        ]
        assert cols(after(lines, "tau_1"), 20, 20) == [
            "1.000000000E-02",
            "1.000000000E-01",
        ]


class TestAbaqus_빈칸:
    """소성 표도 선형탄성구간도 없는 카드는 Abaqus 로만 못 나갔다 — 문헌 값·선언 물성 카드,
    그리고 탄성 없는 열물성 카드(2026-09-27, 형식 표를 채우면서 드러났다)."""

    def test_선형은_ELASTIC_와_열물성이다(self) -> None:
        thermal = {"values": {"thermal_conductivity": 45.0, "specific_heat": 460.0}}
        text = mm("abaqus_elastic", elastic=STEEL, thermal=thermal)
        lines = text.splitlines()
        assert lines[lines.index("*ELASTIC, TYPE=ISOTROPIC") + 1] == (
            "2.100000000000E+05, 3.000000000000E-01"
        )
        assert "*CONDUCTIVITY, TYPE=ISO" in lines and "*PLASTIC" not in text
        assert "abaqus_elastic" in export.available_formats(deck(elastic=STEEL))

    def test_열물성은_탄성_없이도_낸다(self) -> None:
        thermal = {"values": {"thermal_conductivity": 45.0, "specific_heat": 460.0}}
        alone = deck(thermal=thermal, elastic={"values": {"density": 7850.0}})
        assert "abaqus_thermal" in export.available_formats(alone)
        text = render("abaqus_thermal", alone, MM_N_TONNE).text
        assert "*ELASTIC" not in text
        assert "*DENSITY" in text and "*SPECIFIC HEAT" in text
