"""층 1 범용 리더 — **실파일 전수 조사에서 드러난 것들.**

픽스처 4개로만 증명했던 것을 `002_Material` 의 고유 파일 131개에 돌려 보고 나온
결함들이다. 셋 다 성격이 같다 — **틀렸는데 성공했다.** 실패는 사람이 보지만
'조용히 잘못된 성공'은 아무도 못 본다.
"""

from __future__ import annotations

import pytest

from matcore.readers import ReadError, sniff


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
