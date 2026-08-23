"""확장 폴더로 붙인 첫 물성 — **ADR 0013 이 실제로 되는지.**

`extensions/ghosh_hardening/` 하나로 경화식이 붙는다. 중심 코드는 한 줄도 안 고쳤다.

## 시험이 왜 확장 폴더 안에 없나

거기 두면 **pytest 가 확장을 한 번 더 읽는다.** `testpaths` 에 `extensions` 를
더하면 pytest 는 그 폴더를 `sys.path` 에 얹고 `ghosh_hardening.test_x` 로 읽는데,
그 순간 `__init__.py` 가 돌아 식이 등록된다. 그다음 확장 로더가 같은 폴더를
`matnexus_ext.ghosh_hardening` 으로 읽으면 **같은 key 가 둘**이 된다.

실제로 재 봤다:

    ValueError: 적합식 key 중복: ghosh

**레지스트리가 제 일을 한 것이다** — 같은 key 가 둘이면 어느 쪽이 도는지 알 수
없으니 거절하는 게 맞다. 그래서 시험은 여기 두고, 확장은 **운영과 같은 길로**
읽어서 본다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, fitting

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"

# 운영과 같은 길로 읽는다. 두 번 불러도 안전하다 — 이미 읽은 것은 건너뛴다.
extensions.load(EXTENSIONS)


def curve(
    parameters: list[float], top: float = 0.20, points: int = 40
) -> tuple[np.ndarray, np.ndarray]:
    strain = np.linspace(0.0, top, points)
    stress = fitting.FAMILIES["ghosh"].evaluate(
        np.asarray(parameters, dtype=np.float64), strain
    )
    return strain, np.asarray(stress, dtype=np.float64)


class Test붙었나:
    def test_폴더_하나로_등록된다(self) -> None:
        """**중심 코드를 한 줄도 안 고쳤다.** 그것이 ADR 0013 의 주장이다."""
        assert "ghosh" in fitting.FAMILIES
        assert fitting.FAMILIES["ghosh"].label == "Ghosh"

    def test_재료군을_선언한다(self) -> None:
        assert "ghosh" in {item.key for item in fitting.families_for("Metal")}
        assert "ghosh" not in {item.key for item in fitting.families_for("Rubber")}

    def test_경화식_자리에_담긴다(self) -> None:
        family = fitting.FAMILIES["ghosh"]
        assert family.block == "hardening"
        assert family.x_column == "strain_true_plastic"


class Test계산:
    def test_계수가_되돌아온다(self) -> None:
        truth = [700e6, 0.005, 0.2, 80e6]
        strain, stress = curve(truth)
        got = fitting.fit("ghosh", strain, stress)
        for item, expected in zip(got.parameters, truth, strict=True):
            assert item.value == pytest.approx(expected, rel=1e-3)
        assert got.relative_rmse < 1e-6

    def test_접선이_수치_미분과_맞다(self) -> None:
        """**Swift 와 같은 접선이다** — 상수 `p` 는 미분에서 사라진다."""
        family = fitting.FAMILIES["ghosh"]
        values = np.asarray([700e6, 0.005, 0.2, 80e6])
        grid = np.asarray([0.05, 0.5, 1.0])
        step = 1e-7
        numeric = (
            family.evaluate(values, grid + step) - family.evaluate(values, grid - step)
        ) / (2 * step)
        assert np.max(np.abs(family.tangent(values, grid) - numeric) / np.abs(numeric)) < 1e-5

    def test_외삽에서_Voce_와_Swift_사이에_놓인다(self) -> None:
        """Swift 를 상수만큼 내린 것이라 그 아래, 포화형인 Voce 보다는 위다.

        **외삽에서 고를 것이 하나 는다** — 두 식 사이가 비어 있었다.
        """
        strain, stress = curve([700e6, 0.005, 0.2, 80e6])
        ends = {}
        for family in ("voce", "ghosh", "swift"):
            got = fitting.fit(family, strain, stress)
            ends[family] = fitting.extend_table(got, strain, stress, to=1.0, points=10).points[
                -1
            ][1]
        assert ends["voce"] < ends["ghosh"] < ends["swift"]

    def test_외삽_구간에서_연화하지_않는다(self) -> None:
        """접선이 늘 양수다 — 큰 변형까지 늘려도 해석이 발산하지 않는다."""
        strain, stress = curve([700e6, 0.005, 0.2, 80e6])
        got = fitting.fit("ghosh", strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.5, points=20)
        assert not any("접선이 음수" in note for note in extended.notes)
