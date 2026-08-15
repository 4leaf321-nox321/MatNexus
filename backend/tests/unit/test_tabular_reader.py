"""층 1 범용 리더 — **실파일 전수 조사에서 드러난 것들.**

픽스처 4개로만 증명했던 것을 `002_Material` 의 고유 파일 131개에 돌려 보고 나온
결함들이다. 셋 다 성격이 같다 — **틀렸는데 성공했다.** 실패는 사람이 보지만
'조용히 잘못된 성공'은 아무도 못 본다.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from matcore.parsers import ParseError
from matcore.readers import ReadError, ReadOptions, read, sniff
from matcore.readers import profile as profiles


def encode(text: str) -> bytes:
    return text.strip("\n").encode("utf-8")


class TestJson을표로착각하지않는다:
    """기존 앱의 `.mtet`·`.mdss`·`.mdft` 는 JSON 인데, 배열 안 숫자 줄이 연달아
    나와 "표 93개" 로 잡혔다. **고유 파일 131개 중 59개**가 이렇게 '성공' 했다."""

    JSON = """
{
  "tensile-test": {
    "Test Condition": {
      "Specimen Number": "1"
    },
    "Tensile Test Raw Data": {
      "Standard travel": [
        1.46484e-007,
        0.0099015,
        0.0199020,
        0.0299030
      ]
    }
  }
}
"""

    def test_열_이름이_없으면_표가_아니다(self) -> None:
        with pytest.raises(ReadError) as caught:
            sniff(encode(self.JSON))
        assert "열 이름이 하나도 없습니다" in str(caught.value)

    def test_왜_거절했는지_말한다(self) -> None:
        """'실패' 만 알려 주면 사람은 파일이 깨진 줄 안다. JSON 일 수 있다는
        말이 있어야 다음 행동이 정해진다."""
        with pytest.raises(ReadError, match="JSON"):
            sniff(encode(self.JSON))


class Test엑셀패딩:
    """엑셀이 내보낸 CSV 는 빈 칸으로 줄 끝을 채운다. 실측 파일은 67칸 중 4칸만
    채워져 있었다.

    빈 칸을 '단위다움'에 세면 헤더 줄의 점수가 63/67 = 0.94 가 되어 **헤더가
    단위 줄로 오인되고, 그 위의 빈 줄이 헤더가 된다** — 열 이름이 통째로 사라진다.
    """

    PADDED = """
,,,,,,
,,,,,,
,strain,stress,fine strain,fine stress,,
,2.93E-09,1.58266399,0,0,,
6.73E-03,1.98E-04,39.585821,8.41E-02,2.79E+02,,
,4.20E-04,74.34044007,1.68E-01,3.29E+02,,
"""

    def test_열_이름을_잃지_않는다(self) -> None:
        structure = sniff(encode(self.PADDED))
        assert len(structure.tables) == 1
        header = structure.tables[0].header
        assert header[1:5] == ("strain", "stress", "fine strain", "fine stress")

    def test_빈_칸뿐인_줄은_단위_줄이_아니다(self) -> None:
        structure = sniff(encode(self.PADDED))
        assert structure.tables[0].units == ()


class Test칸수가어긋날때:
    """실측(`Example.csv` 구버전): 헤더는 8칸인데 데이터는 7칸이고, **빠진 것이
    마지막이 아니라 6번째**(`Tan(delta)`) 였다.

    앞에서부터 맞춰 붙이면 손실탄성률 데이터에 `Storage modulus` 라는 이름이
    붙는다. **틀린 이름은 이름이 없는 것보다 나쁘다** — 그럴듯해 보여서 아무도
    못 잡는다.
    """

    # 헤더 8칸 · 단위 8칸 · 데이터 7칸. `Tan(delta)` 열이 데이터에서 통째로 빠졌다.
    SHIFTED = (
        "Angular frequency,Step time,Temperature,Oscillation strain,"
        "Oscillation stress,Tan(delta),Storage modulus,Loss modulus\n"
        "rad/s,s,°C,%,MPa,,MPa,MPa\n"
        "6.28319,11.6220,25.00,9.99711e-4,2.01190,201242,1577.45\n"
        "6.28319,24.6220,25.05,2.00024e-3,4.05067,202502,1651.03\n"
    )

    def test_이름을_지어내지_않고_거절한다(self) -> None:
        with pytest.raises(ReadError) as caught:
            sniff(encode(self.SHIFTED))
        assert "8칸이 데이터 7칸" in str(caught.value)

    def test_오류에_진짜_헤더를_남긴다(self) -> None:
        """단위 줄이 아니라 **헤더**가 보여야 사람이 `Tan(delta)` 가 빠진 것을
        알아본다. 단위 줄을 보여 주면 고칠 근거가 안 된다."""
        with pytest.raises(ReadError) as caught:
            sniff(encode(self.SHIFTED))
        message = str(caught.value)
        assert "Angular frequency" in message
        assert "Tan(delta)" in message


class Test헤더가여러줄:
    """헤더가 2~3줄인 파일. **자동으로는 못 알아차린다** — 그래서 사람이 정한다.

    아래 둘은 기계 눈에 완전히 같다.

        ,,Tensile,Tensile      ← 그룹 머리. 버려도 되는 경우가 많다
        Time,Force,Strain      ← 진짜 이름

        Angular,Storage        ← 이름의 앞부분. 버리면 안 된다
        frequency,modulus      ← 이름의 뒷부분
    """

    SPLIT = """
