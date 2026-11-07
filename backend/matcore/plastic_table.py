"""실측 공칭 응력-변형률 곡선 → *MAT_024 소성 표 — **합성이 아니라 잰 곡선에서** (2026-11-08).

문헌 덱은 곡선이 필요한 형식(*MAT_024)에 스칼라(E · 항복 · 인장 · 연신율)로 지은 곡선을
실었다(`matcore.synth`). 문헌 카탈로그에 응력-변형률 한 벌이 저장되면(ADR 0067) 그 곡선이
이긴다 — 지은 곡선은 모양을 지어내지만 잰 곡선은 그 재료의 모양이다.

## 변환은 처리 단계와 같은 식 · 같은 항복 정의

    true_strain = ln(1 + e) · true_stress = s(1 + e) · plastic = true_strain - true_stress/E

`tensile.true_plastic` 의 기본(`proof_stress`)과 같이 **0.2 % 오프셋 항복부터** 싣는다 —
곡선이 오프셋 선(ε - σ/E = 0.002)을 넘는 자리를 보간해 첫 줄 (0, 진항복)에 앉히고, 뒤의
점은 식 그대로다. E 는 **카드의 탄성 블록이 쓰는 그 값**이다 — 곡선의 기울기로 따로 재면
카드 안에서 탄성과 소성이 서로 다른 재료가 된다.

## 최대 응력에서 자른다

진응력 변환은 균일 변형을 전제한다. 공칭 응력이 가장 큰 점(인장강도) 뒤는 네킹이라 그 식이
성립하지 않는다 — 그 점까지만 싣는다. 처리 단계는 자를 곳을 사람이 정하지만 문헌 곡선에는 고를
화면이 없어 인장강도 점으로 정했다.

## 표는 단조 증가

솔버는 뒤섞인 표를 조용히 보간한다. 진응력 · 소성변형률이 함께 늘지 않는 점은 뺀다(합성 표와
같은 규칙).

DB 도 HTTP 도 모른다(matcore 규칙). 값은 전부 SI(Pa · 무차원 변형률)다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: 항복 정의 — 0.2 % 오프셋(Rp0.2). 처리 단계 항복강도의 기본과 같다.
OFFSET = 0.002

#: 표로 옮길 최소 점 수. 첫 줄(항복)과 그 뒤 한 점이면 표지만, 곡선이라고 부르려면 셋은
#: 있어야 한다.
MIN_POINTS = 3


@dataclass(frozen=True)
class MeasuredTable:
    rows: tuple[dict[str, float], ...]
    """`{plastic_strain, true_stress}` — 첫 줄은 (0, 진항복), 둘 다 단조 증가."""
    yield_stress: float
    """공칭 0.2 % 오프셋 항복(Pa) — 곡선에서 보간했다."""
    yield_strain: float
    """그 자리의 공칭 변형률."""
    cut_strain: float | None
    """최대 응력 점에서 잘랐으면 그 공칭 변형률. 끝 점이 최대면 None."""
    first_is_yield: bool
    """곡선이 오프셋 선 위에서 시작했다 — 탄성 구간이 안 실린 곡선이라 첫 점을 항복으로
    봤다."""


def from_nominal(
    strain: np.ndarray | list[float],
    stress: np.ndarray | list[float],
    youngs_modulus: float,
) -> MeasuredTable | str:
    """공칭 곡선 → 소성 표. 못 옮기면 **까닭 글자**(덱 각주에 그대로 실린다)."""
    if youngs_modulus <= 0:
        return f"탄성계수가 양수가 아닙니다({youngs_modulus:g} Pa)."
    x = np.asarray(strain, dtype=np.float64)
    y = np.asarray(stress, dtype=np.float64)
    keep = np.isfinite(x) & np.isfinite(y) & (x >= 0) & (y >= 0)
    x, y = x[keep], y[keep]
    order = np.argsort(x, kind="stable")
    x, y = x[order], y[order]
    # 같은 변형률이 둘이면 앞의 것 — 한 x 에 두 응력이면 표가 아니다.
    unique = np.concatenate(([True], np.diff(x) > 0)) if len(x) else np.array([], dtype=bool)
    x, y = x[unique], y[unique]
    if len(x) < MIN_POINTS:
        return f"곡선의 점이 {len(x)}개라 소성 표로 옮기지 않았습니다(셋 이상 필요)."

    offset = x - y / youngs_modulus
    past = np.flatnonzero(offset >= OFFSET)
    if not len(past):
        return (
            "곡선이 0.2 % 오프셋 항복에 이르지 않습니다 — 탄성 구간뿐이라 소성 표가 없습니다"
            f"(E = {youngs_modulus / 1e9:.4g} GPa 기준)."
        )
    at = int(past[0])
    peak = int(np.argmax(y))
    if peak < at:
        return (
            f"공칭 응력이 항복 전에 가장 큽니다(최대 {y[peak] / 1e6:.4g} MPa) — 항복 뒤가 "
            "연화뿐이라 "
            "소성 표로 옮기지 않았습니다."
        )
    if at == 0:
        yield_strain, yield_stress = float(x[0]), float(y[0])
    else:
        # 오프셋 선을 넘는 자리를 두 점 사이에서 보간한다 — 점 간격이 곧 항복의 오차가 되지
        # 않게.
        before, after = offset[at - 1], offset[at]
        share = (OFFSET - before) / (after - before)
        yield_strain = float(x[at - 1] + share * (x[at] - x[at - 1]))
        yield_stress = float(y[at - 1] + share * (y[at] - y[at - 1]))

    rows: list[dict[str, float]] = [
        {"plastic_strain": 0.0, "true_stress": yield_stress * (1.0 + yield_strain)}
    ]
    for e, s in zip(x[at : peak + 1], y[at : peak + 1], strict=True):
        true_stress = float(s * (1.0 + e))
        plastic = float(np.log1p(e) - true_stress / youngs_modulus)
        if plastic <= rows[-1]["plastic_strain"] or true_stress <= rows[-1]["true_stress"]:
            continue
        rows.append({"plastic_strain": plastic, "true_stress": true_stress})
    if len(rows) < 2:
        return "항복 뒤에 응력이 오르는 점이 없어 소성 표로 옮기지 않았습니다."
    return MeasuredTable(
        rows=tuple(rows),
        yield_stress=yield_stress,
        yield_strain=yield_strain,
        cut_strain=float(x[peak]) if peak < len(x) - 1 else None,
        first_is_yield=at == 0,
    )
