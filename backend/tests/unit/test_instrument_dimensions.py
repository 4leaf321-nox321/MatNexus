"""장비 파일의 항목 이름을 규격의 칸에 잇는다.

**파일 항목 이름이 곧 규격 기호다.** Zwick 은 두께를 `a0`, 폭을 `b0`, 직경을
`d0` 로 적는다 — 규격서 도면의 글자를 그대로 쓴 것이다.

전에는 두께·폭·게이지 셋만 아는 표가 코드에 박혀 있었다. 그래서 환봉 파일이 준
직경은 **갈 곳이 없었다** — 파일에 값이 있는데도 사람이 자를 대고 다시 쟀다.
이제 규격의 칸이 기호를 갖고 있으므로, 규격에 칸을 더하고 글자를 적어 두면
파일 채우기가 저절로 따라온다.
"""

from __future__ import annotations

import pytest

from app.modules.vocabulary.services import Field
from app.shared import curvedata


def field(key: str, label: str, symbol: str | None = None, kind: str = "number") -> Field:
    return Field(
        key=key,
        label=label,
        dimension="length",
        si_unit="m",
        is_required=False,
        help=None,
        inherited=False,
        kind=kind,
        symbol=symbol,
    )


class TestBySymbol:
    def test_기호로_찾는다(self) -> None:
        """**이 파일의 이유.** 이름이 안 맞아도 도면의 글자로 이어진다."""
        found = curvedata.instrument_dimensions(
            {"specimen_diameter_d0": "12.473", "specimen_diameter_d0_unit": "mm"},
            [field("diameter", "직경", symbol="d0")],
        )
        assert found["diameter"] == pytest.approx(0.012473)

    def test_글자만_적힌_항목도_받는다(self) -> None:
        """항목 이름이 `d0` 하나인 파일이 있다."""
        found = curvedata.instrument_dimensions(
            {"d0": "12.5 mm"}, [field("diameter", "직경", symbol="d0")]
        )
        assert found["diameter"] == pytest.approx(0.0125)

    def test_기호가_없으면_이름으로만_찾는다(self) -> None:
        found = curvedata.instrument_dimensions(
            {"specimen_free_length": "35 mm"}, [field("free_length", "자유 길이")]
        )
        assert found["free_length"] == pytest.approx(0.035)

    def test_규격에_없는_칸은_안_채운다(self) -> None:
        """**파일에 있다고 다 넣지 않는다.** 그 규격에 없는 값이면 갈 자리가 없다."""
        found = curvedata.instrument_dimensions(
            {"specimen_diameter_d0": "12.5 mm"}, [field("width", "폭", symbol="b0")]
        )
        assert found == {}

    def test_숫자가_아닌_칸은_건너뛴다(self) -> None:
        """판(문자)·모드(선택)는 치수가 아니다."""
        found = curvedata.instrument_dimensions(
            {"specimen_edition": "D638-22"}, [field("edition", "판", kind="text")]
        )
        assert found == {}


class TestLegacy:
    """**이미 저장된 파일이 있다.** 옛 이름이 계속 통해야 한다."""

    def test_칸을_안_주면_옛_셋을_찾는다(self) -> None:
        found = curvedata.instrument_dimensions(
            {"specimen_thickness_a0": "0.986", "specimen_thickness_a0_unit": "mm"}
        )
        assert found["thickness"] == pytest.approx(0.000986)

    def test_옛_이름은_칸을_줘도_통한다(self) -> None:
        found = curvedata.instrument_dimensions(
            {"specimen_width_b0": "12.473 mm"}, [field("width", "폭")]
        )
        assert found["width"] == pytest.approx(0.012473)


class TestRefusals:
    def test_단위를_모르면_포기한다(self) -> None:
        """**mm 라고 가정하면 m 로 적힌 파일에서 1000배 틀린 시편이 생긴다.**"""
        found = curvedata.instrument_dimensions(
            {"specimen_diameter_d0": "12.5"}, [field("diameter", "직경", symbol="d0")]
        )
        assert found == {}

    def test_시편이_10m_일_리는_없다(self) -> None:
        """단위를 잘못 읽었다는 신호다."""
        found = curvedata.instrument_dimensions(
            {"d0": "12500 mm"}, [field("diameter", "직경", symbol="d0")]
        )
        assert found == {}

    def test_길이가_아닌_단위를_포기한다(self) -> None:
        """**실측으로 걸린 것과 같은 구멍이다**(2026-08-27, 전체 흐름 점검).

        `kg` 은 아는 단위라 환산이 무사히 끝나고, 그 `1.2` 가 「10m 일 리 없다」
        검사까지 통과해 **두께 1.2 m 짜리 시편**이 된다. 프로파일은 열마다
        단위를 지정할 수 있으므로 한 글자 오타면 나는 일이다.
        """
        found = curvedata.instrument_dimensions(
            {"a0": "1.2 kg"}, [field("thickness", "두께", symbol="a0")]
        )
        assert found == {}

    def test_단위_힌트가_길이가_아니어도_포기한다(self) -> None:
        """숫자만 적힌 칸은 힌트를 쓴다 — 그 힌트도 같은 검사를 받아야 한다."""
        found = curvedata.instrument_dimensions(
            {"a0": "1.2", "a0_unit": "kg"}, [field("thickness", "두께", symbol="a0")]
        )
        assert found == {}
