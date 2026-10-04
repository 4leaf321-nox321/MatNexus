"""DMA 처리 단계.

DMA 는 인장과 사정이 정반대다. 장비가 저장·손실 탄성률을 **이미 계산해서** 주므로,
여기 단계들은 새로 만드는 것이 아니라 **채우고 바꾸는** 일을 한다.

지키는 것:

    없는 열을 채운다      tan δ 는 선택 채널이라 없는 파일이 있다
    덮으면 덮었다고 적는다  "장비 값인가 우리 값인가" 를 나중에 답할 수 있어야 한다
    정의를 값과 함께 남긴다 Tg 는 정의마다 값이 다르다
    가정을 적는다          E → G 는 등방·선형을 가정한 변환이다
"""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import pytest

from matcore import processing
from matcore.processing import Frame, ProcessingError


def frame(**columns: list[float]) -> Frame:
    units = {
        "storage_modulus": "Pa",
        "loss_modulus": "Pa",
        "temperature": "K",
        "frequency": "Hz",
        "angular_frequency": "rad/s",
        "tan_delta": "1",
    }
    return Frame(
        {key: np.array(value, dtype=float) for key, value in columns.items()},
        {key: units.get(key, "1") for key in columns},
    )


def run(plugin: str, source: Frame, **options: object) -> processing.PipelineResult:
    processing.load_builtin()
    return processing.apply([processing.Step(plugin, dict(options))], source)


class TestDerived:
    def test_없는_열을_채운다(self) -> None:
        """**tan δ 는 선택 채널이다.** 없으면 Tg 판정이 통째로 막힌다."""
        result = run(
            "dma.derived",
            frame(storage_modulus=[1000.0, 500.0], loss_modulus=[100.0, 250.0]),
        )
        assert result.frame.columns["tan_delta"] == pytest.approx([0.1, 0.5])
        assert result.frame.columns["complex_modulus"][0] == pytest.approx(
            math.hypot(1000.0, 100.0)
        )
        assert result.frame.columns["phase_angle"][0] == pytest.approx(
            math.atan2(100.0, 1000.0)
        )

    def test_파일이_준_열을_덮으면_적는다(self) -> None:
        """**조용히 덮으면 어느 쪽 값인지 못 답한다.**"""
        result = run(
            "dma.derived",
            frame(
                storage_modulus=[1000.0, 500.0],
                loss_modulus=[100.0, 250.0],
                tan_delta=[9.9, 9.9],
            ),
        )
        assert result.frame.columns["tan_delta"] == pytest.approx([0.1, 0.5])
        assert any("덮었습니다" in note for note in result.notes)

    def test_저장_탄성률이_0_이면_거절한다(self) -> None:
        """그 점에서 tan δ 가 무한대가 된다 — 오류 없이 그럴듯한 곡선이 나온다."""
        with pytest.raises(ProcessingError):
            run("dma.derived", frame(storage_modulus=[0.0, 500.0], loss_modulus=[1.0, 2.0]))


class TestFrequency:
    def test_주파수에서_각주파수를_만든다(self) -> None:
        result = run("dma.frequency", frame(frequency=[1.0, 10.0]), direction="to_angular")
        assert result.frame.columns["angular_frequency"] == pytest.approx(
            [2 * math.pi, 20 * math.pi]
        )

    def test_각주파수에서_주파수를_만든다(self) -> None:
        """**한쪽만 오는 파일이 있다.** 마스터커브는 주파수축을 쓴다."""
        result = run(
            "dma.frequency", frame(angular_frequency=[2 * math.pi]), direction="to_frequency"
        )
        assert result.frame.columns["frequency"] == pytest.approx([1.0])

    def test_원본_열이_없으면_무엇이_없는지_말한다(self) -> None:
        with pytest.raises(ProcessingError) as caught:
            run("dma.frequency", frame(storage_modulus=[1.0]), direction="to_angular")
        assert "주파수" in str(caught.value)


