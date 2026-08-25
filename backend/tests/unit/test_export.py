"""솔버 카드 — **덱에 그대로 들어가는 텍스트다.**

이 파일이 지키는 것은 셋이다.

1. **칸과 순서.** OpenRadioss 는 고정 20칸이고 Abaqus 는 응력이 먼저다. 하나
   어긋나면 솔버는 오류 없이 다른 재료로 계산한다 — 그게 가장 나쁜 실패다.
2. **없는 값을 만들지 않는다.** 푸아송비가 없으면 0.3 을 넣지 않고 거부한다.
3. **조용히 고치지 않는다.** 응력이 떨어지는 표는 눕혀서 내보내지 않는다.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest

from matcore import export


def deck(
    *,
    youngs_modulus: float | None = 200e9,
    poisson_ratio: float | None = 0.3,
    density: float | None = 7850.0,
    points: tuple[tuple[float, float], ...] = (
        (0.0, 250e6),
        (0.01, 300e6),
        (0.05, 340e6),
    ),
    provenance: tuple[str, ...] = ("시편 3개 · SECC_MDOI_1.0",),
) -> export.Deck:
    """탄소성 덱 하나. **블록으로 담는다** — 카드 양식은 없어졌다."""
    elastic = {
        key: value
        for key, value in (
            ("youngs_modulus", youngs_modulus),
            ("poisson_ratio", poisson_ratio),
            ("density", density),
        )
        if value is not None
    }
    blocks: dict[str, Any] = {}
    if elastic:
        blocks["elastic"] = {"values": elastic}
    if points:
        blocks["table"] = {
            "rows": [{"plastic_strain": x, "true_stress": y} for x, y in points]
        }
    return export.Deck(name="DP600_MD", solver_id=42, blocks=blocks, provenance=provenance)


CARD = deck()


class Test형식:
    def test_abaqus_는_응력이_먼저다(self) -> None:
        """**Abaqus 와 OpenRadioss 가 서로 반대다.** 바꿔 적으면 변형률 250000000
        인 재료가 되는데, 솔버는 그것을 오류로 보지 않는다."""
        text = export.render("abaqus", CARD).text
        assert "*PLASTIC, HARDENING=ISOTROPIC, EXTRAPOLATION=CONSTANT" in text
        assert "2.500000000000E+08, 0.000000000000E+00" in text

    def test_openradioss_는_소성변형률이_먼저다(self) -> None:
        text = export.render("openradioss", CARD).text
        assert "/MAT/LAW36/42/1" in text
        assert "/FUNCT/42" in text
        # X=소성변형률, Y=응력.
        assert "  0.000000000000E+00     2.500000000E+08" in text

    def test_고정_20칸을_지킨다(self) -> None:
        """**칸이 어긋나면 다른 필드로 읽힌다.** 그러면 밀도가 탄성계수가 된다."""
        lines = export.render("openradioss", CARD).text.splitlines()
        start = lines.index(f"#{'X':>19}{'Y':>20}") + 1
        rows = lines[start : lines.index("/END")]
        assert len(rows) == len(CARD.rows("table"))
        for row in rows:
            assert len(row) == 40, row
        # 스칼라 한 줄짜리 필드도 같은 칸이다.
        assert lines[lines.index(f"#{'RHO_I':>19}") + 1] == f"{7850.0:>20.9E}"

    def test_단위를_선언한다(self) -> None:
        """**환산하지 않는다 — 선언한다.** 우리가 mm 로 바꿔 내보내면 그 덱의
        다른 재료가 SI 인지 확인할 길이 없다."""
        radioss = export.render("openradioss", CARD).text
        assert "/UNIT/1" in radioss and "kg" in radioss
        # Abaqus 는 단위 키워드가 없다. 그래서 주석으로 적는다.
        assert "Consistent units: kg, m, s, Pa" in export.render("abaqus", CARD).text

    def test_중립_JSON_은_스스로_설명한다(self) -> None:
        """**받는 사람이 되짚을 수 있어야 한다.** 값 옆에 이름과 단위를 적는다 —
        `200000000000` 만 남으면 Pa 인지 MPa 인지 알 길이 없다.

        정해진 칸이 없다. 카드에 실린 블록을 그대로 낸다 — 새 물성이 저절로
        따라온다."""
        body = json.loads(export.render("json", CARD).text)
        elastic = body["blocks"]["elastic"]
        assert elastic["values"]["youngs_modulus"] == 200e9
        assert elastic["declared"]["youngs_modulus"]["si_unit"] == "Pa"
        assert elastic["label"] == "탄성"
        rows = body["blocks"]["table"]["rows"]
        assert rows[0]["true_stress"] == 250e6

    def test_같은_카드는_같은_바이트다(self) -> None:
        # 두 파일이 다른지 보려고 열어 보는 일이 실제로 생긴다.
        assert export.render("json", CARD).text == export.render("json", CARD).text

    def test_근거가_카드_안에_들어간다(self) -> None:
        """**덱만 받은 사람이 되짚을 수 있어야 한다.** 파일이 메일로 돌아다니는
        동안 이 주석이 유일한 출처 표시다."""
        assert "SECC_MDOI_1.0" in export.render("abaqus", CARD).text
        assert "SECC_MDOI_1.0" in export.render("openradioss", CARD).text


class Test없는값:
    def test_푸아송비가_없으면_거부한다(self) -> None:
        """0.3 을 넣으면 그것이 측정값인지 덱만 봐서는 알 수 없다."""
        card = deck(poisson_ratio=None, density=None)
        with pytest.raises(export.ExportError, match="푸아송비"):
            export.render("abaqus", card)

    def test_밀도가_없으면_openradioss_는_거부한다(self) -> None:
        # LAW36 은 RHO_I 가 자리 있는 필드다. 비울 수 없다.
        card = deck(density=None)
        with pytest.raises(export.ExportError, match="밀도"):
            export.render("openradioss", card)

    def test_밀도가_없으면_abaqus_는_빼고_그_사실을_적는다(self) -> None:
        """`*DENSITY` 는 Abaqus 에서 선택이다. 빼되 **왜 뺐는지 덱에 적는다** —
        동적 해석을 돌리려던 사람이 덱만 보고 알 수 있어야 한다."""
        card = deck(density=None)
        result = export.render("abaqus", card)
        assert "*DENSITY" not in result.text
        assert "동적 해석" in result.text
        assert any("밀도" in note for note in result.notes)


class Test표정리:
    def test_탄성_구간을_0_으로_자른_자국을_한_점으로_모은다(self) -> None:
        """`clip_zero` 가 남긴 것이라 값이 아니라 자국이다.

        **마지막 0 점이 항복점이다.** 첫 점을 쓰면 응력이 0 에 가까운 곳을
        항복강도라고 적게 된다.
        """
        card = deck(points=((0.0, 10e6), (0.0, 150e6), (0.0, 250e6), (0.01, 300e6)))
        points, notes = export.prepare(card.pairs("table", "plastic_strain", "true_stress"))
        assert points[0] == (0.0, 250e6)
        assert len(points) == 2
        assert any("항복점" in note for note in notes)

    def test_첫_점이_0_이_아니면_거부한다(self) -> None:
        # 0.2% 소성변형이면 이미 소성 구간이다. 항복점이 진짜로 빠진 것이다.
        with pytest.raises(export.ExportError, match="0 이어야"):
            export.prepare(((0.002, 250e6), (0.01, 300e6)))

    def test_거의_0_이면_자리만_맞춘다(self) -> None:
        """진소성변형률 축에서 재샘플하면 공통 시작이 2e-6 처럼 나온다.

        **값을 지어내는 것이 아니라 자리를 맞추는 것이다** — 격자 간격보다 네
        자릿수 작아 응력은 항복점 그대로다. 옮겼다는 사실은 근거에 남는다.
        """
        points, notes = export.prepare(((2.2e-6, 341e6), (0.01, 380e6), (0.05, 400e6)))
        assert points[0] == (0.0, 341e6)
        assert any("0 으로 맞췄습니다" in note for note in notes)

    def test_변형률이_순증가가_아니면_거부한다(self) -> None:
        with pytest.raises(export.ExportError, match="순증가"):
            export.prepare(((0.0, 250e6), (0.02, 300e6), (0.01, 320e6)))

    def test_응력이_떨어지면_눕히지_않고_거부한다(self) -> None:
        """**연화를 숨기지 않는다.**

        눕혀서 내보내면 그 덱은 실제와 다른 재료가 되고, 아무도 그 사실을 모른다.
        네킹 뒤 구간이 섞인 것이 보통이라 무엇을 하면 되는지 함께 말한다.
        """
        with pytest.raises(export.ExportError, match="네킹") as caught:
            export.prepare(((0.0, 250e6), (0.01, 300e6), (0.02, 280e6)))
        assert "실제와 다른 재료" in str(caught.value)

    def test_너무_길면_거부한다(self) -> None:
        many = tuple((index * 1e-4, 250e6 + index) for index in range(export.MAX_POINTS + 1))
        with pytest.raises(export.ExportError, match="재샘플"):
            export.prepare(many)


class Test이름:
    def test_한글_이름을_솔버가_읽는_모양으로_바꾼다(self) -> None:
        # 그대로 넣으면 솔버가 못 읽거나 말없이 잘라 버린다.
        assert export.sanitize_name("인장 MD") == "MD"
        assert export.sanitize_name("SECC_MDOI_1.0") == "SECC_MDOI_1_0"

    def test_숫자로_시작해도_고친다(self) -> None:
        # 솔버 이름은 영문자로 시작해야 한다.
        assert export.sanitize_name("304 Stainless") == "MATERIAL_304_Stainless"

    def test_남는_글자가_없으면_거부한다(self) -> None:
        # 전부 한글이면 이름이 사라진다. 빈 이름으로 내보내면 덱에서 재료를
        # 가리킬 수 없다 — 어떤 이름을 지어야 하는지 말해 준다.
        with pytest.raises(export.ExportError, match="이름"):
            export.sanitize_name("인장", fallback="")

    def test_덱_번호는_같은_카드에_같은_값이다(self) -> None:
        value = "b7564344-72e6-49ce-ac1b-0d4f40fe4e23"
        assert export.solver_id_from(value) == export.solver_id_from(value)
        assert 1 <= export.solver_id_from(value) <= export.MAX_SOLVER_ID


class Test태도:
    def test_쓴_뒤에_다시_읽는다(self) -> None:
        """키워드가 빠진 파일은 솔버가 오류 없이 무시하기도 한다 — 그러면 해석은
        도는데 재료가 안 들어간 채로 돈다.

        **형식마다 받는 물성 모형이 다르다.** 처음에는 모든 형식에 이 탄소성
        카드를 넣었는데, 점탄성 형식이 붙으면서 그 전제가 깨졌다(Prony 계수가
        없다). 카드가 감당하는 형식만 돈다 — 나머지는 `Test거절` 이 본다.

        **무엇을 감당하는지는 카드에게 묻는다.** 전에는 여기서 `"prony" in
        requires` 로 걸러냈는데, 초탄성 형식이 붙자 그 목록에도 이름을 더해야
        했다 — 안 더하면 이 시험이 빨개진다. 새 형식이 붙을 때마다 시험을 고쳐야
        하면 그 시험은 형식의 목록을 두 번째로 적어 둔 것일 뿐이다.
        """
        for key in export.available_formats(CARD):
            text = export.render(key, CARD).text
            for word in export.renderer(key).keywords:
                assert word in text

    def test_모르는_형식은_있는_것을_알려_준다(self) -> None:
        with pytest.raises(export.ExportError, match="있는 것"):
            export.render("nastran", CARD)


def thermal_deck(**values: float | str) -> export.Deck:
    """열물성이 붙은 덱. 시험이 안 주는 값들이라 대개 선언 물성에서 온다."""
    base = deck()
    return export.Deck(
        name=base.name,
        solver_id=base.solver_id,
        blocks={**base.blocks, "thermal": {"values": dict(values)}},
        provenance=base.provenance,
    )


class Test열물성:
    """`*EXPANSION` · `*SPECIFIC HEAT` · `*CONDUCTIVITY`.

    **인장시험이 하나도 안 주는 값들이다.** 여기까지 이어져야 선언 물성이 실제
    쓸모를 갖는다 — 그전까지는 넣어 두고 안 쓰는 칸이다(ADR 0016).
    """

    def test_없으면_한_줄도_안_낸다(self) -> None:
        text = export.render("abaqus", CARD).text
        assert "*EXPANSION" not in text
        assert "*SPECIFIC HEAT" not in text
        assert "*CONDUCTIVITY" not in text

    def test_셋_다_실린다(self) -> None:
        text = export.render(
            "abaqus",
            thermal_deck(
                thermal_expansion=1.17e-05,
                specific_heat=462.0,
                thermal_conductivity=45.0,
            ),
        ).text
        assert f"*EXPANSION, TYPE=ISO\n{1.17e-05:.12E}," in text
        assert f"*SPECIFIC HEAT\n{462.0:.12E}," in text
        assert f"*CONDUCTIVITY, TYPE=ISO\n{45.0:.12E}," in text

    def test_하나만_있어도_낸다(self) -> None:
        """**셋을 묶지 않는다.** 열팽창만 아는 재료로 열응력 해석은 돌아간다 —
        셋을 다 요구하면 그 재료는 영영 덱이 안 나온다."""
        text = export.render("abaqus", thermal_deck(thermal_conductivity=45.0)).text
        assert "*CONDUCTIVITY" in text
        assert "*EXPANSION" not in text
        assert "*SPECIFIC HEAT" not in text

    def test_기준_온도가_없으면_ZERO_를_안_붙인다(self) -> None:
        """`ZERO` 는 열변형이 0 이 되는 온도다. 없는데 293.15 를 적어 넣으면
        **덱은 멀쩡히 돌고 열응력만 통째로 어긋난다.** 안 적으면 Abaqus 가
        해석의 초기 온도를 쓴다 — 그것이 맞는 기본값이다."""
        text = export.render("abaqus", thermal_deck(thermal_expansion=1.17e-05)).text
        assert "ZERO" not in text
        with_zero = export.render(
            "abaqus", thermal_deck(thermal_expansion=1.17e-05, reference_temperature=293.15)
        ).text
        assert f"*EXPANSION, TYPE=ISO, ZERO={293.15:.12E}" in with_zero

    def test_잰_값인지_적은_값인지_덱에_남는다(self) -> None:
        """덱만 받은 사람이 이 숫자의 무게를 알 수 있어야 한다."""
        text = export.render(
            "abaqus",
            thermal_deck(specific_heat=462.0, specific_heat_source="declared:standard"),
        ).text
        assert "source=declared:standard" in text

    def test_소성_표보다_먼저_나온다(self) -> None:
        """`*PLASTIC` 뒤에 오면 그 줄들이 소성 표의 데이터 줄로 읽힌다 —
        Abaqus 는 키워드 뒤의 숫자 줄을 그 키워드의 것으로 먹는다."""
        text = export.render("abaqus", thermal_deck(specific_heat=462.0)).text
        assert text.index("*SPECIFIC HEAT") < text.index("*PLASTIC")

    def test_열물성만으로는_덱이_안_나온다(self) -> None:
        """**선택이라는 말이 '없어도 된다' 지 '그것만 있어도 된다' 는 아니다.**"""
        alone = export.Deck(
            name="X", solver_id=1, blocks={"thermal": {"values": {"specific_heat": 462.0}}}
        )
        assert export.missing_for(alone, "abaqus")


def temperature_deck(
    elastic_rows: list[dict[str, Any]] | None = None,
    thermal_rows: list[dict[str, Any]] | None = None,
) -> export.Deck:
    """온도 표를 든 덱."""
    base = deck()
    blocks = dict(base.blocks)
    if elastic_rows is not None:
        blocks["elastic"] = {**blocks["elastic"], "rows": elastic_rows}
    if thermal_rows is not None:
        blocks["thermal"] = {
            "values": {"thermal_expansion": thermal_rows[0]["thermal_expansion"]},
            "rows": thermal_rows,
        }
    return export.Deck(
        name=base.name, solver_id=base.solver_id, blocks=blocks, provenance=base.provenance
    )


class Test온도의존:
    """**강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어진다.**

    열간 성형·용접·화재 해석은 그 곡선이 필요하다. 값 하나로는 그 해석이 통째로
    막힌다.
    """

    ROWS: ClassVar[list[dict[str, Any]]] = [
        {"temperature": 293.15, "youngs_modulus": 206e9, "poisson_ratio": 0.30},
        {"temperature": 473.15, "youngs_modulus": 195e9, "poisson_ratio": 0.31},
        {"temperature": 673.15, "youngs_modulus": 170e9, "poisson_ratio": 0.32},
    ]

    def test_온도_열이_붙는다(self) -> None:
        text = export.render("abaqus", temperature_deck(elastic_rows=self.ROWS)).text
        body = text[text.index("*ELASTIC") :]
        assert f"{206e9:.12E}, {0.30:.12E}, {293.15:.12E}" in body
        assert f"{170e9:.12E}, {0.32:.12E}, {673.15:.12E}" in body

    def test_한_온도짜리에는_온도_열을_안_붙인다(self) -> None:
        """**붙이면 솔버가 「이 온도에서만 유효」로 읽는다.** 표 밖에서 외삽
        규칙이 달라지고, 상수인 재료가 갑자기 온도 의존이 된다."""
        text = export.render("abaqus", temperature_deck(elastic_rows=self.ROWS[:1])).text
        line = text[text.index("*ELASTIC") :].splitlines()[1]
        assert line.count(",") == 1, line

        # 표가 아예 없을 때도 같다.
        plain = export.render("abaqus", CARD).text
        assert plain[plain.index("*ELASTIC") :].splitlines()[1].count(",") == 1

    def test_표_밖에서_끝값이_유지된다고_적는다(self) -> None:
        """**덱만 받은 사람은 어디까지가 적힌 것인지 알 수 없다.** 400 °C 까지
        적고 800 °C 해석을 돌리면 재료가 그 온도에서도 170 GPa 인 셈이 된다."""
        text = export.render("abaqus", temperature_deck(elastic_rows=self.ROWS)).text
        assert "끝값이 유지됩니다" in text
        assert "293.15~673.15" in text

    def test_빈_칸이_있으면_거절한다(self) -> None:
        """**줄을 조용히 버리지 않는다.** `*ELASTIC` 은 한 줄에 `(E, ν, T)` 를
        받으므로 하나라도 비면 그 온도를 낼 수 없는데, 그냥 빼면 덱은 나가고 그
        구간에서 솔버가 이웃 온도의 값을 쓴다 — 오류 없이 다른 재료가 된다."""
        holed = [
            {"temperature": 293.15, "youngs_modulus": 206e9, "poisson_ratio": 0.30},
            {"temperature": 673.15, "youngs_modulus": 170e9},  # 푸아송비가 없다
        ]
        with pytest.raises(export.ExportError) as caught:
            export.render("abaqus", temperature_deck(elastic_rows=holed))
        assert "빈 칸" in str(caught.value)
        assert "poisson_ratio" in str(caught.value)

    def test_열물성도_표로_나간다(self) -> None:
        rows = [
            {"temperature": 293.15, "thermal_expansion": 1.17e-05},
            {"temperature": 673.15, "thermal_expansion": 1.42e-05},
        ]
        text = export.render("abaqus", temperature_deck(thermal_rows=rows)).text
        body = text[text.index("*EXPANSION") :]
        assert f"{1.17e-05:.12E}, {293.15:.12E}" in body
        assert f"{1.42e-05:.12E}, {673.15:.12E}" in body

    def test_표가_있으면_값을_두_번_안_낸다(self) -> None:
        """**같은 물성이 두 번 실리면 솔버가 뒤엣것으로 덮거나 거절한다.**"""
        rows = [
            {"temperature": 293.15, "thermal_expansion": 1.17e-05},
            {"temperature": 673.15, "thermal_expansion": 1.42e-05},
        ]
        text = export.render("abaqus", temperature_deck(thermal_rows=rows)).text
        assert text.count("*EXPANSION") == 1
        # **`*EXPANSION` 구간만 센다.** 뒤에 오는 `*PLASTIC` 표까지 세면
        # 시험이 무엇을 보는지 흐려진다.
        body = text[text.index("*EXPANSION") :]
        numbers = []
        for line in body.splitlines()[1:]:
            if line.startswith("**"):
                continue
            if line.startswith("*"):
                break
            numbers.append(line)
        assert len(numbers) == 2, numbers

    def test_열이_빠진_줄은_그_키워드에_안_실린다(self) -> None:
        """열팽창만 온도를 타고 비열은 상수인 것이 흔하다. 빈 칸을 0 으로
        채우면 **비열 0 인 재료**가 된다."""
        rows = [
            {"temperature": 293.15, "thermal_expansion": 1.17e-05, "specific_heat": 462.0},
            {"temperature": 673.15, "thermal_expansion": 1.42e-05},
        ]
        text = export.render("abaqus", temperature_deck(thermal_rows=rows)).text
        heat = text[text.index("*SPECIFIC HEAT") :]
        assert f"{462.0:.12E}," in heat
        assert "0.000000000000E+00" not in heat.splitlines()[1]


def heat_deck(
    *,
    density: float | None = 7850.0,
    values: dict[str, float] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> export.Deck:
    """열해석용 덱 하나."""
    blocks: dict[str, Any] = {}
    if density is not None:
        blocks["elastic"] = {"values": {"density": density}}
    thermal: dict[str, Any] = {"values": values or {}}
    if rows:
        thermal["rows"] = rows
    if thermal["values"] or rows:
        blocks["thermal"] = thermal
    return export.Deck(name="SECC_MD", solver_id=42, blocks=blocks)


BASE = {"specific_heat": 462.0, "thermal_conductivity": 45.0, "reference_temperature": 293.15}


class TestOpenRadioss열물성:
    """`/HEAT/MAT` — **Abaqus 와 받는 모양이 다르다.**

        Abaqus        온도-값 표를 그대로
        OpenRadioss   체적 열용량 상수 + 전도도 직선 두 계수

    바꾸는 과정에 실수가 숨을 자리가 둘 있다: 비열에 밀도를 안 곱하는 것과,
    표를 직선으로 누른 사실을 안 적는 것이다.
    """

    def test_비열에_밀도를_곱한다(self) -> None:
        """**체적 열용량이다**(J/(m³·K)). 우리가 담은 것은 질량 기준
        비열(J/(kg·K))이라 곱하지 않으면 밀도 배만큼 틀리고, **덱은 멀쩡히 돌고
        온도만 안 오른다.**"""
        text = export.render("openradioss_thermal", heat_deck(values=BASE)).text
        assert f"{7850.0 * 462.0:>20.9E}" in text
        # 비열 그 자체가 들어가면 안 된다.
        assert f"{462.0:>20.9E}" not in text

    def test_밀도가_없으면_못_낸다(self) -> None:
        """0 을 넣으면 열용량 0 인 재료가 된다."""
        assert "openradioss_thermal" not in export.available_formats(
            heat_deck(density=None, values=BASE)
        )

    def test_전도도가_없으면_거절한다(self) -> None:
        """**AS 는 자리 있는 필드다.** 0 을 넣으면 열이 안 퍼지는 재료가 된다."""
        with pytest.raises(export.ExportError) as caught:
            export.render("openradioss_thermal", heat_deck(values={"specific_heat": 462.0}))
        assert "열전도도" in str(caught.value)

    def test_전도도를_직선으로_맞춘다(self) -> None:
        """`/HEAT/MAT` 은 표를 안 받는다 — `AS + BS·T` 두 계수다."""
        rows = [
            {"temperature": 300.0, "thermal_conductivity": 45.0},
            {"temperature": 500.0, "thermal_conductivity": 41.0},
        ]
        text = export.render("openradioss_thermal", heat_deck(values=BASE, rows=rows)).text
        # 두 점이면 직선이 정확히 지난다: 기울기 -0.02, 절편 51
        assert f"{51.0:>20.9E}" in text
        assert f"{-0.02:>20.9E}" in text

    def test_누른_어긋남을_적는다(self) -> None:
        """**안 적으면 사람은 표를 넣은 대로 나갔다고 믿는다** — 실제로는
        직선으로 눌린 값이 솔버에 간다."""
        rows = [
            {"temperature": 300.0, "thermal_conductivity": 45.0},
            {"temperature": 400.0, "thermal_conductivity": 30.0},
            {"temperature": 500.0, "thermal_conductivity": 41.0},
        ]
        rendered = export.render("openradioss_thermal", heat_deck(values=BASE, rows=rows))
        joined = " ".join(rendered.notes)
        assert "직선으로 맞췄습니다" in joined
        assert "어긋남" in joined
        # **판정하지 않는다.** 몇 %부터 문제인지는 규격과 용도가 정한다.
        assert "합격" not in joined and "부적합" not in joined

    def test_두_점까지는_어긋남을_안_적는다(self) -> None:
        """직선이 정확히 지나가므로 적을 것이 없다. 늘 적으면 그 문장이
        **경고로 안 읽힌다.**"""
        rows = [
            {"temperature": 300.0, "thermal_conductivity": 45.0},
            {"temperature": 500.0, "thermal_conductivity": 41.0},
        ]
        rendered = export.render("openradioss_thermal", heat_deck(values=BASE, rows=rows))
        assert not any("직선으로 맞췄습니다" in note for note in rendered.notes)

    def test_열팽창은_안_실었다고_말한다(self) -> None:
        """Radioss 에서 열팽창은 역학 법칙 쪽이 받는다. **조용히 빼면** 넣은 줄
        알고 열응력 해석을 돌려 팽창 0 인 재료가 된다."""
        rendered = export.render(
            "openradioss_thermal",
            heat_deck(values={**BASE, "thermal_expansion": 1.17e-05}),
        )
        assert any("열팽창계수" in note for note in rendered.notes)
        assert "EXPANSION" in rendered.text

    def test_비열이_표면_어느_온도를_썼는지_말한다(self) -> None:
        """RHOCP 는 상수 한 칸이다 — 표를 넣으면 하나를 골라야 하고, **어느
        것을 골랐는지 말하지 않으면 사람이 알 방법이 없다.**"""
        rows = [
            {"temperature": 300.0, "specific_heat": 462.0, "thermal_conductivity": 45.0},
            {"temperature": 500.0, "specific_heat": 520.0, "thermal_conductivity": 41.0},
        ]
        rendered = export.render("openradioss_thermal", heat_deck(values=BASE, rows=rows))
        assert any("가장 낮은 온도" in note for note in rendered.notes)
        assert f"{7850.0 * 462.0:>20.9E}" in rendered.text

    def test_고정_20칸을_지킨다(self) -> None:
        """**칸이 어긋나면 다른 필드로 읽힌다.** 솔버는 오류를 안 낸다."""
        text = export.render("openradioss_thermal", heat_deck(values=BASE)).text
        row = [
            line
            for line in text.splitlines()
            if line and not line.startswith(("#", "/")) and "E+" in line
        ][0]
        assert len(row) == 80, f"{len(row)}칸: {row!r}"

    def test_소성_덱과_따로다(self) -> None:
        """Radioss 는 열물성을 별도 블록으로 받는다 — Abaqus 처럼 `*MATERIAL`
        아래 이어 붙이는 구조가 아니다."""
        text = export.render("openradioss_thermal", heat_deck(values=BASE)).text
        assert "/MAT/LAW36" not in text
        assert text.rstrip().endswith("/END")
