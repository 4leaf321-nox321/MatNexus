"""솔버 카드 — **덱에 그대로 들어가는 텍스트다.**

이 파일이 지키는 것은 셋이다.

1. **칸과 순서.** OpenRadioss 는 고정 20칸이고 Abaqus 는 응력이 먼저다. 하나
   어긋나면 솔버는 오류 없이 다른 재료로 계산한다 — 그게 가장 나쁜 실패다.
2. **없는 값을 만들지 않는다.** 푸아송비가 없으면 0.3 을 넣지 않고 거부한다.
3. **조용히 고치지 않는다.** 응력이 떨어지는 표는 눕혀서 내보내지 않는다.
"""

from __future__ import annotations

import json

import pytest

from matcore import export

CARD = export.Card(
    name="DP600_MD",
    solver_id=42,
    youngs_modulus=200e9,
    poisson_ratio=0.3,
    density=7850.0,
    points=((0.0, 250e6), (0.01, 300e6), (0.05, 340e6)),
    provenance=("시편 3개 · SECC_MDOI_1.0",),
)


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
        assert len(rows) == len(CARD.points)
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

    def test_중립_JSON_은_단위를_필드_이름에_박는다(self) -> None:
        body = json.loads(export.render("json", CARD).text)
        assert body["elastic"]["youngs_modulus_pa"] == 200e9
        assert body["plasticity"]["points"][0]["true_stress_pa"] == 250e6

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
        card = export.Card(name="X", solver_id=1, youngs_modulus=200e9, points=CARD.points)
        with pytest.raises(export.ExportError, match="푸아송비"):
            export.render("abaqus", card)

    def test_밀도가_없으면_openradioss_는_거부한다(self) -> None:
        # LAW36 은 RHO_I 가 자리 있는 필드다. 비울 수 없다.
        card = export.Card(
            name="X",
            solver_id=1,
            youngs_modulus=200e9,
            poisson_ratio=0.3,
            points=CARD.points,
        )
        with pytest.raises(export.ExportError, match="밀도"):
            export.render("openradioss", card)

    def test_밀도가_없으면_abaqus_는_빼고_그_사실을_적는다(self) -> None:
        """`*DENSITY` 는 Abaqus 에서 선택이다. 빼되 **왜 뺐는지 덱에 적는다** —
        동적 해석을 돌리려던 사람이 덱만 보고 알 수 있어야 한다."""
        card = export.Card(
            name="X",
            solver_id=1,
            youngs_modulus=200e9,
            poisson_ratio=0.3,
            points=CARD.points,
        )
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
        card = export.Card(
            name="X",
            solver_id=1,
            youngs_modulus=200e9,
            poisson_ratio=0.3,
            points=((0.0, 10e6), (0.0, 150e6), (0.0, 250e6), (0.01, 300e6)),
        )
        points, notes = export.prepare(card.points)
        assert points[0] == (0.0, 250e6)
        assert len(points) == 2
        assert any("항복점" in note for note in notes)

    def test_첫_점이_0_이_아니면_거부한다(self) -> None:
        with pytest.raises(export.ExportError, match="0 이어야"):
            export.prepare(((0.002, 250e6), (0.01, 300e6)))

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
        도는데 재료가 안 들어간 채로 돈다."""
        for key, target in export.FORMATS.items():
            text = export.render(key, CARD).text
            for word in target.keywords:
                assert word in text

    def test_모르는_형식은_있는_것을_알려_준다(self) -> None:
        with pytest.raises(export.ExportError, match="있는 것"):
            export.render("nastran", CARD)
