"""Johnson-Cook 의 **준정적·상온 항** — 속도항·온도항을 1 로 둔 것.

    완전한 식   σ = [A + B·εp^n] · [1 + C·ln(ε̇*)] · [1 - T*^m]
    여기서 내는 것            ↑ 이 괄호 하나

`A + B·εp^n` 은 Ludwik 식이기도 하다. 이름을 `johnson_cook_static` 으로 둔 것은
**완전한 JC 가 아니라는 것을 이름이 말하게** 하기 위해서다 — 상온 곡선 하나에
3파라미터를 맞춰 놓고 카드에 「Johnson-Cook」 이라고 적으면, 읽는 사람은 속도·온도
의존이 든 물성으로 받는다.

## 나머지 두 항은 어디 있나

**속도항 C 는 이미 우리가 낸다.** `matcore/groups/rate.py` 의 속도 묶음이 인장
시험 여럿을 변형률속도로 갈라 `σ/σ₀ = 1 + C·ln(ε̇/ε̇₀)` 을 맞춘다(`jc_c`). 여기서
내는 A·B·n 과 그 C 가 함께 있어야 완전한 JC 카드가 된다.

**온도항 m 은 못 낸다.** 같은 재료를 여러 온도로 당긴 데이터가 있어야 하고, 지금은
상온뿐이다. 속도 묶음도 같은 이유로 온도를 안 가른다.

## Swift 와 다른 식이다

    Swift              K(ε₀ + ε)^n        ε=0 에서 유한한 응력
    Johnson-Cook 정적   A + B·ε^n          ε=0 에서 **정확히 A**(항복)

A 가 항복강도로 바로 읽힌다는 것이 이 식의 쓸모다. Swift 의 `K·ε₀^n` 은 그렇게
읽히지 않는다.

## A 를 자유롭게 두면 발산한다

MaterialTwin 이 데인 자리다(`fitting.py` 의 `johnson_cook_card_params`):

> 자유 3파라미터 J-C 피팅은 **A·B가 상호식별 불가라 A가 음수로 발산**하곤 한다.

작은 ε 에서 `A` 와 `B·ε^n` 이 서로를 흡수해서, 데이터를 똑같이 잘 맞추는 (A, B, n)
조합이 무수히 많다. 그래서 MT 는 A 를 항복강도로 **고정**했다.

우리는 고정하지 않고 **경계로 묶는다.** 적합에 들어오는 데이터가 이미 소성 가지라
(`fitting.plastic_branch` 가 마지막 0 점 = 항복점만 남긴다) **최소 응력이 곧
항복강도**다. 밖에서 값을 주입할 필요가 없고, 오히려 데이터에 더 붙는다.

## B·n 경계도 함께 묶는다

MT 가 같은 자리에서 겪은 두 번째 함정:

> 초기값을 경계 `[B≥1, 0≤n≤1]` 안으로 클램프 — 감소·가속 경화나 노이즈로 log-log
> 기울기가 경계를 벗어나면 curve_fit이 'infeasible'로 즉시 실패해 **카드가 조용히
> 완전소성(B=0)으로 떨어지던** 문제 방지.

조용히 틀린 답이 나가는 쪽이라 경계에 박아 둔다.
"""

from __future__ import annotations

import numpy as np

#: A 를 항복강도 둘레 이만큼 안에서만 움직이게 한다. 완전히 고정하지 않는 것은
#: 항복점 한 점에 잡음이 있을 수 있어서다 — 묶되 데이터가 조금은 말하게 둔다.
_YIELD_BAND = 0.05


def evaluate(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    a, b, n = parameters
    # **바닥을 1e-12 로 깔지 않는다.** `0^n` 은 numpy 에서 정확히 0 이라 σ(0)=A 가
    # 그대로 나온다. 작은 값을 깔면 n=0.25 에서 `(1e-12)^0.25 = 1e-3` 이라 B 의
    # 0.1% 가 A 에 얹혀, **A 가 항복강도로 정확히 읽히지 않는다**(시험이 물었다).
    # 음수만 막는다 — 음의 소성변형률에 분수 거듭제곱은 nan 이다.
    base = np.maximum(np.asarray(strain, dtype=np.float64), 0.0)
    return np.asarray(a + b * np.power(base, n), dtype=np.float64)


def tangent(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """`dσ/dε = B·n·ε^(n-1)`.

    n < 1 이라 ε→0 에서 **+∞ 극한**이다(Hockett-Sherby 와 같은 성격). 늘 양수이므로
    외삽에서 연화하지 않는다 — 멱함수형이라 큰 변형에서도 계속 오른다.
    """
    _a, b, n = parameters
    base = np.maximum(np.asarray(strain, dtype=np.float64), 1e-12)
    return np.asarray(b * n * np.power(base, n - 1.0), dtype=np.float64)


def guess(strain: np.ndarray, stress: np.ndarray) -> np.ndarray:
    """A 는 항복(최소 응력), B 는 경화 폭, n 은 흔한 값에서 시작한다.

    **log-log 회귀로 B·n 을 미리 재지 않는다.** MT 는 그렇게 해서 초기값이 경계를
    벗어나면 적합이 통째로 실패했다. 여기서는 경계 안의 안전한 자리에서 출발하고,
    최소제곱이 알아서 간다.
    """
    low = float(np.min(stress))
    top = float(np.max(stress))
    return np.asarray([low if low > 0 else 1.0, max(top - low, 1.0), 0.2], dtype=np.float64)


def bounds(strain: np.ndarray, stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`A` 를 항복 둘레로 묶는다 — 위 docstring 의 상호식별 문제.

    `B ≥ 1` 은 완전소성(B=0)으로 주저앉는 것을 막는다. 진짜로 경화가 없는 재료라면
    B 가 하한에 붙고 R² 가 그것을 말한다 — **적합이 실패하는 것과 재료가 그런 것은
    다르고, 그 둘을 구별할 수 있어야 한다.**
    """
    low = float(np.min(stress))
    top = float(np.max(stress))
    if low <= 0.0:
        low = max(top, 1.0)
    return (
        np.asarray([low * (1.0 - _YIELD_BAND), 1.0, 1e-4], dtype=np.float64),
        np.asarray([low * (1.0 + _YIELD_BAND), top * 10.0, 1.0], dtype=np.float64),
    )
