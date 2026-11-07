"""실측 공칭 곡선 → 소성 표 — **못 옮기는 곡선은 까닭을 말하고, 옮긴 표는 단조 증가.**

정상 경로(오프셋 항복 · 최대 응력에서 자름 · 식)는 덱 시험(`test_literature_curves`)이
손으로 푼 값과 견준다. 여기는 가장자리다.
"""

from __future__ import annotations

import pytest

from matcore import plastic_table

E = 200e9


def test_차례가_뒤섞이고_같은_변형률이_두_번이어도_같은_표() -> None:
    strain = [0.0, 0.001, 0.004, 0.01, 0.05, 0.1]
    stress = [0.0, 200e6, 260e6, 300e6, 380e6, 420e6]
    ordered = plastic_table.from_nominal(strain, stress, E)
    shuffled = plastic_table.from_nominal(
        [0.05, 0.0, 0.1, 0.004, 0.001, 0.01, 0.01],
        [380e6, 0.0, 420e6, 260e6, 200e6, 300e6, 999e6],
        E,
    )
    assert not isinstance(ordered, str) and not isinstance(shuffled, str)
    assert shuffled.rows == ordered.rows
    assert ordered.cut_strain is None  # 끝 점이 최대다


def test_탄성_구간_없이_시작하면_첫_점이_항복() -> None:
    made = plastic_table.from_nominal([0.01, 0.05, 0.1], [300e6, 380e6, 420e6], E)
    assert not isinstance(made, str)
    assert made.first_is_yield
    assert made.rows[0] == {"plastic_strain": 0.0, "true_stress": pytest.approx(300e6 * 1.01)}


@pytest.mark.parametrize(
    ("strain", "stress", "words"),
    [
        ([0.0, 0.001], [0.0, 200e6], "셋 이상"),
        ([0.0, 0.0005, 0.001], [0.0, 100e6, 200e6], "0.2 % 오프셋 항복에 이르지 않습니다"),
        # 오프셋을 넘기 전에 최대 — 항복 뒤가 연화뿐인 곡선.
        ([0.0, 0.001, 0.002, 0.01], [0.0, 200e6, 300e6, 100e6], "항복 전에 가장 큽니다"),
    ],
)
def test_못_옮기는_곡선은_까닭을_말한다(
    strain: list[float], stress: list[float], words: str
) -> None:
    made = plastic_table.from_nominal(strain, stress, E)
    assert isinstance(made, str) and words in made


def test_E_가_양수가_아니면_까닭() -> None:
    made = plastic_table.from_nominal([0.0, 0.01, 0.02], [0.0, 1e6, 2e6], 0.0)
    assert isinstance(made, str) and "탄성계수" in made
