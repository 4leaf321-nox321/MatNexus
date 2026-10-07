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
        # **`EXTRAPOLATION=` 을 안 붙인다** — 2022 에 생긴 매개변수라 2021 이전 Abaqus 가
        # 모른다.
        # 기본(표 밖 응력 일정)과 같은 값이라 적을 까닭도 없다(2026-10-03 대조).
        assert "*PLASTIC, HARDENING=ISOTROPIC\n" in text
        assert "EXTRAPOLATION" not in text
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
        # **숫자에 단위를 안 붙인다.** 이 함수는 단위 환산 뒤에 불려 값이 이미 덱의
        # 계다 — `/1e6 MPa` 로 적으니 255 MPa 가 「0.000255 MPa」 로 나왔다(2026-09-05).
        assert "MPa" not in str(caught.value)
        assert "3e+08" in str(caught.value) and "2.8e+08" in str(caught.value)
        assert "실제와 다른 재료" in str(caught.value)

    def test_첫_점의_값이_항복점_같지_않으면_짚는다(self) -> None:
        """**첫 점의 «값»을 보는 검사다.**

        앵커 검사는 첫 점의 *변형률*이 0 인지만 본다 — 값은 아무도 안 봤다.
        그런데 솔버는 그 점을 초기 항복으로 읽는다(LS-DYNA 는 SIGY 를 거기서
        가져온다). 실측(2026-09-10): 첫 점 173.4 MPa 뒤 곧바로 352.7 MPa 였고
        뒤 구간은 점마다 0.7% 씩 올랐다 — **덱은 멀쩡히 돌고 항복만 절반**이었다.
        """
        points = [(0.0, 173e6), (0.001, 352e6)]
        points += [(0.001 + index * 0.001, 352e6 + index * 1e6) for index in range(1, 30)]
        kept, notes = export.prepare(tuple(points))
        assert len(kept) == len(points), "막지는 않는다"
        found = [note for note in notes if "첫 점이 항복점 값이 아닐 수" in note]
        assert found, notes
        # **숫자를 함께 준다.** 「이상합니다」 만으로는 심각한지 못 정한다.
        assert "103%" in found[0], found[0]
        assert "배입니다" in found[0], found[0]

    def test_고르게_오르는_표에는_안_짚는다(self) -> None:
        """**늘 짚으면 그 문장이 경고로 안 읽힌다.**"""
        points = tuple((index * 0.001, 250e6 + index * 1e6) for index in range(30))
        _, notes = export.prepare(points)
        assert not [note for note in notes if "첫 점이 항복점" in note], notes

    def test_점이_적으면_안_짚는다(self) -> None:
        """점이 서넛이면 「전형적인 상승」 이라 할 것이 없다 — 셋을 놓고 하나를
        이상하다고 하는 것은 판정이 아니라 짐작이다."""
        _, notes = export.prepare(((0.0, 100e6), (0.01, 300e6), (0.02, 305e6)))
        assert not [note for note in notes if "첫 점이 항복점" in note], notes

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
        """`ZERO` 는 할선 열팽창계수의 기준 온도다. 없는데 293.15 를 적어 넣으면
        **덱은 멀쩡히 돌고 열응력만 통째로 어긋난다.** 안 적으면 Abaqus 는 0 을
        쓰지만, α 가 값 하나면 기준 온도가 결과에 안 들어가 상관없다."""
        text = export.render("abaqus", thermal_deck(thermal_expansion=1.17e-05)).text
        assert "ZERO" not in text
        # **열팽창 자신의 온도에서만 온다.** 블록의 기준 온도를 쓰면 「비열을
        # 잰 온도」가 ZERO 로 나가는 일이 생긴다 — 실제로 그랬다(v1.80.0).
        elsewhere = export.render(
            "abaqus", thermal_deck(thermal_expansion=1.17e-05, reference_temperature=293.15)
        ).text
        assert "ZERO" not in elsewhere

        with_zero = export.render(
            "abaqus",
            thermal_deck(thermal_expansion=1.17e-05, thermal_expansion_temperature=293.15),
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

    def test_열팽창_표에_기준_온도가_없으면_덱에_적는다(self) -> None:
        """Abaqus 는 `ZERO` 가 없으면 **0** 을 쓴다 — 해석의 초기 온도가 아니다. 온도별
        α 표면 0 K 기준 할선값으로 읽혀 열변형이 어긋나는데 덱은 멀쩡히 돈다. 지어
        넣지는 않고(293.15 가 맞다는 보장이 없다) 받는 사람이 채우도록 적는다 —
        ANSYS `REFT` · Nastran `TREF` 와 같다. 전에는 아무 말도 없었다(2026-09-30)."""
        rows = [
            {"temperature": 293.15, "thermal_expansion": 1.17e-05},
            {"temperature": 673.15, "thermal_expansion": 1.42e-05},
        ]
        text = export.render("abaqus", temperature_deck(thermal_rows=rows)).text
        head = text[: text.index("*EXPANSION")]
        assert "ZERO not on the card - Abaqus uses ZERO=0" in head
        assert "*EXPANSION, TYPE=ISO\n" in text, "기준 온도를 지어 넣었다"

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

    @pytest.mark.parametrize(
        ("key", "keyword"), [("dyna", "*MAT_024"), ("openradioss", "LAW36")]
    )
    def test_상수만_받는_탄소성_형식은_접었다고_적는다(self, key: str, keyword: str) -> None:
        """*MAT_024 · LAW36 의 E · ν 는 상수다 — 온도 표를 받고도 첫 줄만 쓰면서 **아무 말을
        안 했다**(2026-10-07). 덱만 받은 사람이 알게 덱에, 화면이 보이게 각주에 적는다."""
        rendered = export.render(key, temperature_deck(elastic_rows=self.ROWS))
        assert f"{keyword} E and" in rendered.text
        assert "temperature independent" in rendered.text
        assert [
            note for note in rendered.notes if keyword in note and "가장 낮은 온도" in note
        ]
        # 한 온도짜리에는 안 적는다 — 늘 적으면 경고로 안 읽힌다.
        single = export.render(key, temperature_deck(elastic_rows=self.ROWS[:1]))
        assert "temperature independent" not in single.text

    def test_LS_DYNA_열물성도_표를_접었다고_적는다(self) -> None:
        """*MAT_THERMAL_ISOTROPIC 은 상수다. 설명은 「조용히 누르지 않는다」 였는데 코드는 표를
        안 보고 첫 값을 썼다(2026-10-07)."""
        rows = [
            {"temperature": 300.0, "specific_heat": 462.0, "thermal_conductivity": 45.0},
            {"temperature": 500.0, "specific_heat": 520.0, "thermal_conductivity": 41.0},
        ]
        rendered = export.render("dyna_thermal", heat_deck(values=BASE, rows=rows))
        assert "*MAT_THERMAL_ISOTROPIC is temperature independent" in rendered.text
        assert [note for note in rendered.notes if "*MAT_THERMAL_ISOTROPIC_TD" in note]
        # 열팽창만 온도를 타면(비열 · 전도도 표가 아니면) 이 형식이 접은 것이 없다.
        expansion = [
            {"temperature": 300.0, "thermal_expansion": 1.17e-05},
            {"temperature": 500.0, "thermal_expansion": 1.42e-05},
        ]
        plain = export.render("dyna_thermal", heat_deck(values=BASE, rows=expansion))
        assert "temperature independent" not in plain.text

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
        assert "열전도율" in str(caught.value)

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
        assert any("선팽창계수(CTE)" in note for note in rendered.notes)
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
        row = next(
            line
            for line in text.splitlines()
            if line and not line.startswith(("#", "/")) and "E+" in line
        )
        assert len(row) == 80, f"{len(row)}칸: {row!r}"

    def test_소성_덱과_따로다(self) -> None:
        """Radioss 는 열물성을 별도 블록으로 받는다 — Abaqus 처럼 `*MATERIAL`
        아래 이어 붙이는 구조가 아니다."""
        text = export.render("openradioss_thermal", heat_deck(values=BASE)).text
        assert "/MAT/LAW36" not in text
        assert text.rstrip().endswith("/END")


def test_형식마다_파일_이름이_다르다() -> None:
    """**같은 확장자를 내는 형식끼리 이름이 겹치면 안 된다.**

    한 카드가 `/MAT/LAW36`(역학)과 `/HEAT/MAT`(열)을 함께 내는데 둘 다 `.rad`
    다. 이름이 같으면 받는 쪽에 `SECC_MD.rad` 와 `SECC_MD (1).rad` 가 생기고,
    **어느 쪽이 열인지 알 수 없다.** 덮어쓰면 하나를 잃는다.

    실제로 그랬다 — `/HEAT/MAT` 을 붙인 v1.79.0 에서 처음 닿았다(§10.5).
    """
    from matcore import cards

    cards.load_builtin()
    seen: dict[tuple[str, str], str] = {}
    for renderer in export.list_renderers():
        key = (renderer.extension, renderer.suffix)
        assert key not in seen, (
            f"'{renderer.key}' 와 '{seen[key]}' 가 같은 파일 이름을 냅니다"
            f"(<카드이름>{renderer.suffix}.{renderer.extension}). "
            f"`suffix` 로 갈라 주세요 — 받는 쪽이 어느 쪽인지 알 방법이 없습니다."
        )
        seen[key] = renderer.key


class Test말없이_접은_표:
    """**표를 첫 줄 하나로 접고 말하지 않으면 `render` 가 말한다**(2026-10-07).

    모든 형식에서 표의 둘째 줄을 바꿔 보니 열둘이 온도별 탄성 · 열물성 표를 받고도 첫 줄만
    쓰면서 아무 말을 안 했다(LS-DYNA *MAT_024 · Radioss LAW36 · 확장의 Hill · Johnson-Cook ·
    온도 의존). 그물을 `render` 한 곳에 둬서 확장 · 화면에서 만든 정의까지 걸린다.
    """

    ROWS: ClassVar[list[dict[str, Any]]] = Test온도의존.ROWS

    @staticmethod
    def _target(render: Any) -> export.Renderer:
        return export.Renderer(
            key="probe", label="시험 형식", extension="txt", describe="", render=render
        )

    def test_말없이_접으면_각주를_단다(self) -> None:
        def silent(deck: export.Deck) -> export.Rendered:
            return export.Rendered(text=f"E={deck.number('elastic', 'youngs_modulus')}\n")

        rendered = export.render(
            self._target(silent), temperature_deck(elastic_rows=self.ROWS)
        )
        said = [note for note in rendered.notes if "한 값만" in note]
        assert said and "탄성계수" in said[0] and "가장 낮은 온도" in said[0], rendered.notes
        # 칸 배치처럼 각주가 필요 없는 부름은 건너뛴다.
        quiet = export.render(
            self._target(silent), temperature_deck(elastic_rows=self.ROWS), check_folds=False
        )
        assert quiet.notes == ()

    def test_이미_말했으면_더하지_않는다(self) -> None:
        def honest(deck: export.Deck) -> export.Rendered:
            return export.Rendered(
                text=f"E={deck.number('elastic', 'youngs_modulus')}\n",
                notes=(
                    "온도별 탄성 표가 있는데 이 키워드는 상수 하나입니다 — 가장 낮은 온도.",
                ),
            )

        rendered = export.render(
            self._target(honest), temperature_deck(elastic_rows=self.ROWS)
        )
        assert len(rendered.notes) == 1

    def test_표를_다_쓰거나_그_값을_안_쓰면_말하지_않는다(self) -> None:
        def table(deck: export.Deck) -> export.Rendered:
            rows = deck.rows("elastic")
            return export.Rendered(
                text="".join(
                    f"{row['youngs_modulus']} {row['poisson_ratio']}\n" for row in rows
                )
            )

        def unrelated(deck: export.Deck) -> export.Rendered:
            return export.Rendered(text="no elastic here\n")

        for render in (table, unrelated):
            rendered = export.render(
                self._target(render), temperature_deck(elastic_rows=self.ROWS)
            )
            assert rendered.notes == (), render.__name__


def visco_deck(**shift: object) -> export.Deck:
    """점탄성 카드 — 기준 23 °C, Prony 세 항. `shift` 는 점탄성 블록 값에 얹는다."""
    return export.Deck(
        name="EPDM",
        solver_id=7,
        blocks={
            "elastic": {
                "values": {"youngs_modulus": 2.4e9, "poisson_ratio": 0.35, "density": 1200.0}
            },
            "viscoelastic": {
                "values": {"reference_temperature_k": 296.15, **shift},
                "rows": [
                    {"relative_modulus": 0.3, "relaxation_time_s": 0.01},
                    {"relative_modulus": 0.2, "relaxation_time_s": 1.0},
                    {"relative_modulus": 0.1, "relaxation_time_s": 100.0},
                ],
            },
        },
    )


class TestAbaqus온도이동:
    """**점탄성 덱이 기준 온도 밖에서도 맞게** — `*TRS`(2026-10-07).

    매뉴얼의 식이 우리 것과 같다: WLF `log10 A = -C1(θ-θ0)/(C2+θ-θ0)` → C1 · C2 그대로,
    Arrhenius `ln A = (E0/R)(1/(θ-θZ) - 1/(θ0-θZ))` → E0 = Ea(θZ = 0, K). 데이터 줄은 WLF 가
    θ0 · C1 · C2, Arrhenius 가 θ0 · E0.
    """

    WLF: ClassVar[dict[str, float]] = {
        "shift_c1": 12.5,
        "shift_c2": 105.0,
        "shift_temperature_min_k": 253.15,
        "shift_temperature_max_k": 353.15,
        "shift_max_residual": 0.08,
    }

    def test_WLF_는_Prony_바로_뒤에_TRS_로_간다(self) -> None:
        rendered = export.render("abaqus_viscoelastic", visco_deck(**self.WLF))
        lines = rendered.text.splitlines()
        at = lines.index("*TRS, DEFINITION=WLF")
        assert lines[at - 1].endswith(f"{100.0:.12E}"), "Prony 마지막 행 바로 뒤가 아니다"
        assert lines[at + 1] == f"{296.15:.12E}, {12.5:.12E}, {105.0:.12E}"
        assert "Shift measured over 253.15~353.15 K" in rendered.text
        # 「기준 온도에서만 유효」 는 이제 거짓말이다 — 안 적는다.
        assert "Add *TRS for other temperatures" not in rendered.text
        said = [note for note in rendered.notes if "*TRS" in note]
        assert said and "-20.0~80.0 °C" in said[0], rendered.notes

    def test_Arrhenius_는_E0_와_모델_상수를_말한다(self) -> None:
        rendered = export.render(
            "abaqus_viscoelastic",
            visco_deck(shift_activation_energy=152000.0, shift_max_residual=0.9),
        )
        lines = rendered.text.splitlines()
        at = lines.index("*TRS, DEFINITION=ARRHENIUS")
        assert lines[at + 1] == f"{296.15:.12E}, {152000.0:.12E}"
        # *PHYSICAL CONSTANTS 는 모델 전체 설정이라 재료 덱에 안 넣고 말한다.
        assert "*PHYSICAL CONSTANTS" in rendered.text
        assert not any(line.startswith("*PHYSICAL CONSTANTS") for line in lines)
        assert any("8.31446" in note for note in rendered.notes)
        # 맞춘 이동이 관측과 0.9 자릿수 어긋났다 — 말한다.
        assert any("0.90 자릿수" in note for note in rendered.notes)

    def test_상수가_없으면_전처럼_기준_온도에서만이라고_한다(self) -> None:
        rendered = export.render("abaqus_viscoelastic", visco_deck(shift_method="manual"))
        assert "*TRS" not in rendered.text.replace("Add *TRS", "")
        assert "Add *TRS for other temperatures" in rendered.text


class TestOptiStruct온도이동:
    """**MATTVE**(2026-10-07) — 매뉴얼의 식이 우리 것과 같다(WLF
    `log10 A = -C1(T-T0)/(C2+T-T0)`, Arrhenius `ln A = (E0/R)(1/(T-Tz) - 1/(T0-Tz))`).
    자리: MID · WLF · C1 · C2 / T0, Arrhenius 는 MID · ARRHENIU · E0 · R / T0 · Tz.
    매뉴얼상 비선형 정적 · 과도 해석에서만 쓰인다."""

    def test_WLF_는_MATVE_뒤에_MATTVE_로_간다(self) -> None:
        rendered = export.render(
            "optistruct_viscoelastic", visco_deck(**TestAbaqus온도이동.WLF)
        )
        lines = rendered.text.splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith("MATTVE*"))
        assert at > max(i for i, line in enumerate(lines) if line.startswith("MATVE*"))
        assert lines[at] == (
            f"MATTVE* {7:<16d}{'WLF':<16}{12.5:<16.8E}{105.0:<16.8E}".rstrip()
        )
        assert lines[at + 1] == f"*       {296.15:<16.8E}".rstrip()
        assert "nonlinear static / nonlinear transient" in rendered.text
        assert any("MATTVE" in note and "-20.0~80.0 °C" in note for note in rendered.notes)
        assert "$ Valid at" not in rendered.text

    def test_Arrhenius_는_E0_와_R_을_같은_단위로(self) -> None:
        rendered = export.render(
            "optistruct_viscoelastic", visco_deck(shift_activation_energy=152000.0)
        )
        lines = rendered.text.splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith("MATTVE*"))
        head = f"MATTVE* {7:<16d}{'ARRHENIU':<16}"
        assert lines[at] == f"{head}{152000.0:<16.8E}{8.31446261815324:<16.8E}".rstrip()
        assert lines[at + 1] == f"*       {296.15:<16.8E}{0.0:<16.8E}".rstrip()

    def test_상수가_없으면_MATTVE_를_안_쓴다(self) -> None:
        rendered = export.render("optistruct_viscoelastic", visco_deck())
        assert "MATTVE" not in rendered.text
        assert "$ Valid at 296.15 K only" in rendered.text


