"""반복(사이클) 시험의 공용 단계(확장 `cyclic`, 2026-10-20).

답을 아는 곡선으로 본다 — 사이클 k 는 (r_{k-1}, 0) → (p_k, σ_k) 직선으로 당기고, 기울기 U_k 로
응력 0 까지 내린다. 그러면

    제하 탄성률      U_k
    잔류 변형률      r_k = p_k - σ_k / U_k
    고리 넓이        σ_k (r_k - r_{k-1}) / 2

사용자 보고: 반복 시험 공용 단계(사이클 분리 · 사이클별 제하 탄성률 · 잔류 변형률 ·
히스테리시스 에너지)가 없었다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError

# **운영과 같은 길로** — 확장 로더를 거쳐 읽는다.
extensions.load(Path(__file__).resolve().parents[2] / "extensions")

PEAKS = (0.01, 0.02, 0.03)
STRESSES = (100e6, 200e6, 300e6)
UNLOAD = (200e9, 180e9, 160e9)
RESIDUAL = tuple(p - s / u for p, s, u in zip(PEAKS, STRESSES, UNLOAD, strict=True))


def _curve(
    strain_key: str = "strain_engineering", stress_key: str = "stress_engineering"
) -> Frame:
    strain: list[float] = []
    stress: list[float] = []
    start = 0.0
    for peak, top, residual in zip(PEAKS, STRESSES, RESIDUAL, strict=True):
        up = np.linspace(0.0, 1.0, 40)
        strain.extend(start + (peak - start) * up)
        stress.extend(top * up)
        down = np.linspace(0.0, 1.0, 40)[1:]
        strain.extend(peak + (residual - peak) * down)
        stress.extend(top * (1.0 - down))
        start = residual
    return Frame(
        {strain_key: np.asarray(strain), stress_key: np.asarray(stress)},
        {strain_key: "1", stress_key: "Pa"},
    )


def _run(step: str, frame: Frame | None = None, **options: object) -> processing.StepResult:
    plugin = registry.get(step)
    result: processing.StepResult = plugin.fn(frame or _curve(), dict(options))
    return result


def _values(result: processing.StepResult) -> dict[str, float]:
    return {one.key: one.value for one in result.scalars}


def test_사이클을_나누고_점마다_번호와_가지를_단다() -> None:
    got = _run("cyclic.cycles")
    assert _values(got)["cycle_count"] == 3
    cycle = got.frame.columns["cycle"]
    branch = got.frame.columns["cycle_branch"]
    assert set(np.unique(cycle)) == {1.0, 2.0, 3.0}
    # 첫 점은 하중, 끝 점은 셋째 사이클의 제하다.
    assert branch[0] == 1.0 and branch[-1] == -1.0 and cycle[-1] == 3.0


def test_제하_탄성률은_사이클마다의_내리는_기울기() -> None:
    found = _values(_run("cyclic.unloading_modulus"))
    for number, slope in enumerate(UNLOAD, start=1):
        assert found[f"unloading_modulus_c{number}"] == pytest.approx(slope, rel=1e-9)
    assert found["unloading_modulus_first"] == pytest.approx(UNLOAD[0])
    assert found["unloading_modulus_last"] == pytest.approx(UNLOAD[-1])
    assert found["unloading_modulus_ratio"] == pytest.approx(UNLOAD[-1] / UNLOAD[0])


def test_잔류_변형률은_응력_0_을_지나는_변형률() -> None:
    found = _values(_run("cyclic.residual_strain"))
    for number, residual in enumerate(RESIDUAL, start=1):
        assert found[f"residual_strain_c{number}"] == pytest.approx(residual, rel=1e-9)
    assert found["residual_strain_max"] == pytest.approx(max(RESIDUAL))


def test_히스테리시스는_고리_넓이() -> None:
    found = _values(_run("cyclic.hysteresis"))
    before = 0.0
    for number, (top, residual, peak) in enumerate(
        zip(STRESSES, RESIDUAL, PEAKS, strict=True), start=1
    ):
        area = top * (residual - before) / 2
        assert found[f"hysteresis_energy_c{number}"] == pytest.approx(area, rel=1e-9)
        assert found[f"energy_loss_ratio_c{number}"] == pytest.approx(
            (residual - before) / (peak - before), rel=1e-9
        )
        before = residual


def test_압축_열도_스스로_찾는다() -> None:
    """같은 단계가 반복 압축에 선다 — 압축 처리가 만든 열(양수)을 찾아 쓴다."""
    frame = _curve("compressive_strain", "compressive_stress")
    found = _values(_run("cyclic.unloading_modulus", frame))
    assert found["unloading_modulus_c2"] == pytest.approx(UNLOAD[1], rel=1e-9)


def test_네킹은_제하가_아니다() -> None:
    """변형률이 늘며 응력만 떨어지는 단조 시험 — 사이클로 세면 안 된다."""
    strain = np.linspace(0.0, 0.3, 200)
    stress = np.where(strain < 0.2, 400e6 * strain / 0.2, 400e6 - 2e9 * (strain - 0.2))
    frame = Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )
    with pytest.raises(ProcessingError, match="사이클"):
        _run("cyclic.cycles", frame)


def test_레시피에서_하중_채널이_있는_시험에_선다() -> None:
    """시험 종류를 따로 두지 않는다 — 하중 채널이 있으면 인장 · 압축 · 굽힘 어디든."""
    for step in ("cyclic.cycles", "cyclic.unloading_modulus", "cyclic.residual_strain"):
        assert registry.get(step).requires_channels == (("force",),)
    out = processing.apply(
        [processing.Step("cyclic.cycles", {}), processing.Step("cyclic.hysteresis", {})],
        _curve(),
    )
    assert {one.key for one in out.stages[-1].scalars} >= {"hysteresis_energy_total"}


def test_제하_탄성률은_제하_가지_윗부분에서_잰다() -> None:
    """제하 끝은 굽는다(역방향 소성 · 접촉) — 가지 전체에 직선을 얹으면 기울기가 작게 나온다.
    윗부분만 쓰면 처음 기울기(U)가 나온다."""
    top, slope, peak, bend = 200e6, 200e9, 0.02, 0.0005
    up = np.linspace(0.0, 1.0, 60)
    down = np.linspace(0.0, 1.0, 120)[1:]
    strain = np.concatenate(
        [peak * up, peak - (top / slope) * down - bend * down**4, [peak - top / slope - bend]]
    )
    stress = np.concatenate([top * up, top * (1.0 - down), [0.0]])
    # 다음 사이클로 조금 다시 당긴다 — 골이 서야 사이클이 닫힌다.
    strain = np.concatenate([strain, strain[-1] + np.linspace(0.0, 0.002, 20)[1:]])
    stress = np.concatenate([stress, np.linspace(0.0, 150e6, 20)[1:]])
    frame = Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )
    found = _values(_run("cyclic.unloading_modulus", frame, unload_fraction=0.2))
    assert found["unloading_modulus_c1"] == pytest.approx(slope, rel=0.01)
