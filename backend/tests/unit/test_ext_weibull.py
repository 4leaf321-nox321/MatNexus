"""와이블 강도 분포(확장 `weibull`, 2026-10-20).

답을 아는 표본 — 형상 m = 8, 척도 x₀ = 100 N 의 분위수로 30 개를 만든다(난수 없음). 최대우도는
그 근처로 돌아와야 한다.

사용자 보고: 곡선 없이 파단 하중과 와이블(형상 · 척도)만 있는 외부 자료를 담을 블록이 없었다.
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path

import pytest

from matcore import extensions, registry
from matcore.groups import GroupError, Member

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
strength = importlib.import_module(f"{extensions.PACKAGE}.weibull.strength")

SHAPE, SCALE, COUNT = 8.0, 100.0, 30


def _members(key: str = "max_force", count: int = COUNT) -> list[Member]:
    values = [
        SCALE * (-math.log(1 - (index - 0.5) / count)) ** (1 / SHAPE)
        for index in range(1, count + 1)
    ]
    return [
        Member(label=f"S{index}", values={key: value}) for index, value in enumerate(values)
    ]


def test_형상_척도를_되찾는다() -> None:
    got = strength.weibull_fit(_members())
    assert got.values["weibull_shape"] == pytest.approx(SHAPE, rel=0.08)
    assert got.values["weibull_scale"] == pytest.approx(SCALE, rel=0.02)
    # 하위 5 % = x₀ · (-ln 0.95)^(1/m).
    expected = got.values["weibull_scale"] * (-math.log(0.95)) ** (
        1 / got.values["weibull_shape"]
    )
    assert got.values["weibull_p05"] == pytest.approx(expected, rel=1e-6)
    assert got.values["sample_count"] == COUNT
    assert not got.warnings


def test_카드_블록은_행이_자기_단위를_든다() -> None:
    got = strength.weibull_fit(_members())
    block = strength.card_blocks(got.values, got.detail, got.warnings)["strength_distribution"]
    assert block["values"]["distribution"] == "weibull"
    assert block["values"]["quantity"] == "max_force"
    rows = {row["name"]: row for row in block["rows"]}
    # 경화식 행과 같은 칸(`si_unit`) — 단위계 환산과 화면이 그 칸을 읽는다(2026-10-20 검토).
    assert rows["shape"]["si_unit"] == "1" and rows["scale"]["si_unit"] == "N"
    assert rows["p05"]["value"] == pytest.approx(got.values["weibull_p05"])


def test_단위계를_바꾸면_척도도_옮겨진다() -> None:
    """강도(Pa)로 맞춘 척도는 mm 계에서 MPa 다 — `unit` 칸이던 때는 SI 숫자에 MPa 계라고
    적혀 나갔다(2026-10-20 검토)."""
    from matcore import export
    from matcore.export.systems import MM_N_TONNE

    got = strength.weibull_fit(_members("tensile_strength"), quantity="tensile_strength")
    block = strength.card_blocks(got.values, got.detail, got.warnings)
    deck = export.Deck(name="W", solver_id=1, blocks=block, provenance=())
    moved = export.to_system(deck, MM_N_TONNE)
    rows = {row["name"]: row for row in moved.blocks["strength_distribution"]["rows"]}
    assert rows["scale"]["value"] == pytest.approx(got.values["weibull_scale"] * 1e-6)
    assert rows["shape"]["value"] == pytest.approx(got.values["weibull_shape"])


def test_다른_값으로도_맞춘다() -> None:
    got = strength.weibull_fit(_members("tensile_strength"), quantity="tensile_strength")
    assert got.detail["unit"] == "Pa"


def test_적으면_말하고_너무_적으면_안_맞춘다() -> None:
    few = strength.weibull_fit(_members(count=6))
    assert any("크게 흔들립니다" in one for one in few.warnings)
    with pytest.raises(GroupError, match="5개 이상"):
        strength.weibull_fit(_members(count=4))


def test_값이_다_같으면_맞추지_않는다() -> None:
    """흩어짐이 0 이면 m 이 무한대로 간다 — 50 다섯 개에 m = 5e6 이 경고 없이 나왔다(2026-10-20
    검토). 무한대 값은 빼고 센다(scipy 가 ValueError 로 터졌다)."""
    same = [Member(label=f"S{index}", values={"max_force": 50.0}) for index in range(5)]
    with pytest.raises(GroupError, match="모두 같아"):
        strength.weibull_fit(same)
    with_inf = [*_members(count=6), Member(label="X", values={"max_force": math.inf})]
    fitted = strength.weibull_fit(with_inf)
    assert fitted.values["sample_count"] == 6


def test_거의_같으면_형상_계수를_의심한다() -> None:
    near = [
        Member(label=f"S{index}", values={"max_force": 50.0 + 1e-4 * index})
        for index in range(6)
    ]
    fitted = strength.weibull_fit(near)
    assert fitted.values["weibull_shape"] > 100
    assert any("보기 어렵게 큽니다" in one for one in fitted.warnings)


def test_묶음으로_등록된다() -> None:
    plugin = registry.get("weibull.strength")
    assert plugin.kind == "grouping"
    assert "adhesion" in plugin.applies_to
