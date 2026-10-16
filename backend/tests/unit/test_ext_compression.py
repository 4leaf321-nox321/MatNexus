"""압축 시험 → 압축 응력 · 변형률 · 탄성률 · 규격 지표(확장 `compression`, 2026-10-16).

부호      장비가 압축을 음수로 적어도 양수로 바꾼다 — 통계가 오름차순 변형률을 전제한다
접촉점    닿기 전 구간을 버리고 그 자리를 변형 0 으로
사이클    고무 · 폼은 4번째(ISO 3386) · 3번째(D3574 C) 하중 구간을 쓴다
강도      ISO 844 · D1621: 10% 전의 **항복 봉우리**, 없으면 10% 응력 — 전체 최대가 아니다
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions
from matcore.processing import Frame, ProcessingError

extensions.load(Path(__file__).resolve().parents[2] / "extensions")

compress = importlib.import_module(f"{extensions.PACKAGE}.compression.compress")

HEIGHT = 0.0125
AREA = np.pi * 0.029**2 / 4
E = 5.0e6


def _frame(**columns: np.ndarray) -> Frame:
    units = {"force": "N", "displacement": "m", "strain": "1"}
    return Frame(dict(columns), {key: units[key] for key in columns})


def _options(**extra: Any) -> dict[str, Any]:
    return {"height": HEIGHT, "area": AREA, **extra}


def _values(step: Any) -> dict[str, float]:
    return {one.key: one.value for one in step.scalars}


def _rubber(top: float = 0.3, points: int = 301) -> tuple[np.ndarray, np.ndarray]:
    strain = np.linspace(0, top, points)
    return strain * HEIGHT, E * strain * AREA


def test_변위를_높이로_나눠_양수_응력_변형률() -> None:
    displacement, force = _rubber()
    step = compress.engineering(_frame(force=force, displacement=displacement), _options())
    strain = step.frame.columns[compress.STRAIN]
    stress = step.frame.columns[compress.STRESS]
    assert strain[-1] == pytest.approx(0.3)
    assert stress[-1] == pytest.approx(E * 0.3)
    found = _values(compress.modulus(step.frame, {"method": "secant", "maximum_strain": 0.1}))
    assert found["compressive_modulus"] == pytest.approx(E, rel=1e-6)


def test_압축이_음수면_뒤집는다() -> None:
    displacement, force = _rubber()
    step = compress.engineering(_frame(force=-force, displacement=-displacement), _options())
    assert step.frame.columns[compress.STRESS][-1] == pytest.approx(E * 0.3)
    assert any("뒤집" in one for one in step.notes)
    kept = compress.engineering(
        _frame(force=-force, displacement=-displacement), _options(sign="as_is")
    )
    assert kept.frame.columns[compress.STRESS][-1] < 0


def test_압축계_변형률이_있으면_그것() -> None:
    displacement, force = _rubber()
    strain = displacement / HEIGHT / 2  # 압축계는 시편 가운데만 — 변위보다 작다
    step = compress.engineering(
        _frame(force=force, displacement=displacement, strain=strain), _options()
    )
    assert step.frame.columns[compress.STRAIN][-1] == pytest.approx(0.15)
    forced = compress.engineering(
        _frame(force=force, displacement=displacement, strain=strain),
        _options(source="displacement"),
    )
    assert forced.frame.columns[compress.STRAIN][-1] == pytest.approx(0.3)


def test_닿기_전_구간을_버리고_변형_0_을_옮긴다() -> None:
    displacement, force = _rubber()
    gap = np.linspace(0, 0.001, 20)  # 1 mm 를 헛누른다
    frame = _frame(
        force=np.concatenate([np.zeros(20), force[1:]]),
        displacement=np.concatenate([gap, displacement[1:] + 0.001]),
    )
    step = compress.engineering(frame, _options())
    strain = step.frame.columns[compress.STRAIN]
    assert strain[0] == pytest.approx(0.0)
    assert strain[-1] == pytest.approx(0.3, rel=0.01)
    assert any("접촉 전" in one for one in step.notes)


def _cycles(count: int, soften: float = 0.1) -> Frame:
    """count 번 0 → 30% → 0. 누를 때마다 soften 만큼 부드러워진다(Mullins)."""
    up = np.linspace(0, 0.3, 61)
    down = up[::-1][1:]
    strain_parts, force_parts = [], []
    for cycle in range(count):
        modulus = E * (1 - soften * cycle)
        strain_parts += [up if cycle == 0 else up[1:], down]
        force_parts += [
            modulus * (up if cycle == 0 else up[1:]) * AREA,
            0.6 * modulus * down * AREA,
        ]
    strain = np.concatenate(strain_parts)
    return _frame(force=np.concatenate(force_parts), displacement=strain * HEIGHT)


def test_사이클을_세고_자동이면_마지막() -> None:
    step = compress.engineering(_cycles(4), _options(contact_force=0.0))
    assert _values(step)["loading_cycle_count"] == 4
    stress = step.frame.columns[compress.STRESS]
    # 마지막(4번째) 하중 구간: E·(1 - 0.3).
    assert stress[-1] == pytest.approx(E * 0.7 * 0.3, rel=1e-6)
    assert np.all(np.diff(step.frame.columns[compress.STRAIN]) >= 0)


def test_규격이_정한_사이클을_고른다() -> None:
    step = compress.engineering(_cycles(4), _options(contact_force=0.0, cycle=2))
    assert step.frame.columns[compress.STRESS][-1] == pytest.approx(E * 0.9 * 0.3, rel=1e-6)
    with pytest.raises(ProcessingError, match="4개뿐"):
        compress.engineering(_cycles(4), _options(contact_force=0.0, cycle=5))


def test_한_번_누른_시험은_구간이_하나() -> None:
    displacement, force = _rubber()
    step = compress.engineering(_frame(force=force, displacement=displacement), _options())
    assert _values(step)["loading_cycle_count"] == 1
    assert not any("하중 구간" in one for one in step.notes)


def _indices(strain: np.ndarray, stress: np.ndarray) -> dict[str, float]:
    frame = Frame(
        {compress.STRAIN: strain, compress.STRESS: stress},
        {compress.STRAIN: "1", compress.STRESS: "Pa"},
    )
    return _values(compress.indices(frame, {}))


def test_닿은_변형률의_응력만_낸다() -> None:
    strain = np.linspace(0, 0.45, 451)
    found = _indices(strain, E * strain)
    assert found["compressive_stress_at_10pct"] == pytest.approx(E * 0.10)
    assert found["compressive_stress_at_40pct"] == pytest.approx(E * 0.40)
    assert "compressive_stress_at_50pct" not in found
    assert "compressive_stress_at_65pct" not in found


def _rigid_foam() -> tuple[np.ndarray, np.ndarray]:
    """5% 에서 항복 봉우리(1 MPa) → 0.8 MPa 평탄 → 50% 뒤 치밀화(봉우리보다 커진다)."""
    strain = np.linspace(0, 0.8, 801)
    stress = np.where(strain < 0.05, 20e6 * strain, 0.0)
    stress = np.where(
        (strain >= 0.05) & (strain < 0.08), 1e6 - (strain - 0.05) / 0.03 * 0.2e6, stress
    )
    stress = np.where((strain >= 0.08) & (strain < 0.5), 0.8e6, stress)
    stress = np.where(strain >= 0.5, 0.8e6 + 20e6 * (strain - 0.5) ** 2, stress)
    return strain, stress


def test_압축_강도는_10퍼센트_전의_항복_봉우리() -> None:
    """**전체 최대가 아니다** — 경질 폼은 치밀화 뒤가 더 크다."""
    strain, stress = _rigid_foam()
    assert float(np.max(stress)) > 1e6
    found = _indices(strain, stress)
    assert found["compressive_strength"] == pytest.approx(1e6, rel=0.01)


def test_봉우리가_없으면_10퍼센트_응력() -> None:
    strain = np.linspace(0, 0.3, 301)
    stress = 1e6 * (1 - np.exp(-strain / 0.03)) + 2e6 * strain
    found = _indices(strain, stress)
    assert found["compressive_strength"] == pytest.approx(
        float(np.interp(0.10, strain, stress))
    )


def test_10퍼센트에_못_닿으면_최대() -> None:
    strain = np.linspace(0, 0.05, 51)
    found = _indices(strain, E * strain)
    assert found["compressive_strength"] == pytest.approx(E * 0.05)


def test_폼_평탄_응력_치밀화_흡수_에너지() -> None:
    strain, stress = _rigid_foam()
    found = _indices(strain, stress)
    assert found["plateau_stress"] == pytest.approx(0.8e6)
    # 0.8e6 + 20e6 (ε - 0.5)² = 1.3 · 0.8e6 → ε = 0.5 + √(0.012) ≈ 0.6095
    assert found["densification_strain"] == pytest.approx(0.5 + np.sqrt(0.012), abs=0.002)
    expected = float(np.trapezoid(stress[strain <= 0.5], strain[strain <= 0.5]))
    assert found["energy_absorption_50pct"] == pytest.approx(expected, rel=1e-3)


def test_높이가_0_이면_멈춘다() -> None:
    displacement, force = _rubber()
    with pytest.raises(ProcessingError, match="높이"):
        compress.engineering(
            _frame(force=force, displacement=displacement), _options(height=0.0)
        )
