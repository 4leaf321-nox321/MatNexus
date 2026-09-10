"""탄성계수를 **격자점으로 재면 안 된다** — 그 사실을 말하는가.

## 무슨 일이 있었나 (2026-09-11 VOC)

*"항복점까지의 포인트가 적어서 기본값 400포인트로는 탄성계수 계산에 필요한 점
개수가 부족하다."*

표준 레시피가 재샘플(400점)을 탄성계수 **앞**에 두고 있었다. 금속은 항복이
변형률 0.002 언저리인데 곡선은 0.4 까지 간다 — 400점을 전 구간에 고르게 뿌리면
**항복 전에는 한두 점**만 남는다. 개발 DB 의 실제 곡선 5건이 전부 그렇게
막혔다(띠 안 0~1점).

## 왜 「점 수를 늘린다」 가 답이 아닌가

같은 곡선을 4000점으로 재샘플하면 띠 안에 6~12점이 들어와 값이 **나온다.**
그런데 잰 점이 18개뿐인 곡선에서도 나온다 — 그 점들은 두 잰 점 사이를 직선으로
이은 자리라 **새 정보가 없고**, 직선 위의 점이라 R² 도 1 에 붙는다.

    MIN_TRUSTWORTHY_POINTS   보간된 점이 채워 준다   → 뚫린다
    MIN_TRUSTWORTHY_R_SQUARED  직선 위의 점이라 1     → 뚫린다

두 방어가 함께 뚫리는 것이 이 파일이 있는 이유다. 값을 막지는 않는다(촘촘한
곡선을 재샘플한 것이면 기울기는 맞다) — 대신 **점 수의 뜻이 달라졌다는 것을
반드시 말한다.**
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from matcore import processing
from matcore.processing.tensile import _uniform_grid

processing.load_builtin()

MODULUS = processing.Step("tensile.elastic_modulus", {"method": "auto"})


def curve(
    points: int, *, modulus: float = 200e9, yield_stress: float = 4e8
) -> tuple[Any, Any]:
    """탄성 뒤 완전소성인 곡선. 항복 변형률은 `yield_stress / modulus` 다."""
    x = np.linspace(0.0, 0.4, points)
    y = np.minimum(x * modulus, yield_stress)
    return x, y


def frame_of(x: Any, y: Any) -> processing.Frame:
    return processing.Frame({"strain_engineering": x, "stress_engineering": y}, {})


def notes_of(frame: processing.Frame) -> str:
    return " ".join(processing.apply([MODULUS], frame).notes)


class Test격자_알아보기:
    def test_균등_격자를_알아본다(self) -> None:
        assert _uniform_grid(np.linspace(0.0, 0.4, 400)) == 400

    def test_잰_점은_격자가_아니다(self) -> None:
        """장비는 고른 간격으로 안 찍는다 — 한 점만 어긋나도 격자가 아니다."""
        x = np.linspace(0.0, 0.4, 400)
        x[7] += 1e-4
        assert _uniform_grid(np.sort(x)) == 0

    def test_점이_둘뿐이면_판단하지_않는다(self) -> None:
        """두 점은 언제나 「간격이 같다」 — 그것으로 격자라고 말할 수 없다."""
        assert _uniform_grid(np.array([0.0, 0.1])) == 0


class Test격자_위에서_쟀을_때:
    def test_값이_나와도_격자라고_말한다(self) -> None:
        """**여기가 조용히 틀리는 자리다.** 71점·R²=1 이 화면에 뜨는데 그 점들은
        잰 점이 아니다."""
        x, y = curve(18)
        grid = np.linspace(0.0, 0.4, 4000)
        said = notes_of(frame_of(grid, np.interp(grid, x, y)))
        assert "균등 격자로 재샘플된 것" in said
        assert "보간된 점" in said

    def test_못_냈을_때도_격자라고_말한다(self) -> None:
        """「곡선이 성깁니다」 만 적으면 다시 잴 수 없다고 읽는다 — 사실은 잰 점을
        우리가 버린 것이다."""
        x, y = curve(4000)
        grid = np.linspace(0.0, 0.4, 60)
        said = notes_of(frame_of(grid, np.interp(grid, x, y)))
        assert "탄성계수를 내지 않았습니다" in said
        assert "이 단계 뒤로" in said

    def test_잰_점으로_쟀으면_그런_말을_안_한다(self) -> None:
        """잔소리를 붙이지 않는다 — 늘 뜨는 경고는 아무도 안 읽는다."""
        # 장비는 고른 간격으로 안 찍는다. **아주 조금 흔들려도 격자가 아니다** —
        # 되로 재는 문턱(관측 폭의 1e-9)이 그만큼 좁아 잰 곡선이 걸릴 일은 없다.
        x, y = curve(4000)
        shaken = np.sort(x + np.random.default_rng(0).normal(0, 1e-7, x.size))
        said = notes_of(frame_of(shaken, np.interp(shaken, x, y)))
        assert "균등 격자" not in said


class Test순서가_값을_가른다:
    """**표준 레시피의 순서가 곧 이 값의 존폐다.**

    같은 곡선, 같은 단계인데 재샘플이 앞이냐 뒤냐로 값이 나오고 안 나온다.
    프론트의 `standard.ts` 가 그 순서를 든다.
    """

    def _steps(self, resample_first: bool) -> list[processing.Step]:
        grid = processing.Step(
            "curve.resample", {"x": "strain_engineering", "count": 400, "start": 0}
        )
        return [grid, MODULUS] if resample_first else [MODULUS, grid]

    def test_재샘플이_앞이면_값이_안_나온다(self) -> None:
        x, y = curve(4000)
        got = processing.apply(self._steps(True), frame_of(x, y))
        assert "youngs_modulus" not in {one.key for one in got.scalars}

    def test_뒤로_보내면_나온다(self) -> None:
        x, y = curve(4000)
        got = processing.apply(self._steps(False), frame_of(x, y))
        found = {one.key: one.value for one in got.scalars}
        assert found["youngs_modulus"] == pytest.approx(200e9, rel=1e-3)