class TestGlassTransition:
    """**정의마다 값이 다르다.** 그래서 무엇으로 쟀는지가 값과 함께 남아야 한다."""

    #: 실제 순서를 담은 스윕 — **저장 탄성률이 먼저 떨어지고, 손실이 피크를
    #: 지나고, tan δ 가 마지막에 피크다.** 셋이 같은 온도를 주면 이 파일이
    #: 지키려는 것을 증명하지 못한다.
    SWEEP: ClassVar[dict[str, list[float]]] = dict(
        temperature=[300.0, 310.0, 320.0, 330.0, 340.0],
        storage_modulus=[1000.0, 480.0, 200.0, 60.0, 50.0],
        loss_modulus=[10.0, 90.0, 150.0, 55.0, 8.0],
        tan_delta=[0.01, 0.1875, 0.75, 0.9167, 0.16],
    )

    def _value(self, method: str, **options: object) -> float:
        result = run("dma.glass_transition", frame(**self.SWEEP), method=method, **options)
        return next(s.value for s in result.scalars if s.key == "glass_transition")

    def test_정의마다_다른_값이_나온다(self) -> None:
        """**이 파일의 이유.** 하나로 박아 두면 다른 정의로 보고된 값과 비교가
        안 되고, 조용히 바꾸면 예전 값과 어긋난다."""
        tan_peak = self._value("tan_delta_peak")
        loss_peak = self._value("loss_peak")
        onset = self._value("storage_onset", drop=0.5)
        # 같은 스윕인데 셋이 20 K 씩 벌어진다.
        assert onset == pytest.approx(310.0)
        assert loss_peak == pytest.approx(320.0)
        assert tan_peak == pytest.approx(330.0)

    def test_피크에서의_값도_낸다(self) -> None:
        """피크가 뚜렷한지 보는 근거다."""
        result = run("dma.glass_transition", frame(**self.SWEEP), method="tan_delta_peak")
        peak = next(s for s in result.scalars if s.key == "glass_transition_peak")
        assert peak.value == pytest.approx(0.9167)

    def test_끝에서_잡힌_피크는_말해_준다(self) -> None:
        """**끝에서 잡힌 피크는 피크가 아니다.** 스윕이 전이를 안 지났다는
        뜻인데, 값 자체는 그럴듯하게 나온다."""
        result = run(
            "dma.glass_transition",
            frame(
                temperature=[300.0, 310.0, 320.0],
                storage_modulus=[1000.0, 900.0, 800.0],
                loss_modulus=[1.0, 2.0, 3.0],
                tan_delta=[0.01, 0.02, 0.03],
            ),
            method="tan_delta_peak",
        )
        assert any("끝에서 잡혔" in note for note in result.notes)

    def test_전이를_안_지난_스윕은_온셋을_거절한다(self) -> None:
        with pytest.raises(ProcessingError) as caught:
            run(
                "dma.glass_transition",
                frame(
                    temperature=[300.0, 310.0, 320.0],
                    storage_modulus=[1000.0, 990.0, 980.0],
                    loss_modulus=[1.0, 2.0, 3.0],
                ),
                method="storage_onset",
                drop=0.5,
            )
        assert "떨어지는 지점이 없습니다" in str(caught.value)


def _log_sweep(corner: float = 300.0) -> Frame:
    """log E′ 가 꺾인 직선 셋 — **답을 안다.** 유리 영역 기울기 -0.002/K, `corner` 부터
    -0.05/K 로 40 K, 그 뒤 고무 영역. 두 접선(유리 기준선과 가장 가파른 직선)은 정확히
    `corner` 에서 만난다."""
    t = np.arange(200.0, 401.0, 5.0)
    glassy = 9.5 - 0.002 * (t - 200.0)
    at_corner = 9.5 - 0.002 * (corner - 200.0)
    steep = at_corner - 0.05 * (t - corner)
    rubbery = at_corner - 0.05 * 40.0 - 0.001 * (t - corner - 40.0)
    y = np.where(t <= corner, glassy, np.where(t <= corner + 40.0, steep, rubbery))
    storage = 10.0**y
    return Frame(
        {
            "temperature": t,
            "storage_modulus": storage,
            "loss_modulus": storage * 0.1,
            "tan_delta": np.full_like(t, 0.1),
        },
        {"temperature": "K", "storage_modulus": "Pa", "loss_modulus": "Pa", "tan_delta": "1"},
    )


