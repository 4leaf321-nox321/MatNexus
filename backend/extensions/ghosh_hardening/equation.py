"""Ghosh 경화식 — **Swift 를 아래로 내린 것.**

    σ = K(ε₀ + ε)^n - p

Swift 가 `K(ε₀+ε)^n` 이므로 상수 `p` 만큼 내린 꼴이다. 그래서 큰 변형에서 Swift 와
같은 기울기로 오르되 **낮은 값에서 오른다** — 외삽에서 Voce(포화)와 Swift(멱함수)
사이에 놓인다.

## 65 의 매개변수화를 안 따랐다

65 `metal_hardening.py` 의 Ghosh 는 `K(ε₀ - ε)^(-δ)` 이고 `ε < ε₀` 를 요구한다.
**ε 가 ε₀ 에 다가가면 발산한다.**

우리 쓰임과 안 맞는다. 여기서 경화식을 쓰는 첫 자리가 **외삽**인데(v1.46.0),
발산하는 식으로 소성변형률 1.0 까지 늘리면 정의 자체가 안 된다. 널리 쓰이는
`K(ε₀+ε)^n - p` 를 넣는다 — 판재 성형 문헌에서 Ghosh 로 인용되는 형태다.

**둘은 다른 식이므로 같은 이름을 쓰는 것이 걸린다.** 다만 65 와 우리가 같은 이름을
쓴다고 계수가 오갈 일이 없다(카드는 우리 것만 읽는다). 이 사연을 여기 적어 둔다.

## 접선은 Swift 와 같다

`dσ/dε = K·n·(ε₀+ε)^(n-1)` — 상수 `p` 는 미분에서 사라진다. 그래서 **연화 검사는
Swift 와 똑같이 통과한다**(늘 양수). 외삽에서 안전한 쪽이다.
"""

from __future__ import annotations

import numpy as np


def evaluate(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    k, epsilon_0, n, p = parameters
    base = np.maximum(epsilon_0 + np.asarray(strain, dtype=np.float64), 1e-12)
    return np.asarray(k * np.power(base, n) - p, dtype=np.float64)


def tangent(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """`p` 는 상수라 미분에서 사라진다 — Swift 와 같은 접선이다."""
    k, epsilon_0, n, _p = parameters
    base = np.maximum(epsilon_0 + np.asarray(strain, dtype=np.float64), 1e-12)
    return np.asarray(k * n * np.power(base, n - 1.0), dtype=np.float64)


def guess(strain: np.ndarray, stress: np.ndarray) -> np.ndarray:
    """**Swift 자리에서 시작한다**(`p = 0`). 거기서 아래로 내려가며 맞춘다."""
    top = float(np.max(stress))
    return np.asarray([top if top > 0 else 1.0, 0.005, 0.2, 0.0], dtype=np.float64)


def bounds(strain: np.ndarray, stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`p` 의 상한이 최소 응력이다.

    더 크게 두면 적합 구간 안에서 **응력이 음수인 곡선**이 나올 수 있다. 곡선은
    그려지지만 뜻이 없고, 그 카드로 만든 덱은 솔버가 거절한다.
    """
    top = float(np.max(stress))
    low = float(np.min(stress))
    return (
        np.asarray([0.0, 1e-9, 1e-4, 0.0], dtype=np.float64),
        np.asarray([top * 10.0, 1.0, 1.0, max(low, 1.0)], dtype=np.float64),
    )