class Test나머지_솔버_온도이동:
    """매뉴얼 원문으로 확인한 것만 싣는다(2026-10-07).

    ANSYS     TB,SHIFT — 시간을 A 로 **곱한다**(ξ = A·t) → A = 1/a_T. 매뉴얼의 WLF
              `log10 A = C1(T-Tr)/(C2+T-Tr)` 에 마이너스가 없어도 C1 · C2 그대로.
              Arrhenius 는 TN `ln A = (H/R)(1/Tr - 1/T)` → H/R = Ea/R.
              TBDATA 1=Tr, 2=C1, 3=C2 / 1=Tr, 2=H/R.
    Nastran   MATTVE(SOL 400) — `log10 a_T = -A1(T-T0)/(A2+T-T0)` 우리와 같다. Arrhenius 꼴
              없음.
    LS-DYNA   *MAT_076 1번 카드 TREF · A · B — Arrhenius `Φ = exp[-A(1/T - 1/TREF)]`, B = 0.
              WLF 는 매뉴얼의 두 식 부호가 어긋나 **싣지 않는다.**
    """

    ARRHENIUS: ClassVar[dict[str, float]] = {
        "shift_activation_energy": 152000.0,
        "shift_temperature_min_k": 263.15,
        "shift_temperature_max_k": 333.15,
    }

    def test_ANSYS_WLF_와_TN(self) -> None:
        wlf = export.render("ansys_viscoelastic", visco_deck(**TestAbaqus온도이동.WLF)).text
        lines = wlf.splitlines()
        at = lines.index("TB,SHIFT,MNX_MAT,1,3,WLF")
        assert lines[at + 1] == f"TBDATA,1,{296.15:.12E},{12.5:.12E},{105.0:.12E}"
        assert at > max(i for i, line in enumerate(lines) if line.startswith("TB,PRONY"))
        assert "no TB,SHIFT" not in wlf

        tn = export.render(
            "ansys_viscoelastic", visco_deck(**self.ARRHENIUS)
        ).text.splitlines()
        at = tn.index("TB,SHIFT,MNX_MAT,1,2,TN")
        assert tn[at + 1] == f"TBDATA,1,{296.15:.12E},{152000.0 / 8.31446261815324:.12E}"

    def test_Nastran_은_WLF_만_MATTVE_로(self) -> None:
        wlf = export.render(
            "nastran_viscoelastic", visco_deck(**TestAbaqus온도이동.WLF)
        ).text.splitlines()
        at = next(i for i, line in enumerate(wlf) if line.startswith("MATTVE*"))
        assert wlf[at] == f"MATTVE* {7:<16d}{'WLF':<16}{296.15:<16.8E}".rstrip()
        # 둘째 반 줄(FRACT · TDIF · TREF · NP)은 비고, 다음 논리 줄이 A1 · A2 다.
        assert wlf[at + 1] == "*"
        assert wlf[at + 2] == f"*       {12.5:<16.8E}{105.0:<16.8E}".rstrip()

        arrhenius = export.render("nastran_viscoelastic", visco_deck(**self.ARRHENIUS))
        assert "MATTVE*" not in arrhenius.text
        assert "$ Valid at 296.15 K only" in arrhenius.text
        assert any("Arrhenius 식이 없어" in note for note in arrhenius.notes)

    def test_LS_DYNA_는_Arrhenius_만_1번_카드에(self) -> None:
        rendered = export.render("dyna_viscoelastic", visco_deck(**self.ARRHENIUS))
        lines = rendered.text.splitlines()
        card = lines[lines.index("*MAT_GENERAL_VISCOELASTIC") + 2]
        # MID RO BULK PCF EF TREF A B — 10칸씩. PCF · EF 는 비운다.
        assert card[50:60].strip() == "296.15"
        assert float(card[60:70]) == pytest.approx(152000.0 / 8.31446261815324, rel=1e-6)
        assert float(card[70:80]) == 0.0, "B = 0 이어야 Arrhenius 다"
        assert card[30:50].strip() == "", "PCF · EF 는 비운다"

        wlf = export.render("dyna_viscoelastic", visco_deck(**TestAbaqus온도이동.WLF))
        assert "WLF shift not written" in wlf.text
        assert "$ Valid at 296.15 K only" in wlf.text
        first = wlf.text.splitlines()
        assert len(first[first.index("*MAT_GENERAL_VISCOELASTIC") + 2].rstrip()) <= 30
