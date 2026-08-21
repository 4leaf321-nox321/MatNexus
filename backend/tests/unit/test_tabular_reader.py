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


class TestJson은Json리더로간다:
    """기존 앱의 `.mtet`·`.mdss`·`.mdft` 는 JSON 인데, 배열 안 숫자 줄이 연달아
    나와 "표 93개" 로 잡혔다. **고유 파일 131개 중 59개**가 이렇게 '성공' 했다.

    처음에는 **거절**했다. 조용히 틀린 성공보다 낫기 때문이다. 그런데 거절만
    하면 그 파일들은 영영 안 들어온다 — 그래서 `readers/json_tables.py` 를
    만들고, `read()` 가 내용을 보고 갈라 준다.

    여기 남은 시험은 **갈림길이 제대로 도는지**를 지킨다. 이 파일이 다시 구분자
    리더로 흘러가면 그때가 '표 93개' 로 돌아가는 날이다.
    """

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

    def test_숫자_줄을_표로_세지_않는다(self) -> None:
        """**'표 93개' 가 이 시험이 막는 것이다.** 배열 안의 숫자 줄은 표가 아니다."""
        structure = sniff(encode(self.JSON))
        assert len(structure.tables) == 1

    def test_열_이름을_키에서_얻는다(self) -> None:
        """구분자 리더는 이 파일에서 열 이름을 하나도 못 찾았다. JSON 은 키가
        곧 열 이름이라 찾을 것도 없다."""
        table = sniff(encode(self.JSON)).tables[0]
        assert table.header == ("Standard travel",)
        assert table.name == "Tensile Test Raw Data"
        assert table.row_count == 4
        # **원문 문자열 그대로.** 숫자로 바꾸는 것은 매핑을 정한 뒤의 일이다.
        assert table.rows[0] == ("1.46484e-07",)

    def test_표_안의_열이_메타로_새지_않는다(self) -> None:
        """새면 메타가 수백 줄이 되고 사람이 미리보기에서 아무것도 못 찾는다."""
        meta = dict(sniff(encode(self.JSON)).meta)
        assert meta == {"Specimen Number": "1"}

    def test_구분자_텍스트의_마커를_JSON_으로_보지_않는다(self) -> None:
        """**실측으로 걸렸다.** `[` 로 시작하면 JSON 이라고 봤더니 `[step]` 마커로
        시작하는 파일이 "1행 2칸: Expecting value" 로 죽었다 — 읽히던 것이 안
        읽혔다. `{` 는 확실하지만 `[` 는 실제로 파싱될 때만 JSON 이다."""
        structure = sniff(
            encode(
                """
[step]
Angular frequency,Storage modulus
rad/s,MPa
6.28,201242
6.29,201243
"""
            )
        )
        assert len(structure.tables) == 1
        assert structure.tables[0].header == ("Angular frequency", "Storage modulus")

    def test_깨진_JSON_은_조용히_넘어가지_않는다(self) -> None:
        """잘린 JSON 을 텍스트 리더로 흘려보내면 그게 '표 93개' 다."""
        with pytest.raises(ReadError, match="파싱에 실패"):
            sniff(encode(self.JSON[: len(self.JSON) // 2]))


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


class Test메타와표가섞여있을때:
    """**표가 삼키지 않은 줄이 전부 메타다.**

    처음에는 '첫 표 앞' 까지만 메타로 봤다. 그래서 둘을 놓쳤다.

      - 표 **뒤**의 요약부. 실측한 `.tra` 는 요약이 앞에 있지만 뒤에 붙이는 장비도
        있다. 그러면 `Force maximum,3466.4` 가 통째로 사라진다
      - 표 **사이**의 키-값

    그리고 '앞까지' 로 자르면 헤더 줄과 단위 줄이 메타에 섞여 들어왔다 — 이건
    특수한 파일이 아니라 **모든 파일에서 나던 일**이다.
    """

    def test_헤더와_단위_줄은_메타가_아니다(self) -> None:
        structure = sniff(
            encode(
                """
Operator,박용진
Instrument,DMA850
Angular frequency,Storage modulus
rad/s,MPa
6.28,201242
6.29,201243
"""
            )
        )
        assert list(structure.meta) == [("Operator", "박용진"), ("Instrument", "DMA850")]

    def test_표_뒤의_키_값도_읽는다(self) -> None:
        structure = sniff(
            encode(
                """
Operator,박용진
Angular frequency,Storage modulus
rad/s,MPa
6.28,201242
6.29,201243
Force maximum,3466.4
Specimen thickness,0.986
"""
            )
        )
        meta = dict(structure.meta)
        assert meta["Force maximum"] == "3466.4"
        assert meta["Specimen thickness"] == "0.986"

    def test_표_사이의_키_값도_읽는다(self) -> None:
        structure = sniff(
            encode(
                """
Operator,박용진
Angular frequency,Storage modulus
rad/s,MPa
6.28,201242
6.29,201243
Test note,두 번째 구간
Temperature,Loss modulus
degC,MPa
25.0,1577
25.1,1578
"""
            )
        )
        assert len(structure.tables) == 2
        assert dict(structure.meta)["Test note"] == "두 번째 구간"

    def test_표_이름과_마커는_메타가_아니다(self) -> None:
        """`[step]` 과 표 이름은 표의 것이다. 메타로 들어가면 '보관될 메타' 에
        `step = ` 같은 것이 쌓인다."""
        structure = sniff(
            encode(
                """
Operator,박용진

[step]
Sweep - 1
Angular frequency,Storage modulus
rad/s,MPa
6.28,201242
6.29,201243
"""
            )
        )
        assert structure.tables[0].name == "Sweep - 1"
        assert list(structure.meta) == [("Operator", "박용진")]


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