Angular,Storage,Loss
frequency,modulus,modulus
rad/s,MPa,MPa
6.28319,201242,1577.45
6.29319,201243,1578.02
"""

    def test_기본은_한_줄_아랫줄만_쓴다(self) -> None:
        """실측으로 확인한 지금까지의 동작. **두 열의 이름이 같아진다** — 이름으로
        하는 매핑이 성립하지 않는 상태다."""
        table = sniff(encode(self.SPLIT)).tables[0]
        assert table.header == ("frequency", "modulus", "modulus")

    def test_줄_수를_알려_주면_이어_붙인다(self) -> None:
        table = read(encode(self.SPLIT), ReadOptions(header_rows=2)).tables[0]
        assert table.header == ("Angular frequency", "Storage modulus", "Loss modulus")
        assert table.units == ("rad/s", "MPa", "MPa")

    def test_그룹_머리도_같은_방식으로_붙는다(self) -> None:
        """빈 칸은 건너뛰므로 그룹 머리가 있는 열만 접두어가 붙는다."""
        table = read(
            encode(
                """
,,Tensile,Tensile
Time,Force,Strain,Stress
s,N,%,MPa
0.0,0.0,0.0,0.0
0.1,120.5,0.02,241.0
"""
            ),
            ReadOptions(header_rows=2),
        ).tables[0]
        assert table.header == ("Time", "Force", "Tensile Strain", "Tensile Stress")

    def test_표_이름은_헤더_위로_밀린다(self) -> None:
        table = read(
            encode(
                """
[step]
Sweep - 1
Angular,Storage
frequency,modulus
rad/s,MPa
6.28319,201242
6.29319,201243
"""
            ),
            ReadOptions(header_rows=2),
        ).tables[0]
        assert table.name == "Sweep - 1"
        assert table.header == ("Angular frequency", "Storage modulus")


class Test단위를모르면멈춘다:
    """**매핑한 열의 단위를 모르면 원값이 SI 인 척 저장된다.**

    201242 MPa 가 201242 Pa 가 되어 10⁶ 배 틀리는데, 숫자는 멀쩡해 보이고 뜻만
    바뀌므로 화면 어디에도 티가 나지 않는다. 시험종류 편집에서 단위를 잠그는 것과
    같은 이유로 여기서 멈춘다.
    """

    RULE: ClassVar[dict[str, Any]] = {
        "match": {"extensions": [".csv"]},
        "columns": {"Storage modulus": {"channel": "e_storage"}},
    }
    NO_UNITS = """
Angular frequency,Storage modulus
6.28319,201242
6.29319,201243
"""

    def test_단위_줄이_없으면_거절한다(self) -> None:
        with pytest.raises(ParseError, match="단위"):
            profiles.apply(self.RULE, encode(self.NO_UNITS))

    def test_어느_열인지_말한다(self) -> None:
        with pytest.raises(ParseError, match="Storage modulus"):
            profiles.apply(self.RULE, encode(self.NO_UNITS))

    def test_프로파일이_단위를_적으면_통과한다(self) -> None:
        """빠져나갈 길이 있어야 한다 — 단위를 안 적어 주는 장비가 실재한다."""
        rule = {
            **self.RULE,
            "columns": {"Storage modulus": {"channel": "e_storage", "unit": "MPa"}},
        }
        parsed = profiles.apply(rule, encode(self.NO_UNITS))
        channel = next(c for c in parsed.all_curves[0].channels if c.key == "e_storage")
        assert channel.si_unit == "Pa"
        assert channel.values[0] == pytest.approx(2.01242e11)

    def test_매핑하지_않은_열은_막지_않는다(self) -> None:
        """정의된 채널이 아니라 계산에 안 쓰인다. 원값으로 두고 넘어간다 —
        사람이 나중에 매핑할 수도 있다."""
        parsed = profiles.apply(
            {"match": {"extensions": [".csv"]}, "columns": {}},
            encode(self.NO_UNITS),
        )
        channel = parsed.all_curves[0].channels[0]
        assert channel.si_unit == "?"
        assert channel.values[0] == pytest.approx(6.28319)


class Test회귀방지:
    def test_단위_줄에_빈_칸이_있어도_단위_줄이다(self) -> None:
        """DMA 변형률 스윕은 `Tan(delta)` 열의 단위가 비어 있다. 빈 칸을 분모에서
        뺀 뒤에도 이 판정이 유지돼야 한다 — 아니면 단위 줄이 헤더가 된다."""
        structure = sniff(
            encode(
                """
Angular frequency,Temperature,Tan(delta)
rad/s,°C,
6.28319,25.00,
6.28319,25.05,
"""
            )
        )
        table = structure.tables[0]
        assert table.header == ("Angular frequency", "Temperature", "Tan(delta)")
        assert table.units == ("rad/s", "°C", "")

    def test_표_이름과_메타는_그대로_읽는다(self) -> None:
        structure = sniff(
            encode(
                """
Operator,박용진
Length,50.0 mm

[step]
Strain Sweep - 2
Angular frequency,Temperature
rad/s,°C
6.28319,25.00
6.28319,25.05
"""
            )
        )
        assert dict(structure.meta)["Operator"] == "박용진"
        assert structure.tables[0].name == "Strain Sweep - 2"
