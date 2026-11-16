"""곡선 모양 · 근사 사본(`matcore.curves.shape` · `near_copy` · `copy_gap`, 2026-11-17,
VOC 54).

값 지문은 정확히 같은 값만 알아본다. 같은 측정인데 지문이 다른 사본 셋을 모양으로 알아보고,
따로 잰 시편은 알아보지 않는다(기준 `NEAR_COPY` 0.4 %).

    자릿수를 줄인 사본    엑셀로 열었다 저장 — 유효숫자 4자리
    점을 솎은 사본        장비가 10점에 하나만 내보냄(첫 점도 빠짐)
    단위 배수 사본        하중 단위를 kN 으로 잘못 적음 — SI 로 바꾸면 1000배
    다른 시편            강도 1 % · 연신 3 % 다르고 잡음이 다른 곡선 — 사본이 아니다
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import curves


def _tensile(
    points: int = 2000, *, strength: float = 3500.0, stretch: float = 0.02, seed: int = 1
) -> dict[str, list[float | None]]:
    rng = np.random.default_rng(seed)
    displacement = np.linspace(0.0, stretch, points)
    force = strength * np.tanh(displacement * 300) * (1 - 0.3 * (displacement / stretch) ** 4)
    force = force + rng.normal(0.0, 2.0, points)
    width = np.full(points, 0.0125)
    return {
        "displacement": [float(one) for one in displacement],
        "force": [float(one) for one in force],
        "specimen_width": [float(one) for one in width],
    }


def _gap(
    first: dict[str, list[float | None]], second: dict[str, list[float | None]]
) -> tuple[float, dict[str, float]]:
    a = curves.Shape.of(curves.shape(first))
    b = curves.Shape.of(curves.shape(second))
    assert a is not None and b is not None
    got = curves.copy_gap(a, b)
    assert got is not None, "견줄 수 있어야 한다"
    return got


def test_축은_늘기만_하는_열이고_점은_64개다() -> None:
    made = curves.shape(_tensile())
    assert made is not None
    assert made["lead"] == "displacement"
    grid = made["grid"]
    assert isinstance(grid, dict) and sorted(grid) == ["force", "specimen_width"]
    assert all(len(values) == curves.SHAPE_POINTS for values in grid.values())


def test_자릿수를_줄인_사본은_거의_같다() -> None:
    original = _tensile()
    rounded = {
        key: [None if one is None else float(f"{one:.4g}") for one in values]
        for key, values in original.items()
    }
    assert curves.fingerprint(rounded) != curves.fingerprint(original)
    gap, _ = _gap(original, rounded)
    assert gap < curves.NEAR_COPY


def test_점을_솎은_사본은_거의_같다() -> None:
    original = _tensile()
    thinned = {key: values[1::10] for key, values in original.items()}
    gap, factors = _gap(original, thinned)
    assert gap < curves.NEAR_COPY
    assert set(factors.values()) == {1.0}


def test_단위를_배수로_잘못_적은_사본은_배율과_함께_알아본다() -> None:
    original = _tensile()
    wrong = dict(original)
    wrong["force"] = [None if one is None else one * 1000 for one in original["force"]]
    gap, factors = _gap(original, wrong)
    assert gap < 1e-9
    assert factors["force"] == 1000.0 and factors["displacement"] == 1.0
    # 반대 방향으로 견줘도 배율은 「둘째가 첫째의 몇 배」 다.
    _, back = _gap(wrong, original)
    assert back["force"] == pytest.approx(1e-3)


def test_따로_잰_시편은_사본이_아니다() -> None:
    gap, _ = _gap(_tensile(), _tensile(strength=3535.0, stretch=0.0206, seed=2))
    assert gap > curves.NEAR_COPY


def test_축이나_채널이_다르면_견주지_않는다() -> None:
    a = curves.Shape.of(curves.shape(_tensile()))
    fewer = {key: values for key, values in _tensile().items() if key != "specimen_width"}
    b = curves.Shape.of(curves.shape(fewer))
    assert a is not None and b is not None
    assert curves.copy_gap(a, b) is None


def test_늘기만_하는_열이_없으면_행_차례로_잰다() -> None:
    wave: list[float | None] = [float(np.sin(index / 9)) for index in range(300)]
    made = curves.shape({"stress": wave})
    assert made is not None and made["lead"] is None
    scaled: list[float | None] = [None if one is None else one * 1e6 for one in wave]
    gap, factors = _gap({"stress": wave}, {"stress": scaled})
    assert gap < 1e-9 and factors["stress"] == 1e6


def test_빈_칸과_짧은_열은_빼고_깨진_모양은_견주지_않는다() -> None:
    assert curves.shape({"force": [1.0, None, 2.0]}) is None
    assert curves.Shape.of(None) is None
    assert (
        curves.Shape.of({"lead": "x", "low": 0, "high": 1, "grid": {"y": [1, 2, 3]}}) is None
    )
    assert curves.Shape.of({"grid": {"y": ["a"] * curves.SHAPE_POINTS}}) is None
