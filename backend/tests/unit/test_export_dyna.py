"""LS-DYNA 렌더러 — *MAT_024 · *MAT_076 · *MAT_THERMAL_ISOTROPIC.

무는 것이 넷이다.

    단위계가 값을 바꾼다      mm·N·tonne 로 내면 E 가 MPa 숫자로 적힌다 (환산 누락은
                            오류 없이 1000배 틀린 덱이다 — 가장 비싼 결함)
    모자라면 거부한다        푸아송비 없이 024 없음, Prony 없이 076 없음
    유도식이 덱에 적힌다      G0·K 를 어떻게 만들었는지 받은 사람이 되짚는다
    물리를 검사한다          Prony 합 ≥ 1 · 항 수 > 18 · ν ≥ 0.5 는 거부
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

import matcore.export.dyna  # noqa: F401  (렌더러 등록)
from matcore import cards
from matcore.export import Deck, ExportError, render
from matcore.export.systems import MM_N_TONNE

# 블록의 단위 선언(si_unit)이 있어야 to_system 이 환산한다.
cards.load_builtin()


def deck(**blocks: object) -> Deck:
    base: dict[str, object] = {
        "elastic": {
            "values": {"youngs_modulus": 200e9, "poisson_ratio": 0.3, "density": 7850.0}
        },
        "table": {
            "rows": [
                {"plastic_strain": 0.0, "true_stress": 350e6},
                {"plastic_strain": 0.05, "true_stress": 420e6},
            ]
        },
    }
    base.update(blocks)
    return Deck(
        name="SECC_MD",
        solver_id=101,
        blocks=base,
        provenance=("시험 3건: T-0001 · T-0002 · T-0003",),
    )


class Test탄소성_024:
    def test_SI_덱이_키워드와_값을_다_싣는다(self) -> None:
        made = render("dyna", deck())
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in made.text
        assert "*DEFINE_CURVE" in made.text
        # **줄 전체를 못 박는다.** 필드가 자리를 바꿔도(ro↔e) 부분 문자열 검사는
        # 통과한다 — 고정 10칸에서 자리 바뀜은 오류 없이 엉뚱한 재료다.
        assert "       101 7.850E+03 2.000E+11 3.000E-01 3.500E+08" in made.text
        # 출처가 $ 주석으로 들어간다 — 덱만 받은 사람이 되짚는 유일한 표시.
        assert "$ 시험 3건: T-0001" in made.text
        assert "Consistent units: kg, m, s, Pa" in made.text

    def test_단위계를_고르면_숫자와_선언이_함께_바뀐다(self) -> None:
        """**환산 누락은 오류 없이 1000배 틀린 덱이다.** 값·선언·곡선까지 전부
        그 계여야 한다 — 하나라도 SI 로 남으면 이 시험이 문다."""
        made = render("dyna", deck(), MM_N_TONNE)
        assert "Consistent units: tonne, mm, s, MPa" in made.text
        assert "2.000E+05" in made.text  # E: 200 GPa → 2e5 MPa
        assert "7.850E-09" in made.text  # 밀도: 7850 kg/m3 → 7.85e-9 tonne/mm3
        assert "3.500E+02" in made.text  # 항복강도: 350 MPa
        # 곡선 점(20칸)도 그 계다.
        assert "4.200000000E+02" in made.text
        # SI 숫자가 남아 있으면 안 된다.
        assert "2.000E+11" not in made.text

    def test_푸아송비가_없으면_거부한다(self) -> None:
        bare = deck(elastic={"values": {"youngs_modulus": 200e9, "density": 7850.0}})
        with pytest.raises(ExportError, match="푸아송비"):
            render("dyna", bare)


class Test점탄성_076:
    def viscoelastic(self, rows: list[dict[str, float]], **values: float) -> Deck:
        block: dict[str, object] = {
            "rows": rows,
            "values": {"reference_temperature_k": 296.15, **values},
        }
        return deck(
            elastic={
                "values": {"youngs_modulus": 2.8e9, "poisson_ratio": 0.4, "density": 1200.0}
            },
            viscoelastic=block,
        )

    def test_유도식과_값이_덱에_적힌다(self) -> None:
        made = render(
            "dyna_viscoelastic",
            self.viscoelastic([{"relative_modulus": 0.3, "relaxation_time_s": 10.0}]),
        )
        assert "*MAT_GENERAL_VISCOELASTIC" in made.text
        # G0 = 2.8e9/2.8 = 1e9 → Gi = 0.3e9. K = 2.8e9/0.6 ≈ 4.667e9. β = 0.1.
        assert "3.000E+08" in made.text
        assert "4.667E+09" in made.text
        assert "1.000E-01" in made.text
        assert "G0 = E/(2(1+nu))" in made.text
        assert "Valid at 296.15 K" in made.text

    def test_물리가_어긋나면_거부한다(self) -> None:
        with pytest.raises(ExportError, match="1 이상"):
            render(
                "dyna_viscoelastic",
                self.viscoelastic([{"relative_modulus": 1.2, "relaxation_time_s": 1.0}]),
            )
        many = [
            {"relative_modulus": 0.01, "relaxation_time_s": float(10**n)} for n in range(19)
        ]
        with pytest.raises(ExportError, match="18항"):
            render("dyna_viscoelastic", self.viscoelastic(many))


class Test열물성:
    def test_비열과_전도도가_실린다(self) -> None:
        made = render(
            "dyna_thermal",
            deck(thermal={"values": {"specific_heat": 460.0, "thermal_conductivity": 45.0}}),
        )
        assert "*MAT_THERMAL_ISOTROPIC" in made.text
        assert "4.600E+02" in made.text
        assert "4.500E+01" in made.text

    def test_밀도가_없으면_비우고_말한다(self) -> None:
        bare = Deck(
            name="PCM",
            solver_id=7,
            blocks={
                "thermal": {"values": {"specific_heat": 1800.0, "thermal_conductivity": 0.2}}
            },
        )
        made = render("dyna_thermal", bare)
        assert "TRO: no measured density" in made.text
        assert any("밀도" in note for note in made.notes)


# ── 카드를 건너뛰지 않는다 · 장기 탄성률 · 속도별 표 · 초탄성 (2026-09-27) ──────────────
#
# 매뉴얼(R13·R17)의 규칙은 「따로 적지 않았으면 카드는 필수」 다. 빠진 카드는 다음 줄이
# 그 자리로 읽힌다 — 오류 없이 다른 재료다.


def _between(text: str, start: str, end: str) -> list[str]:
    lines = text.splitlines()
    first = lines.index(start)
    last = next(i for i in range(first + 1, len(lines)) if lines[i].startswith(end))
    return [line for line in lines[first + 1 : last] if not line.startswith("$")]


class Test빠진_카드:
    def test_MAT_024_는_카드_넷이다(self) -> None:
        """LCSS 가 있어도 3·4번 카드(EPS·ES)는 있어야 한다."""
        body = _between(
            render("dyna", deck()).text, "*MAT_PIECEWISE_LINEAR_PLASTICITY", "*DEFINE_CURVE"
        )
        assert len(body) == 4
        assert body[2] == body[3] == f"{0:>10}" * 8

    def test_MAT_076_은_2번_카드와_장기_항이_있다(self) -> None:
        """2번 카드는 「Prony 를 쓰면 비워 두라」 는 칸이지 빼도 되는 카드가 아니다. 그리고
        076 에는 평형 탄성률 칸이 없다 — β=0 항이 없으면 재료가 전단 강성 0 으로 흘러내린다."""
        made = render(
            "dyna_viscoelastic",
            Test점탄성_076().viscoelastic(
                [{"relative_modulus": 0.3, "relaxation_time_s": 10.0}]
            ),
        )
        body = _between(made.text, "*MAT_GENERAL_VISCOELASTIC", "*END")
        assert body[1] == f"{0:>10}" * 8
        # G0 = 1e9 · G∞ = 0.7e9 (β=0) · G1 = 0.3e9 (β=0.1)
        assert body[2] == f"{0.7e9:>10.3E}{0.0:>10.3E}"
        assert body[3] == f"{0.3e9:>10.3E}{0.1:>10.3E}"


def _rate_deck(*ends: float) -> Deck:
    rows: list[dict[str, float]] = []
    for index, (rate, end) in enumerate(zip((0.001, 100.0), ends, strict=True)):
        rows.extend(
            {
                "strain_rate": rate,
                "plastic_strain": x,
                "true_stress": (350e6 + 400e6 * x) * (1 + 0.1 * index),
            }
            for x in (0.0, end / 2, end)
        )
    return deck(rate_table={"values": {"rate_count": 2}, "rows": rows})


class Test속도별_표:
    def test_표_뒤에_곡선이_값의_차례대로(self) -> None:
        """짝은 번호가 아니라 **자리**다. 곡선 사이에 다른 키워드가 끼면 안 된다."""
        text = render("dyna_rate", _rate_deck(0.2, 0.2), MM_N_TONNE).text
        lines = [line for line in text.splitlines() if not line.startswith("$")]
        table = lines.index("*DEFINE_TABLE")
        assert lines[table + 1] == f"{101:>10}"
        assert lines[table + 2 : table + 4] == [f"{0.001:>20.12E}", f"{100.0:>20.12E}"]
        assert lines[table + 4] == "*DEFINE_CURVE"
        curves = [i for i, line in enumerate(lines) if line == "*DEFINE_CURVE"]
        assert [lines[i + 1][:10].strip() for i in curves] == ["10101", "10102"]
        # LCSS 가 표를 가리키고 VP=1 이다.
        card2 = _between(text, "*MAT_PIECEWISE_LINEAR_PLASTICITY", "*DEFINE_TABLE")[1]
        assert card2[20:30].strip() == "101" and card2[40:50].strip() == "1.0"

    def test_끝이_다르면_짧은_끝에서_자르고_말한다(self) -> None:
        """표의 곡선은 같은 x 에서 끝나야 한다. 긴 곡선을 늘리지 않고 자른다."""
        made = render("dyna_rate", _rate_deck(0.4, 0.2), MM_N_TONNE)
        ends = [
            float(line[:20])
            for line in made.text.splitlines()
            if len(line) == 40 and not line.startswith("$")
        ]
        assert max(ends) == pytest.approx(0.2)
        assert any("잘랐습니다" in note for note in made.notes)


class Test초탄성:
    RUBBER: ClassVar[dict[str, Any]] = {"values": {"poisson_ratio": 0.4995, "density": 1100.0}}

    def hyper(self, family: str, **params: float) -> Deck:
        rows = [
            {"name": key, "value": value, "si_unit": "1" if key == "alpha" else "Pa"}
            for key, value in params.items()
        ]
        return Deck(
            name="EPDM",
            solver_id=7,
            blocks={
                "elastic": self.RUBBER,
                "hyperelastic": {"values": {"family": family}, "rows": rows},
            },
        )

    def test_Mooney_는_027_이고_2번_카드가_있다(self) -> None:
        text = render(
            "dyna_hyperelastic", self.hyper("mooney_rivlin", c10=0.6e6, c01=0.15e6), MM_N_TONNE
        ).text
        body = _between(text, "*MAT_MOONEY-RIVLIN_RUBBER", "*END")
        assert (
            body[0]
            == f"{7:>10}{1.1e-9:>10.3E}{0.4995:>10.3E}{0.6:>10.3E}{0.15:>10.3E}{0.0:>10.3E}"
        )
        assert body[1] == f"{0:>10}" * 4

    def test_Ogden_은_2μ_나누기_α_로_옮긴다(self) -> None:
        """077_O 는 G = Σμα/2 — 카드의 μ(Abaqus 규약, G = μ)를 그대로 넣으면 G 가 α/2 배."""
        text = render(
            "dyna_hyperelastic", self.hyper("ogden_1", mu=1.5e6, alpha=3.0), MM_N_TONNE
        ).text
        body = _between(text, "*MAT_OGDEN_RUBBER", "*END")
        assert body[1] == f"{1.0:>10.3E}" and body[2] == f"{3.0:>10.3E}"

    def test_푸아송비_없이는_안_낸다(self) -> None:
        bare = Deck(
            name="EPDM",
            solver_id=7,
            blocks={
                "elastic": {"values": {"density": 1100.0}},
                "hyperelastic": {
                    "values": {"family": "neo_hookean"},
                    "rows": [{"name": "c10", "value": 0.5e6}],
                },
            },
        )
        with pytest.raises(ExportError, match="푸아송비"):
            render("dyna_hyperelastic", bare)
