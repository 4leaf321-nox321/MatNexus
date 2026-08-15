"""이름 생성 규칙 — 기존 앱에서 실제로 났던 사고를 재현해 막혔는지 본다."""

from __future__ import annotations

import pytest

from matcore import naming


class TestSanitize:
    def test_구분자를_값에_남기지_않는다(self) -> None:
        """값에 `_` 가 있으면 계층 경계가 무너진다."""
        assert naming.sanitize("M_DOI") == "M-DOI"

    def test_경로_금지문자를_바꾼다(self) -> None:
        """기존 앱은 생산일을 그대로 넣어 ID에 슬래시가 섞였다.

        `SampleType_8_9_10_11_12_13_14_2025/06/19` — 파일 경로로 못 쓴다.
        """
        assert naming.sanitize("2025/06/19") == "2025-06-19"
        assert "/" not in naming.sanitize("A/B:C*D?E")

    def test_공백과_연속_구분자를_정리한다(self) -> None:
        assert naming.sanitize("  Front Door  ") == "Front-Door"
        assert naming.sanitize("A___B") == "A-B"

    def test_한글을_남긴다(self) -> None:
        """Details 에 '개발A안' 같은 값이 들어온다."""
        assert naming.sanitize("개발A안") == "개발A안"

    def test_빈_값은_빈_문자열(self) -> None:
        assert naming.sanitize(None) == ""
        assert naming.sanitize("   ") == ""


class TestField:
    def test_빈_칸도_자리를_지킨다(self) -> None:
        """기존 앱의 `.filter(v => v)` 가 만든 사고를 막는 지점이다."""
        assert naming.field("") == naming.PLACEHOLDER

    def test_칸_수가_값에_따라_변하지_않는다(self) -> None:
        가득 = naming.join_fields("SECC", "MDOI", "1.0")
        비었음 = naming.join_fields("SECC", "", "1.0")
        assert 가득.count(naming.FIELD_SEP) == 비었음.count(naming.FIELD_SEP)
        assert 비었음 == "SECC_-_1.0"


class TestFormatNumber:
    def test_부동소수_흔들림을_없앤다(self) -> None:
        """SI(m)로 저장한 0.45mm 를 mm로 되돌리면 0.44999999999999996 이 된다.

        그대로 이름에 넣으면 같은 재료가 경로에 따라 다른 이름을 받는다.
        """
        assert naming.format_number(0.45 * 1000 / 1000) == "0.45"
        assert naming.format_number(0.00045 * 1000) == "0.45"

    def test_정수여도_소수점을_남긴다(self) -> None:
        assert naming.format_number(1) == "1.0"
        assert naming.format_number(1.0) == "1.0"

    def test_불필요한_0을_지운다(self) -> None:
        assert naming.format_number(1.20) == "1.2"

    @pytest.mark.parametrize("bad", ["", None, "abc", float("nan"), float("inf")])
    def test_숫자가_아니면_자리표시자(self, bad: object) -> None:
        assert naming.format_number(bad) == naming.PLACEHOLDER  # type: ignore[arg-type]


class TestLayers:
    def test_계층_체인(self) -> None:
        material = naming.material_name(grade="SECC", details="MDOI", thickness_mm=1.0)
        sample = naming.sample_name(material=material, seq_no=2)
        specimen = naming.specimen_name(sample=sample, orientation="MD", seq_no=3)
        run = naming.test_run_name(specimen=specimen, type_abbr="TEN", seq_no=1)

        assert material == "SECC_MDOI_1.0"
        assert sample == "SECC_MDOI_1.0__02"
        assert specimen == "SECC_MDOI_1.0__02__MD_03"
        assert run == "SECC_MDOI_1.0__02__MD_03__TEN_01"

    def test_계층_경계가_값에_먹히지_않는다(self) -> None:
        """값에서 `_` 를 없애므로 `__` 는 언제나 계층 경계다."""
        material = naming.material_name(grade="A_B", details="C__D", thickness_mm=1)
        assert naming.LAYER_SEP not in material

    def test_같은_입력이면_같은_이름(self) -> None:
        """기존 앱은 타임스탬프+난수 때문에 매번 달랐다 — 재등록이 멱등하지 않았다."""
        kwargs = {"specimen": "S", "type_abbr": "TEN", "seq_no": 1}
        assert naming.test_run_name(**kwargs) == naming.test_run_name(**kwargs)  # type: ignore[arg-type]

    def test_두께를_나중에_채워도_칸이_늘지_않는다(self) -> None:
        """기존 앱에서는 `SECC_MDOI_MD` → `SECC_MDOI_1.0_MD` 로 칸이 늘었다."""
        before = naming.material_name(grade="SECC", details="MDOI", thickness_mm=None)
        after = naming.material_name(grade="SECC", details="MDOI", thickness_mm=1.0)
        assert before == "SECC_MDOI_-"
        assert before.count(naming.FIELD_SEP) == after.count(naming.FIELD_SEP)
