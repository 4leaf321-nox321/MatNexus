"""곡선 점검 — 잰 곡선처럼 생겼나(2026-11-17, ADR 0096).

잰 공칭 곡선             원점에서 탄성 → 꺾여 경화, 잡음 → nominal
크로스헤드 곡선          초기 기울기가 영률의 1/4 → nominal, 기울기는 info
앞부분이 잘린 잰 곡선    첫 점이 탄성 직선 중간(최대의 34 %) → nominal, 첫 점 info (SPCC)
소성 표                  변형률 0 에 σy → plastic_table
항복점에서 시작          탄성 직선 위 항복점에서 바로 경화(데모 곡선) → plastic_table
표에서 다시 만든 곡선    점 사이가 정확히 직선 → rebuilt
"""

from __future__ import annotations

import numpy as np

from matcore import curve_quality as cq

E = 200e9
EY = 300e6 / E
RNG = np.random.default_rng(1)


def _verdicts(quality: cq.Quality) -> dict[str, str]:
    return {one.key: one.verdict for one in quality.checks}


def test_잰_공칭_곡선() -> None:
    strain = np.linspace(0, 0.15, 3000)
    stress = np.where(strain < EY, E * strain, 300e6 + 800e6 * (strain - EY))
    stress = stress + RNG.normal(0, 1e6, len(strain))
    made = cq.assess(strain, stress, reference_modulus=E)
    assert made.shape == "nominal"
    assert _verdicts(made)["first_point"] == "ok"
    assert _verdicts(made)["initial_slope"] == "ok"
    assert "piecewise" not in _verdicts(made)  # 잡음이 있으면 점 사이가 정확히 직선이 아니다


def test_크로스헤드_곡선은_기울기만_info() -> None:
    strain = np.linspace(0, 0.15, 3000)
    knee = 4 * EY
    stress = np.where(
        strain < knee, 0.25 * E * strain, 0.25 * E * knee + 800e6 * (strain - knee)
    ) + RNG.normal(0, 1e6, len(strain))
    made = cq.assess(strain, stress, reference_modulus=E)
    assert made.shape == "nominal"
    assert _verdicts(made)["initial_slope"] == "info"


def test_앞부분이_잘린_잰_곡선은_공칭이다() -> None:
    """개발 DB 의 SPCC — 처리 곡선이 탄성 구간 중간(206 MPa, 최대의 34 %)에서 시작한다."""
    strain = [0.00111, 0.00315, 0.0038, 0.01, 0.03, 0.06, 0.1, 0.15, 0.2, 0.25]
    stress = [206.6e6, 376.1e6, 383.4e6, 420e6, 480e6, 530e6, 570e6, 595e6, 604.3e6, 600e6]
    made = cq.assess(strain, stress)
    assert made.shape == "nominal"
    assert _verdicts(made)["first_point"] == "info"


def test_소성_표는_plastic_table() -> None:
    strain = np.linspace(0, 0.2, 40)
    stress = 300e6 + 600e6 * (1 - np.exp(-strain / 0.05))
    made = cq.assess(strain, stress, reference_modulus=E)
    assert made.shape == "plastic_table"
    assert _verdicts(made)["first_point"] == "warn"


def test_항복점에서_바로_경화하면_plastic_table() -> None:
    """개발 DB 의 데모 곡선(SCATTER_DP600) — 탄성 직선 위 항복점에서 시작해 바로 눕는다. 영률이
    없어도 가른다."""
    strain = EY + np.linspace(0, 0.15, 160)
    stress = 357e6 + 600e6 * (1 - np.exp(-(strain - EY) / 0.05))
    made = cq.assess(strain, stress)
    assert made.shape == "plastic_table"
    assert _verdicts(made)["first_point"] == "warn"


def test_표에서_다시_만든_곡선은_rebuilt() -> None:
    plastic = np.linspace(0, 0.2, 40)
    table = 300e6 + 600e6 * (1 - np.exp(-plastic / 0.05))
    nodes_x = np.concatenate([[0, EY], EY + plastic[1:]])
    nodes_y = np.concatenate([[0, 300e6], table[1:]])
    grid = np.linspace(0, nodes_x[-1], 500)
    made = cq.assess(grid, np.interp(grid, nodes_x, nodes_y), reference_modulus=E)
    assert made.shape == "rebuilt"
    assert _verdicts(made)["piecewise"] == "info"


def test_점이_모자라면_말하지_않는다() -> None:
    made = cq.assess([0.0, 0.01], [0.0, 1e8])
    assert made.shape == "unclear" and made.checks[0].key == "points"
