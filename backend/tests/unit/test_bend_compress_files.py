"""굽힘 · 압축 장비 파일 — Zwick testXpert `.tra` 와 Instron Bluehill CSV(2026-10-16).

**실파일 없이 적은 형식이다.** 장비 소프트웨어가 쓰는 이름(영문 · 독일어)과 꼴로 만든 합성
파일이다 — 실파일이 오면 여기에 더해 둔다. 확인하는 것:

    Zwick      한 파서를 인장 · 굽힘 · 압축이 함께 쓴다. 파일 안의 이름으로 종류를 가른다
               (`classify`) — **한 종류만 걸릴 때만** 고른다
    Instron    단위 줄이 괄호에 싸여 온다(`(mm)` · `(sec)`). 안 벗기면 mm 가 m 인 척 저장된다
    프로파일   `Flexure …` · `Compressive …` 이름이 지문이다. 서로를 잡지 않는다
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.modules.tests.legacy_profiles import (
    INSTRON_COMPRESSION_DEFINITION,
    INSTRON_FLEXURAL_DEFINITION,
    TA_DMA850_DEFINITION,
)
from matcore import units
from matcore.parsers import Channel, ParsedTest, zwick_tra
from matcore.readers import profile as profiles
from matcore.readers import sniff

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

ZWICK_FLEXURAL = (
    '"Flexural modulus",3012.5,"MPa"\n'
    '"Flexural strength",92.1,"MPa"\n'
    '"Specimen thickness a0",4.02,"mm"\n'
    '"Specimen width b0",10.01,"mm"\n'
    '"Standard force","Standard travel","Deflection","Test time"\n'
    '"N","mm","mm","s"\n'
    "0.0,0.0,0.0,0.0\n"
    "10.5,0.05,0.04,0.5\n"
    "21.0,0.10,0.08,1.0\n"
    "31.4,0.15,0.12,1.5\n"
)

ZWICK_COMPRESSION_DE = (
    '"Druckfestigkeit";1,25;"MPa"\n'
    '"Probenhöhe h0";12,5;"mm"\n'
    '"Standardkraft";"Standardweg";"Dehnung"\n'
    '"kN";"mm";"%"\n'
    "0,0;0,0;0,0\n"
    "0,12;0,25;2,0\n"
    "0,25;0,50;4,0\n"
)

INSTRON_PLAIN = (
    "Time,Extension,Load\n(sec),(mm),(N)\n0.0,0.0,0.0\n0.1,0.01,5.0\n0.2,0.02,10.0\n"
)

INSTRON_FLEXURE = (
    '"Time","Flexure extension","Flexure load","Deflection"\n'
    '"(s)","(mm)","(N)","(mm)"\n'
    '"0.00","0.000","0.00","0.000"\n'
    '"0.10","0.010","4.20","0.008"\n'
    '"0.20","0.020","8.40","0.016"\n'
)

INSTRON_COMPRESSION_INLINE = (
    "Time (s),Compressive extension (mm),Compressive load (kN)\n"
    "0.0,0.0,0.0\n"
    "0.5,0.1,0.2\n"
    "1.0,0.2,0.4\n"
)


def _channels(parsed: ParsedTest) -> dict[str, Channel]:
    return {one.key: one for one in parsed.channels}


def _profile_channels(definition: dict[str, Any], text: str) -> dict[str, Channel]:
    parsed = profiles.apply(definition, text.encode("utf-8"))
    return {one.key: one for one in parsed.curves[0].channels}


class TestZwick:
    def test_굽힘_파일의_채널(self) -> None:
        parsed = zwick_tra.parse(ZWICK_FLEXURAL.encode())
        found = _channels(parsed)
        assert set(found) == {"force", "displacement", "deflection", "time"}
        assert found["deflection"].si_unit == "m"
        assert found["deflection"].values[-1] == pytest.approx(0.12e-3)
        assert parsed.metadata["specimen_thickness_a0"] == "4.02"
        assert not [one for one in parsed.warnings if "모르는 채널" in one]

    def test_독일어_압축_파일(self) -> None:
        """독일어 로케일은 `;` 로 나누고 소수점이 `,` 다. kN · % 도 SI 로."""
        found = _channels(zwick_tra.parse(ZWICK_COMPRESSION_DE.encode()))
        assert found["force"].values[-1] == pytest.approx(250.0)
        assert found["displacement"].values[-1] == pytest.approx(0.5e-3)
        assert found["strain"].values[-1] == pytest.approx(0.04)

    def test_종류를_가른다(self) -> None:
        assert zwick_tra.classify(ZWICK_FLEXURAL.encode()) == ("flexural", "deflection")
        assert zwick_tra.classify(ZWICK_COMPRESSION_DE.encode()) == ("compression", "druck")
        assert zwick_tra.classify((FIXTURES / "Example.tra").read_bytes()) == (
            "tensile",
            "work hardening",
        )

    def test_이름으로_못_가르면_고르지_않는다(self) -> None:
        """하중 · 변위뿐이면 인장인지 압축인지 모른다 — 찍으면 압축이 인장으로 처리된다."""
        plain = '"Standard force","Standard travel"\n"N","mm"\n0,0\n1,0.1\n2,0.2\n'
        assert zwick_tra.classify(plain.encode()) is None
        both = '"Flexural strength",1,"MPa"\n"Compressive strength",1,"MPa"\n' + plain
        assert zwick_tra.classify(both.encode()) is None
        assert zwick_tra.classify(b"not a table") is None

    def test_Instron_기본_이름도_읽는다(self) -> None:
        """시험 종류를 골라 올리면 `Time · Extension · Load` 뿐인 Bluehill CSV 도 읽힌다."""
        found = _channels(zwick_tra.parse(INSTRON_PLAIN.encode()))
        assert found["displacement"].si_unit == "m"
        assert found["displacement"].values[-1] == pytest.approx(0.02e-3)
        assert found["force"].values[-1] == pytest.approx(10.0)
        assert found["time"].si_unit == "s"


class TestInstron:
    def test_괄호_단위_줄을_단위로_본다(self) -> None:
        (table,) = sniff(INSTRON_PLAIN.encode()).tables
        assert table.header == ("Time", "Extension", "Load")
        assert table.units == ("(sec)", "(mm)", "(N)")

    def test_굽힘_프로파일(self) -> None:
        found = _profile_channels(INSTRON_FLEXURAL_DEFINITION, INSTRON_FLEXURE)
        assert found["displacement"].values[-1] == pytest.approx(0.02e-3)
        assert found["deflection"].values[-1] == pytest.approx(0.016e-3)
        assert found["force"].values[-1] == pytest.approx(8.4)

    def test_이름_안의_단위(self) -> None:
        found = _profile_channels(INSTRON_COMPRESSION_DEFINITION, INSTRON_COMPRESSION_INLINE)
        assert found["force"].values[-1] == pytest.approx(400.0)
        assert found["displacement"].values[-1] == pytest.approx(0.2e-3)

    @pytest.mark.parametrize(
        ("definition", "text", "expected"),
        [
            (INSTRON_FLEXURAL_DEFINITION, INSTRON_FLEXURE, True),
            (INSTRON_FLEXURAL_DEFINITION, INSTRON_COMPRESSION_INLINE, False),
            (INSTRON_COMPRESSION_DEFINITION, INSTRON_COMPRESSION_INLINE, True),
            (INSTRON_COMPRESSION_DEFINITION, INSTRON_FLEXURE, False),
            # 이름만으로는 종류를 모른다 — 지문으로 잡지 않는다.
            (INSTRON_FLEXURAL_DEFINITION, INSTRON_PLAIN, False),
            (INSTRON_COMPRESSION_DEFINITION, INSTRON_PLAIN, False),
            # TA DMA 프로파일이 Instron 굽힘 파일을 잡지 않는다.
            (TA_DMA850_DEFINITION, INSTRON_FLEXURE, False),
        ],
    )
    def test_지문이_서로를_잡지_않는다(
        self, definition: dict[str, Any], text: str, expected: bool
    ) -> None:
        structure = sniff(text.encode())
        assert (
            profiles.matches(definition, filename="raw.csv", structure=structure) is expected
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("(mm)", "mm"), ("[N]", "N"), (" (sec) ", "sec"), ("mm", "mm"), ("W/(m*K)", "W/(m*K)")],
)
def test_한_겹_싼_단위만_벗긴다(raw: str, expected: str) -> None:
    assert units.unwrap(raw) == expected


def test_괄호_단위를_심볼로() -> None:
    assert profiles.unit_symbol("(sec)") == "s"
    assert profiles.unit_symbol("(kN)") == "kN"