class Test접선_교점_온셋:
    """ASTM E1640 — log E′ 의 유리 기준선과 변곡점 접선이 만나는 온도.

    전에는 「온셋」 이라는 라벨 아래 낙폭 절반 지점(전이의 한가운데)을 냈다(2026-09-30
    바로잡음). 온셋으로 보고된 Tg 와 견주려면 이 정의가 따로 있어야 한다.
    """

    def test_두_접선이_만나는_온도를_낸다(self) -> None:
        result = run("dma.glass_transition", _log_sweep(), method="storage_tangent_onset")
        values = {s.key: s.value for s in result.scalars}
        assert values["glass_transition"] == pytest.approx(300.0, abs=1e-6)
        # 그 온도의 기준선 위 E′ — 10^(9.5 - 0.2)
        assert values["glass_transition_peak"] == pytest.approx(10**9.3, rel=1e-9)
        assert any("기준선(자동)" in note for note in result.notes)

    def test_낙폭_절반_지점보다_낮다(self) -> None:
        """온셋은 전이의 시작이다 — 낙폭 절반(한가운데)보다 늘 낮게 나와야 한다."""
        sweep = _log_sweep()
        onset = run("dma.glass_transition", sweep, method="storage_tangent_onset")
        middle = run("dma.glass_transition", sweep, method="storage_onset", drop=0.5)

        def tg(result: processing.PipelineResult) -> float:
            return next(s.value for s in result.scalars if s.key == "glass_transition")

        assert tg(onset) < tg(middle)

    def test_기준선_구간을_직접_줄_수_있다(self) -> None:
        result = run(
            "dma.glass_transition",
            _log_sweep(),
            method="storage_tangent_onset",
            baseline_start=220.0,
            baseline_end=280.0,
        )
        assert next(s.value for s in result.scalars if s.key == "glass_transition") == (
            pytest.approx(300.0, abs=1e-6)
        )
        assert any("기준선(지정): 220~280 K" in note for note in result.notes)

    def test_전이_한가운데서_시작한_스윕은_짐작하지_않는다(self) -> None:
        """평탄부가 없으면 첫 두 점에 그은 「기준선」 이 그럴듯한 온도를 낸다."""
        sweep = _log_sweep(corner=205.0)
        with pytest.raises(ProcessingError, match="유리 영역"):
            run("dma.glass_transition", sweep, method="storage_tangent_onset")


class TestToShear:
    def test_등방_변환으로_전단을_낸다(self) -> None:
        """**Prony 카드는 전단 기준이다.** 인장으로 쟀으면 여기를 거쳐야 한다."""
        result = run(
            "dma.to_shear",
            frame(storage_modulus=[2700.0], loss_modulus=[270.0]),
            poisson_ratio=0.35,
        )
        assert result.frame.columns["storage_modulus_shear"] == pytest.approx([1000.0])
        assert result.frame.columns["loss_modulus_shear"] == pytest.approx([100.0])

    def test_가정을_결과에_적는다(self) -> None:
        """ν 는 온도에 따라 변하고 이방성 재료에서는 이 식이 성립하지 않는다."""
        result = run(
            "dma.to_shear",
            frame(storage_modulus=[2700.0], loss_modulus=[270.0]),
            poisson_ratio=0.35,
        )
        assert any("등방" in note and "0.35" in note for note in result.notes)

    def test_포아송비를_안_주면_거절한다(self) -> None:
        """**기본값을 안 둔다.** 이 값이 결과를 그대로 바꾼다."""
        with pytest.raises(ProcessingError):
            run("dma.to_shear", frame(storage_modulus=[2700.0], loss_modulus=[270.0]))

    def test_0_5_는_그_자체로_못_쓴다(self) -> None:
        """완전 비압축성이다 — 나눗셈은 되지만 뜻이 없다."""
        with pytest.raises(ProcessingError):
            run(
                "dma.to_shear",
                frame(storage_modulus=[2700.0], loss_modulus=[270.0]),
                poisson_ratio=0.5,
            )


