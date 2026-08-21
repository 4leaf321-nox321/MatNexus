"""JSON 리더 — **실파일 282개 전수 조사에서 정해진 것들.**

기존 앱(`MaterialAppVer2`)의 `.mtet`·`.mdss`·`.mdft` 가 JSON 이라 그동안 못
읽었다. 그 파일들을 전부 돌려 보고 나온 사실이 여기 시험의 근거다.

    파일 282개  →  데이터가 든 249개 전부 읽힘, 못 읽은 것 0
                   나머지 33개는 Raw Data 가 아예 없는 껍데기 (옳게 거절)
    서로 다른 열 이름 17개
    Raw Data 모양 두 가지 — 블록 중첩 131개, 평면 124개

픽스처는 그 두 모양을 손으로 줄여 만든 것이다. **외부 디렉터리에 기대지 않는다**
— CI 에는 그 파일들이 없고, 시험이 환경에 따라 갈리면 시험이 아니다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matcore.readers import ReadError, read, sniff

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TENSILE = FIXTURES / "legacy_tensile.mtet"
DMA = FIXTURES / "legacy_dma.mdft"


class Test평면:
    """`.mtet` — Raw Data 안이 바로 열이다. 실측 124개."""

    def test_표_하나로_읽는다(self) -> None:
        structure = sniff(TENSILE.read_bytes())
        assert len(structure.tables) == 1
        table = structure.tables[0]
        assert table.name == "Tensile Test Raw Data"
        assert table.column_count == 4
        assert table.row_count == 5

    def test_열_이름을_키_순서대로_지킨다(self) -> None:
        """순서가 바뀌면 헤더와 값이 어긋난다. JSON 객체는 순서를 보존한다."""
        table = sniff(TENSILE.read_bytes()).tables[0]
        assert table.header == (
            "#",
            "Standard extensometer (mm)",
            "Standard load cell (N)",
            "Specimen width (mm)",
        )
        assert table.rows[0] == ("1", "0.0000", "19.4642", "12.473")

    def test_표_밖의_값만_메타로_간다(self) -> None:
        meta = dict(sniff(TENSILE.read_bytes()).meta)
        assert meta["Instrument name"] == "Zwick Z100"
        assert meta["Force maximum (MPa)"] == "282.128"
        # 표 안의 열 이름이 메타로 새면 안 된다.
        assert "Standard load cell (N)" not in meta


class Test블록중첩:
    """`.mdft` — Raw Data 안에 블록이 한 겹 더 있다. 실측 131개."""

    def test_블록마다_표가_하나씩(self) -> None:
        tables = sniff(DMA.read_bytes()).tables
        assert len(tables) == 2
        assert [t.name for t in tables] == [
            "Temperature Sweep (Multifrequency) - 2",
            "Temperature Sweep (Multifrequency) - 3",
        ]

    def test_블록을_섞지_않는다(self) -> None:
        """**섞으면 온도가 다른 두 스윕이 한 곡선이 된다.** 조용히 틀린 그림이다."""
        first, second = sniff(DMA.read_bytes()).tables
        temperature = first.header.index("Temperature (°C)")
        assert {row[temperature] for row in first.rows} == {"-40.00", "-40.05", "-40.13"}
        assert {row[temperature] for row in second.rows} == {"-30.00", "-30.05", "-30.13"}


class Test단위를열이름에서_뽑지않는다:
    """`Standard extensometer (mm)` 의 `(mm)` 을 단위로 떼고 싶어진다. **안 한다.**

    실측: 서로 다른 열 이름 17개 중 `Tan(delta)` 가 596번 나온다. 괄호를 단위로
    떼면 `Tan` 이라는 열에 `delta` 라는 단위가 붙는다. 게다가 같은 열이 파일에
    따라 `(mm)` 을 달고도 안 달고도 온다(55회 대 33회) — 떼도 일관돼지지 않는다.

    단위는 프로파일이 채널마다 선언한다. 그게 프로파일이 있는 이유다.
    """

    def test_열_이름을_그대로_둔다(self) -> None:
        table = sniff(DMA.read_bytes()).tables[0]
        assert "Tan(delta)" in table.header
        assert "Storage modulus (MPa)" in table.header

    def test_단위_줄은_비어_있다(self) -> None:
        """`table.units` 가 비면 프로파일의 채널 선언이 쓰인다."""
        assert sniff(DMA.read_bytes()).tables[0].units == ()


class Test표가아닌것:
    def test_길이가_다르면_표가_아니다(self) -> None:
        """**짧은 쪽에 맞춰 자르지 않는다.** 자르면 열마다 다른 점을 가리키는
        곡선이 조용히 만들어진다."""
        ragged = b'{"raw": {"a": [1, 2, 3], "b": [4, 5]}}'
        with pytest.raises(ReadError, match="표를 찾지 못했습니다"):
            sniff(ragged)

    def test_한_행짜리는_표가_아니다(self) -> None:
        """그것까지 표로 만들면 메타 딕셔너리가 통째로 표가 된다."""
        with pytest.raises(ReadError, match="표를 찾지 못했습니다"):
            sniff(b'{"raw": {"a": [1], "b": [2]}}')

    def test_데이터가_없으면_이유를_말한다(self) -> None:
        """실측 282개 중 33개가 이것이다 — Raw Data 가 아예 없는 껍데기.
        **'실패' 만 알려 주면 사람은 파일이 깨진 줄 안다.**"""
        empty = b'{"tensile-test": {"Test Condition": {"Specimen Number": "1"}}}'
        with pytest.raises(ReadError, match="열 지향"):
            sniff(empty)


class Test행지향:
    """실측 파일에는 없었지만 JSON 의 다른 절반이다. 지금 막아 두면 다음 장비에서
    또 리더를 만들게 된다."""

    RECORDS = b'[{"strain": 0.001, "stress": 200}, {"strain": 0.002, "stress": 400}]'

    def test_같은_키를_가진_객체_배열을_읽는다(self) -> None:
        table = sniff(self.RECORDS).tables[0]
        assert table.header == ("strain", "stress")
        assert table.rows == (("0.001", "200"), ("0.002", "400"))

    def test_키가_다르면_표가_아니다(self) -> None:
        with pytest.raises(ReadError, match="표를 찾지 못했습니다"):
            sniff(b'[{"strain": 1}, {"stress": 2}]')


class Test갈림길:
    def test_구분자_설정은_JSON_에_안_쓰인다고_말한다(self) -> None:
        """말없이 무시하면 사람은 설정이 먹은 줄 안다."""
        from matcore.readers import ReadOptions

        structure = read(TENSILE.read_bytes(), ReadOptions(delimiter=","))
        assert any("구분자" in warning for warning in structure.warnings)

    def test_구분자가_없다고_적는다(self) -> None:
        assert sniff(TENSILE.read_bytes()).delimiter == ""
