"""Johnson-Cook 준정적 항 — **이름이 불완전함을 말하는가, 그리고 MT 가 데인 두 자리.**

확장은 `extensions/johnson_cook_static/` 하나이고 중심 코드는 안 고쳤다
(`test_ext_ghosh.py` 와 같은 구조 — 시험을 확장 폴더 밖에 두는 이유도 거기 있다).

이 식은 MaterialTwin 에 있던 것을 가져온 것인데, **거기서 이미 두 번 데였다.**
그 둘이 이 파일의 핵심이다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, fitting

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"

# 운영과 같은 길로 읽는다. 두 번 불러도 안전하다 — 이미 읽은 것은 건너뛴다.
extensions.load(EXTENSIONS)

KEY = "johnson_cook_static"


def curve(
    parameters: list[float], top: float = 0.20, points: int = 40
) -> tuple[np.ndarray, np.ndarray]:
    strain = np.linspace(0.0, top, points)
    stress = fitting.FAMILIES[KEY].evaluate(np.asarray(parameters, dtype=np.float64), strain)
    return strain, np.asarray(stress, dtype=np.float64)


class Test붙었나:
    def test_폴더_하나로_등록된다(self) -> None:
        assert KEY in fitting.FAMILIES
        assert fitting.FAMILIES[KEY].block == "hardening"
        assert fitting.FAMILIES[KEY].x_column == "strain_true_plastic"

    def test_금속에만_선다(self) -> None:
        assert KEY in {item.key for item in fitting.families_for("Metal")}
        assert KEY not in {item.key for item in fitting.families_for("Rubber")}

    def test_이름이_준정적임을_말한다(self) -> None:
        """**「Johnson-Cook」 이라고만 적으면 거짓말이 된다.**

        상온 곡선 하나에 3파라미터를 맞춘 것인데, 읽는 사람은 속도·온도 의존이
        든 물성으로 받는다. key 와 라벨과 설명 셋 다 그것을 말해야 한다 — 카드에
        실리는 것은 라벨이고, 화면에 뜨는 것은 설명이다.
        """
        family = fitting.FAMILIES[KEY]
        assert family.key.endswith("_static")
        assert "준정적" in family.label
        assert "속도항" in family.describe and "온도항" in family.describe


class Test계산:
    def test_계수가_되돌아온다(self) -> None:
        truth = [350e6, 600e6, 0.25]
        strain, stress = curve(truth)
        got = fitting.fit(KEY, strain, stress)
        for item, expected in zip(got.parameters, truth, strict=True):
            assert item.value == pytest.approx(expected, rel=1e-3)
        assert got.relative_rmse < 1e-6

    def test_A_가_항복강도로_읽힌다(self) -> None:
        """**이 식을 쓰는 이유다.** Swift 의 `K·ε₀^n` 은 그렇게 안 읽힌다."""
        truth = [350e6, 600e6, 0.25]
        strain, stress = curve(truth)
        got = fitting.fit(KEY, strain, stress)
        first = {item.name: item.value for item in got.parameters}["a"]
        assert first == pytest.approx(truth[0], rel=1e-3)
        assert first == pytest.approx(float(np.min(stress)), rel=1e-3)

    def test_접선이_수치_미분과_맞다(self) -> None:
        family = fitting.FAMILIES[KEY]
        values = np.asarray([350e6, 600e6, 0.25])
        grid = np.asarray([0.05, 0.5, 1.0])
        step = 1e-7
        numeric = (
            family.evaluate(values, grid + step) - family.evaluate(values, grid - step)
        ) / (2 * step)
        assert np.max(np.abs(family.tangent(values, grid) - numeric) / np.abs(numeric)) < 1e-5

    def test_외삽_구간에서_연화하지_않는다(self) -> None:
        """접선 `B·n·ε^(n-1)` 은 늘 양수다 — 멱함수형이라 계속 오른다."""
        strain, stress = curve([350e6, 600e6, 0.25])
        got = fitting.fit(KEY, strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.5, points=20)
        assert not any("접선이 음수" in note for note in extended.notes)


class TestMaterialTwin_이_데인_자리:
    """MT `fitting.py` 의 `johnson_cook_card_params` 주석에 적힌 두 함정."""

    def test_A_가_음수로_발산하지_않는다(self) -> None:
        """> 자유 3파라미터 J-C 피팅은 A·B가 상호식별 불가라 A가 음수로 발산하곤 한다.

        작은 ε 에서 `A` 와 `B·ε^n` 이 서로를 흡수해 데이터를 똑같이 맞추는 조합이
        무수히 많다. MT 는 A 를 밖에서 항복강도로 **고정**해 막았다.

        우리는 고정하지 않고 경계로 묶는다 — 적합에 들어오는 것이 이미 소성
        가지라(`plastic_branch`) **최소 응력이 곧 항복강도**여서 주입할 필요가 없다.

        경화가 거의 없어 A·B 가 가장 심하게 섞이는 데이터로 본다.
        """
        strain, stress = curve([400e6, 5e6, 0.9])
        got = fitting.fit(KEY, strain, stress)
        found = {item.name: item.value for item in got.parameters}
        assert found["a"] > 0.0
        assert found["a"] == pytest.approx(float(np.min(stress)), rel=0.06)

    def test_경화가_없어도_조용히_완전소성으로_안_떨어진다(self) -> None:
        """> 초기값이 경계를 벗어나면 curve_fit이 'infeasible'로 즉시 실패해
        > **카드가 조용히 완전소성(B=0)으로 떨어지던** 문제.

        **적합이 실패한 것과 재료가 그런 것은 다르다.** 평평한 곡선을 줘도 적합
        자체는 돌아야 하고, 그 사실은 R² 가 말해야 한다 — 파라미터가 0 으로
        주저앉아 아무 말 없이 나가면 안 된다.
        """
        strain = np.linspace(0.0, 0.2, 40)
        stress = np.full_like(strain, 400e6)
        got = fitting.fit(KEY, strain, stress)
        found = {item.name: item.value for item in got.parameters}
        assert found["b"] >= 1.0, "B 가 하한 아래로 내려갔습니다 — 경계가 안 걸렸습니다."
        assert found["a"] == pytest.approx(400e6, rel=0.06)

    def test_잡음이_섞여도_적합이_실패하지_않는다(self) -> None:
        """MT 가 실패하던 조건이 '감소·가속 경화나 잡음' 이었다."""
        rng = np.random.default_rng(20260907)
        strain, stress = curve([350e6, 600e6, 0.25])
        noisy = stress * rng.normal(1.0, 0.02, size=stress.shape)
        got = fitting.fit(KEY, strain, noisy)
        assert got.r_squared > 0.9