class Test선형점탄성_탄성률:
    """변형률 스윕에서 E 를 뽑는다 — **인장의 탄성계수와 같은 자리.**

    인장은 곡선에서 직선 구간을 찾아 기울기를, 여기는 평탄 구간을 찾아 높이를
    낸다. 그래서 무는 자리도 같다: **어디까지를 그 구간으로 보는가.**
    """

    #: 0.1 % 부터 무너지는 합성 곡선. 평탄부 1.20 GPa.
    STRAIN: ClassVar[list[float]] = [1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0, 3.0]
    STORAGE: ClassVar[list[float]] = [
        1.200e9,
        1.199e9,
        1.198e9,
        1.190e9,
        0.900e9,
        0.400e9,
        0.150e9,
        0.050e9,
    ]

    def _run(self, **options: object) -> processing.PipelineResult:
        return run(
            "dma.lve_modulus",
            frame(oscillation_strain=self.STRAIN, storage_modulus=self.STORAGE),
            **options,
        )

    def test_평탄부의_높이를_낸다(self) -> None:
        values = {one.key: one.value for one in self._run().scalars}
        # 앞 네 점이 5 % 안에 있다 — 그 평균.
        assert values["youngs_modulus"] == pytest.approx(1.1968e9, rel=1e-3)
        assert values["lve_point_count"] == 4

    def test_선형_한계를_함께_낸다(self) -> None:
        """**이보다 크게 흔들면 그 값은 선형이 아니다.** 값만 주고 한계를 안
        주면 다음 사람이 어디까지 믿을 수 있는지 모른다."""
        values = {one.key: one.value for one in self._run().scalars}
        assert values["lve_strain_limit"] == pytest.approx(3e-2)

    def test_산출_키가_탄성_블록의_이름이다(self) -> None:
        """**카드가 인장에서 왔는지 DMA 에서 왔는지 몰라도 되게.** 키를 따로
        두면 블록마다 대응표를 손으로 적어야 한다."""
        assert "youngs_modulus" in {one.key for one in self._run().scalars}

    def test_중간에_무너졌다_올라온_점은_안_줍는다(self) -> None:
        """**낮은 쪽부터 이어진 구간만 본다.** 주우면 평균이 조용히 올라가고,
        그 값은 어떤 변형률의 것도 아니게 된다."""
        broken = frame(
            oscillation_strain=[1e-3, 3e-3, 1e-2, 3e-2, 1e-1],
            # 셋째에서 무너졌다가 넷째에서 되올라온다.
            storage_modulus=[1.20e9, 1.19e9, 0.50e9, 1.20e9, 0.40e9],
        )
        outcome = processing.apply(
            [processing.Step("dma.lve_modulus", {"minimum_points": 2})], broken
        )
        values = {one.key: one.value for one in outcome.scalars}
        assert values["lve_point_count"] == 2

    def test_평탄이_너무_짧으면_막는다(self) -> None:
        """**두 점은 직선이지 평탄이 아니다.** 그 평균을 「E 를 쟀다」 고 부를 수
        없다 — 없는 값을 만들지 않는다."""
        steep = frame(
            oscillation_strain=[1e-3, 1e-2, 1e-1],
            storage_modulus=[1.20e9, 0.60e9, 0.20e9],
        )
        with pytest.raises(ProcessingError) as caught:
            processing.apply([processing.Step("dma.lve_modulus", {})], steep)
        assert "선형 구간" in str(caught.value)

    def test_끝까지_평탄하면_한계를_못_봤다고_말한다(self) -> None:
        """그 값을 「선형 한계」 라고 부르면 **잰 적 없는 것을 잰 것처럼** 말하는
        셈이 된다."""
        flat = frame(
            oscillation_strain=[1e-3, 3e-3, 1e-2, 3e-2],
            storage_modulus=[1.20e9, 1.20e9, 1.19e9, 1.19e9],
        )
        outcome = processing.apply([processing.Step("dma.lve_modulus", {})], flat)
        assert any("관측하지 못했습니다" in said for said in outcome.notes)

    def test_판정_폭을_넓히면_더_줍는다(self) -> None:
        """관행값(5 %)이 모든 재료에 맞지는 않는다 — 고를 수 있어야 한다."""
        narrow = {one.key: one.value for one in self._run(tolerance=0.05).scalars}
        wide = {one.key: one.value for one in self._run(tolerance=0.30).scalars}
        assert wide["lve_point_count"] > narrow["lve_point_count"]
