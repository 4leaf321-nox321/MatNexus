"""레오미터 유동 시험 종류와 TA HR 프로파일 — **공개 실파일에서 정해진 것들.**

TA Discovery HR30 의 TRIOS 내보내기(read-rheol 저장소의 `sample_Trios_2.csv`·
`sample_Trios_1.txt`)를 열어 채널을 맞췄다. 한 파일에 Peak hold·Flow sweep·Amplitude
sweep 이 `[step]` 블록으로 같이 오고, 열은 이렇다:

    Stress,Shear rate,Viscosity,Step time,Temperature,Normal stress
    Pa,1/s,Pa.s,min,°C,Pa

DMA850 과 같은 TRIOS 구조라 같은 읽기가 그대로 먹는다. 실파일 둘(쉼표·탭) 다 읽혔다.
여기 붙인 fixture 는 그 구조를 그대로 흉내 낸 **합성 파일**이다 — Carreau 점도
(η₀=12, η∞=0.05, λ=0.5, n=0.35)로 만들어 유변 식 검증에도 쓴다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.tests.legacy_profiles import TA_DMA850_DEFINITION, TA_HR_FLOW_DEFINITION
from matcore.readers import profile as profiles
from matcore.readers import sniff

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FLOW = FIXTURES / "rheometer_flow_sweep.csv"


class Test지문:
    def test_전단율과_점도_열로_알아본다(self) -> None:
        structure = sniff(FLOW.read_bytes())
        assert profiles.matches(TA_HR_FLOW_DEFINITION, filename="x.csv", structure=structure)
        # 같은 TRIOS 구조지만 DMA 프로파일은 이 파일을 안 잡는다 — 열 이름이 다르다.
        assert not profiles.matches(
            TA_DMA850_DEFINITION, filename="x.csv", structure=structure
        )

    def test_DMA_파일은_안_잡는다(self) -> None:
        dma = (FIXTURES / "dma_freq_temp.csv").read_bytes()
        assert not profiles.matches(
            TA_HR_FLOW_DEFINITION, filename="x.csv", structure=sniff(dma)
        )


class Test읽기:
    def test_Flow_sweep_단만_곡선이_되고_단위는_SI_로_바뀐다(self) -> None:
        out = profiles.apply(TA_HR_FLOW_DEFINITION, FLOW.read_bytes())
        assert [one.label for one in out.curves] == ["Flow sweep - 1"]
        curve = out.curves[0]
        by_key = {channel.key: channel for channel in curve.channels}
        assert set(by_key) == {
            "shear_rate",
            "viscosity",
            "shear_stress",
            "temperature",
            "step_time",
            "normal_stress",
        }
        assert by_key["viscosity"].si_unit == "Pa.s"
        assert by_key["shear_rate"].si_unit == "1/s"
        # min → s, °C → K. **조용히 틀리는 자리** — 파일이 단위 줄을 주고 읽는 쪽이 바꾼다.
        assert by_key["step_time"].si_unit == "s"
        assert by_key["step_time"].values[0] == pytest.approx(0.116824 * 60, rel=1e-6)
        assert by_key["temperature"].si_unit == "K"
        assert by_key["temperature"].values[0] == pytest.approx(298.15)
        # 점도는 전단율이 오를수록 내린다(전단 박화) — 합성 Carreau 곡선.
        viscosity = [float(v) for v in by_key["viscosity"].values if v is not None]
        assert viscosity[0] == pytest.approx(11.99, abs=0.01)
        assert viscosity[-1] < 0.3
        # Peak hold 는 건너뛰었다고 말한다 — 조용히 버리지 않는다.
        assert any("Peak hold" in one for one in out.warnings)
