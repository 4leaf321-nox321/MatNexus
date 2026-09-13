"""유변 식 — 점도 η 를 전단율 rate 의 함수로.

    Cross      η = η∞ + (η0 - η∞) / (1 + (λ·rate)^m)
    Carreau    η = η∞ + (η0 - η∞) · (1 + (λ·rate)²)^((n-1)/2)

둘 다 낮은 전단율에서 η0(영전단 점도)로 평평하고, 1/λ 근처에서 꺾여 전단 박화로
들어가며, 높은 전단율에서 η∞ 로 간다. 다른 것은 **꺾이는 모양**뿐이다 — Cross 는
로그-로그에서 기울기 -m 의 직선으로, Carreau 는 기울기 (n-1) 로 간다.

파라미터는 전부 SI(Pa·s, s, 무차원)다. 초기값은 데이터에서 읽는다 — η0 는 가장
낮은 전단율의 점도, η∞ 는 가장 높은 것, λ 는 점도가 절반으로 내린 자리의 역수.
"""

from __future__ import annotations

import numpy as np

# ── 공통 초기값 ─────────────────────────────────────────────────────────────


def _plateaus(rate: np.ndarray, viscosity: np.ndarray) -> tuple[float, float, float]:
    """(η0, η∞, λ) 를 데이터에서 읽는다. 전단율 오름차순이라고 본다."""
    eta0 = float(np.max(viscosity))
    eta_inf = float(np.min(viscosity))
    if eta_inf >= eta0:
        eta_inf = eta0 * 0.01
    half = eta_inf + 0.5 * (eta0 - eta_inf)
    below = np.nonzero(viscosity <= half)[0]
    positive = rate[rate > 0]
    if below.size and rate[below[0]] > 0:
        lam = 1.0 / float(rate[below[0]])
    elif positive.size:
        lam = 1.0 / float(np.sqrt(positive[0] * positive[-1]))
    else:
        lam = 1.0
    return eta0, eta_inf, lam


def _bounds(rate: np.ndarray, viscosity: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    eta0 = float(np.max(viscosity))
    positive = rate[rate > 0]
    fastest = float(positive[-1]) if positive.size else 1.0
    slowest = float(positive[0]) if positive.size else 1e-3
    lower = np.array([eta0 * 0.5, 0.0, 0.01 / fastest, 0.0])
    upper = np.array([eta0 * 20.0, eta0, 100.0 / slowest, 1.0])
    return lower, upper


# ── Cross ───────────────────────────────────────────────────────────────────


def cross_evaluate(parameters: np.ndarray, rate: np.ndarray) -> np.ndarray:
    eta0, eta_inf, lam, m = parameters
    x = np.asarray(rate, dtype=np.float64)
    result: np.ndarray = eta_inf + (eta0 - eta_inf) / (1.0 + np.power(lam * x, m))
    return result


def cross_guess(rate: np.ndarray, viscosity: np.ndarray) -> np.ndarray:
    eta0, eta_inf, lam = _plateaus(rate, viscosity)
    return np.array([eta0, eta_inf, lam, 0.7])


def cross_bounds(rate: np.ndarray, viscosity: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lower, upper = _bounds(rate, viscosity)
    upper[3] = 2.0  # m 은 1 을 넘기도 한다
    return lower, upper


# ── Carreau ─────────────────────────────────────────────────────────────────


def carreau_evaluate(parameters: np.ndarray, rate: np.ndarray) -> np.ndarray:
    eta0, eta_inf, lam, n = parameters
    x = np.asarray(rate, dtype=np.float64)
    result: np.ndarray = eta_inf + (eta0 - eta_inf) * np.power(
        1.0 + np.square(lam * x), (n - 1.0) / 2.0
    )
    return result


def carreau_guess(rate: np.ndarray, viscosity: np.ndarray) -> np.ndarray:
    eta0, eta_inf, lam = _plateaus(rate, viscosity)
    return np.array([eta0, eta_inf, lam, 0.4])


def carreau_bounds(rate: np.ndarray, viscosity: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return _bounds(rate, viscosity)


# ── 적합 전 다듬기 ──────────────────────────────────────────────────────────


def prepare(
    rate: np.ndarray, viscosity: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """전단율·점도가 양수인 점만. 전단율 0 은 로그 축에 없고, 점도 0 이하는 잰 값이 아니다."""
    x = np.asarray(rate, dtype=np.float64)
    y = np.asarray(viscosity, dtype=np.float64)
    keep = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    dropped = int(x.size - keep.sum())
    notes = [f"전단율·점도가 0 이하인 점 {dropped}개를 뺐습니다."] if dropped else []
    order = np.argsort(x[keep], kind="stable")
    return x[keep][order], y[keep][order], notes


def zero_shear(parameters: np.ndarray) -> dict[str, float]:
    """식이 달라도 견줄 수 있는 값 — 영전단 점도와 꺾이는 전단율(1/λ)."""
    eta0, _eta_inf, lam, _ = parameters
    return {
        "zero_shear_viscosity": float(eta0),
        "onset_shear_rate": float(1.0 / lam) if lam > 0 else float("inf"),
    }
