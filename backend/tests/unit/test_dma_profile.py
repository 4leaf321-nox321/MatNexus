"""DMA 시험 종류와 TA DMA850 프로파일 — **실파일에서 정해진 것들.**

`Example FreqTemp2.csv`(TA DMA850, TRIOS 내보내기)를 열어 채널을 맞췄다.

    온도    -40 · -30 · -20 · -10 · 0 · 10 °C      6단
    주파수  0.1 · 0.2 · 0.5 · 1 · 2 · 5 · 10 · 20 Hz   각 온도에서 8점
    TTS     장비가 계산한 이동인자와 마스터커브가 함께 온다

실측 DMA CSV 9개 전부 읽혔다(실패 0).

이 시험이 지키는 것은 **곡선이 제 이름을 갖는가** 하나다. 점탄성 계산(마스터커브·
Prony)은 아직 없다 — 그건 다음 단계이고, 그 계산이 여기서 나온 채널 이름을 찾는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.tests.legacy_profiles import TA_DMA850_DEFINITION
from matcore.parsers import CurveData
from matcore.readers import profile as profiles
from matcore.readers import sniff

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"


def curves(path: Path) -> tuple[CurveData, ...]:
    return profiles.apply(TA_DMA850_DEFINITION, path.read_bytes()).curves


class Test지문:
    def test_열_이름으로_알아본다(self) -> None:
        """`.csv` 는 어느 장비나 쓴다. 확장자만 보면 남의 파일을 읽는다."""
        structure = sniff(FREQ_TEMP.read_bytes())
        assert profiles.matches(
            TA_DMA850_DEFINITION, filename="Example FreqTemp2.csv", structure=structure
        )

    def test_인장_파일은_안_잡는다(self) -> None:
        tensile = b"Time,Force\ns,N\n0,0\n1,100\n2,200\n"
        structure = sniff(tensile)
        assert not profiles.matches(
            TA_DMA850_DEFINITION, filename="x.csv", structure=structure
        )


class Test측정과계산을가른다:
    """**버리지도 섞지도 않는다.**

    장비가 계산한 TTS 결과를 버리면 그 앱이 한 일을 잃고, 측정과 같이 섞으면
    처리가 마스터커브를 원본으로 착각해 **마스터커브에 또 마스터커브를 씌운다.**
    """

    def test_측정_스윕과_TTS_를_따로_담는다(self) -> None:
        found = curves(FREQ_TEMP)
        measured = [c for c in found if c.kind == "measured"]
        derived = [c for c in found if c.kind == "derived"]
        assert len(measured) == 6, [c.label for c in measured]
        assert len(derived) == 2, [c.label for c in derived]

    def test_이동인자와_마스터커브가_둘_다_남는다(self) -> None:
        labels = {c.label for c in curves(FREQ_TEMP) if c.kind == "derived"}
        assert any(label and "shift factors" in label for label in labels), labels
        assert any(label and "master curve" in label for label in labels), labels


class Test채널:
    def test_점탄성에_필요한_넷이_SI_로_온다(self) -> None:
        """이 넷이 시험 종류의 필수 채널이다. 없으면 점탄성 계산이 성립하지 않는다."""
        first = curves(FREQ_TEMP)[0]
        units = {c.key: c.si_unit for c in first.channels}
        assert units["storage_modulus"] == "Pa"
        assert units["loss_modulus"] == "Pa"
        assert units["temperature"] == "K"
        assert units["angular_frequency"] == "rad/s"

    def test_MPa_를_Pa_로_바꾼다(self) -> None:
        """**10⁶ 배 틀리면 숫자는 멀쩡해 보이고 뜻만 바뀐다.** 화면 어디에도
        티가 안 난다."""
        first = curves(FREQ_TEMP)[0]
        storage = next(c for c in first.channels if c.key == "storage_modulus")
        # 201242 MPa → 2.01242e11 Pa
        assert storage.values[0] == pytest.approx(201242e6)

    def test_섭씨를_켈빈으로_바꾼다(self) -> None:
        first = curves(FREQ_TEMP)[0]
        temperature = next(c for c in first.channels if c.key == "temperature")
        # -40 °C → 233.15 K
        assert temperature.values[0] == pytest.approx(233.15)

    def test_tan_delta_는_무차원이다(self) -> None:
        """단위 칸이 비어 있어서 프로파일이 `1` 을 선언해 준다. 안 하면 '단위를
        알 수 없는 열' 로 등록이 거부된다."""
        first = curves(FREQ_TEMP)[0]
        tan_delta = next(c for c in first.channels if c.key == "tan_delta")
        assert tan_delta.si_unit == "1"

    def test_매핑_안_한_열도_버리지_않는다(self) -> None:
        """이동인자 표의 `aT (x variable)` 같은 것. 채널로 선언하진 않았지만
        **장비가 계산한 값이라 남긴다** — 나중에 사람이 매핑할 수도 있다."""
        shift = next(c for c in curves(FREQ_TEMP) if c.label and "shift factors" in c.label)
        keys = {c.key for c in shift.channels}
        assert "temperature" in keys
        assert len(keys) > 1, keys


class Test시편치수:
    def test_값과_단위가_한_칸에_와도_가른다(self) -> None:
        """실파일이 `Length,50.0 mm` 로 준다. Zwick 은 단위를 따로 주므로 이
        분리는 DMA 에서만 필요하다."""
        parsed = profiles.apply(TA_DMA850_DEFINITION, FREQ_TEMP.read_bytes())
        assert parsed.metadata["specimen_thickness"].startswith("0.989")
        assert parsed.metadata["specimen_width"].startswith("4.938")
