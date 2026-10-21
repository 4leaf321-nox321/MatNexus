"""박리 · 이탈력(확장 `adhesion`, 2026-10-20).

답을 아는 곡선 — 처음 10 % 에서 10 N 까지 오르고(최대), 8 N 근처에서 박리가 이어지다 끝에서
떨어진다. 폭 25 mm 면 박리 강도 320 N/m, 90° 면 접착 에너지도 320 J/m², 180° 면 640.

사용자 보고: 이탈력(배터리 PTT · 테이프 · SIM 트레이 삽입 · 인출) 처리 단계가 없었다.
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, registry
from matcore.groups import Member
from matcore.processing import Frame, ProcessingError

# **운영과 같은 길로** — 확장 로더를 거쳐 읽는다.
extensions.load(Path(__file__).resolve().parents[2] / "extensions")
peel = importlib.import_module(f"{extensions.PACKAGE}.adhesion.peel")

WIDTH = 0.025


def _curve() -> Frame:
    displacement = np.linspace(0.0, 0.1, 1001)
    share = displacement / 0.1
    force = np.where(
        share < 0.1,
        100.0 * share,  # 0 → 10 N
        8.0 + 0.2 * np.sin(200 * share),  # 박리 — 8 N 근처
    )
    force = np.where(share > 0.95, force * (1 - (share - 0.95) / 0.05), force)  # 끝에서 떨어짐
    return Frame(
        {"force": force, "displacement": displacement}, {"force": "N", "displacement": "m"}
    )


def _values(**options: object) -> dict[str, float]:
    step = registry.get("adhesion.peel")
    return {one.key: one.value for one in step.fn(_curve(), dict(options)).scalars}


def test_최대_하중과_안정_구간_평균() -> None:
    found = _values()
    assert found["max_force"] == pytest.approx(10.0, rel=1e-3)
    assert found["plateau_force"] == pytest.approx(8.0, abs=0.02)
    assert found["plateau_force_cv"] < 0.05
    # 곡선 아래 넓이 — 오르는 삼각형 + 평탄 + 떨어지는 삼각형.
    assert found["fracture_energy"] == pytest.approx(
        0.5 * 10 * 0.01 + 8 * 0.085 + 0.5 * 8 * 0.005, rel=0.02
    )


def test_폭이_있으면_박리_강도_각도가_있으면_접착_에너지() -> None:
    found = _values(width=WIDTH, peel_angle=math.pi / 2)
    assert found["peel_strength"] == pytest.approx(8.0 / WIDTH, rel=0.005)
    assert found["adhesion_energy"] == pytest.approx(found["peel_strength"], rel=1e-9)
    twice = _values(width=WIDTH, peel_angle=math.pi)
    assert twice["adhesion_energy"] == pytest.approx(2 * twice["peel_strength"], rel=1e-9)


def test_폭이_없으면_박리_강도를_안_낸다() -> None:
    """이탈 · 삽입은 폭이 없다 — 지어내지 않는다."""
    step = registry.get("adhesion.peel").fn(_curve(), {})
    keys = {one.key for one in step.scalars}
    assert "peel_strength" not in keys and "adhesion_energy" not in keys
    assert any("시편 폭이 없어" in one for one in step.notes)


def test_안정_구간이_뒤집히면_멈춘다() -> None:
    with pytest.raises(ProcessingError, match="안정 구간"):
        registry.get("adhesion.peel").fn(_curve(), {"window_start": 0.8, "window_end": 0.2})


def test_각도를_도로_넣으면_멈춘다() -> None:
    """**라디안이다** — 90 을 넣으면 1 - cos(90 rad) = 1.45 배가 오류 없이 나왔다(2026-10-20
    검토). 화면은 도로 받아 옮기므로 이 길은 API · MCP 다."""
    with pytest.raises(ProcessingError, match="라디안"):
        registry.get("adhesion.peel").fn(_curve(), {"width": WIDTH, "peel_angle": 90})


def test_누르는_쪽을_음수로_적어도_같은_값() -> None:
    """SIM 트레이 삽입처럼 하중 · 변위를 음수로 적는 장비 — 전에는 최대 하중이 0 근처,
    박리 강도가 음수로 나왔다(2026-10-20 검토)."""
    curve = _curve()
    pushed = Frame(
        {"force": -curve.columns["force"], "displacement": -curve.columns["displacement"]},
        {"force": "N", "displacement": "m"},
    )
    step = registry.get("adhesion.peel").fn(pushed, {"width": WIDTH})
    found = {one.key: one.value for one in step.scalars}
    plain = _values(width=WIDTH)
    assert found["max_force"] == pytest.approx(plain["max_force"])
    assert found["peel_strength"] == pytest.approx(plain["peel_strength"])
    assert any("부호를 뒤집었습니다" in one for one in step.notes)


def test_묶음은_평균하고_카드는_응집_영역과_참고_물성() -> None:
    members = [
        Member(label="A", values={"peel_strength": 300.0, "adhesion_energy": 300.0}),
        Member(label="B", values={"peel_strength": 340.0, "adhesion_energy": 340.0}),
    ]
    got = peel.summary(members)
    assert got.values["peel_strength"] == pytest.approx(320.0)
    assert got.values["sample_count"] == 2
    blocks = peel.card_blocks(got.values, got.detail, got.warnings)
    assert blocks["cohesive_zone"]["values"]["fracture_energy"] == pytest.approx(320.0)
    assert blocks["cohesive_zone"]["values"]["mode"] == "모드 I (박리)"
    assert blocks["reference"]["values"]["peel_strength"] == pytest.approx(320.0)
    # 최대 견인력은 박리 시험이 주지 않는다 — 칸에 지어내지 않는다.
    assert "peak_traction" not in blocks["cohesive_zone"]["values"]
