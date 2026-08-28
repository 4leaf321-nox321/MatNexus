"""Prony 급수 적합 — 마스터커브를 해석이 쓸 수 있는 형태로.

마스터커브는 그래프다. 해석기가 먹는 것은 **계수 몇 개**다. 일반화 Maxwell
모형이 그 다리다.

    E'(ω)  = E∞ + Σ Eᵢ·(ωτᵢ)² / (1 + (ωτᵢ)²)
    E''(ω) =      Σ Eᵢ·(ωτᵢ)  / (1 + (ωτᵢ)²)

저장·손실을 **함께** 맞춘다. 하나만 맞추면 나머지 하나가 틀린 계수가 나오는데,
그 계수로 만든 카드는 해석에서 감쇠를 엉뚱하게 준다.

## 항 수를 사람이 안 정해도 된다

몇 항이 맞는지는 곡선을 봐야 아는 것이고, 사람도 대개 몇 개 해 보고 고른다.
그래서 후보를 여럿 맞춰 보고 **BIC 로 고른다** — 항을 늘리면 잔차는 언제나
줄어들지만 계수도 늘어난다. BIC 가 그 둘을 저울질한다.

고른 것만 주지 않고 **후보를 전부 준다.** 사람이 "3항이면 충분한데 왜 6항을
골랐지" 를 볼 수 있어야 한다 — 경화식 견주기와 같은 판단이다.

## 관측 밖의 τ 는 근거가 없다

완화시간의 기본 범위를 관측 주파수에서 정한다(`1/ω`). 그 밖의 τ 는 데이터가
말해 주지 않는 값이고, 맞춘 값이 경계에 붙으면 **외삽하고 있다는 뜻**이라
경고한다. 65 도 같은 검사를 갖고 있다(`_at_bound`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

#: 기본으로 재 볼 항 수. 1항은 물성이라기보다 상수이고, 10항을 넘으면 계수가
#: 데이터 점보다 많아지기 시작한다(실측 마스터커브는 점 200개 안팎).
DEFAULT_CANDIDATES = (2, 3, 4, 5, 6, 7, 8)

#: 맞춘 τ 가 경계에 이만큼 가까우면 "경계에 붙었다" 로 본다(로그 자릿수).
BOUND_MARGIN = 0.05

#: 최적화 반복 상한.
MAX_EVALUATIONS = 20_000


class PronyError(Exception):
    """이 적합을 이 입력에 적용할 수 없다. 메시지는 **사용자가 읽는다.**"""


@dataclass(frozen=True)
class PronyTerm:
    modulus_pa: float
    relaxation_time_s: float


@dataclass(frozen=True)
class PronySeries:
    """맞춘 계수와 **그것을 얼마나 믿을 수 있는지.**"""

    equilibrium_pa: float
    """ω→0 에서 남는 탄성률. 고무 상태의 값이다."""
    terms: tuple[PronyTerm, ...]
    normalized_rmse: float
    """정규화 잔차. 탄성률 크기와 무관하게 비교할 수 있다."""
    bic: float
    """항 수를 고르는 기준. **작을수록 좋다.**"""
    at_bound: tuple[float, ...] = ()
    """경계에 붙은 완화시간. 있으면 **관측 밖을 외삽하고 있다.**"""

    @property
    def instantaneous_pa(self) -> float:
        """ω→∞ 에서의 탄성률. 유리 상태의 값이다."""
        return self.equilibrium_pa + sum(term.modulus_pa for term in self.terms)

    @property
    def relative_moduli(self) -> tuple[float, ...]:
        """`gᵢ = Eᵢ / E₀`. **Abaqus `*VISCOELASTIC` 이 이 형태를 먹는다.**

        절대 탄성률이 아니라 비율로 주는 규약이라, 카드를 만들 때 여기서 바로
        가져간다. 합이 1 을 넘으면 평형 탄성률이 음수라는 뜻이다.
        """
        total = self.instantaneous_pa
        if total <= 0:
            raise PronyError("순간 탄성률이 양수가 아닙니다. 계수를 확인하세요.")
        return tuple(term.modulus_pa / total for term in self.terms)


def storage_loss(
    series: PronySeries, frequency_hz: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """계수로 저장·손실 탄성률을 되만든다. 맞춘 것을 겹쳐 그릴 때 쓴다."""
    omega = 2.0 * math.pi * np.asarray(frequency_hz, dtype=float)
    taus = np.asarray([term.relaxation_time_s for term in series.terms])
    moduli = np.asarray([term.modulus_pa for term in series.terms])
    omega_tau = omega[np.newaxis, :] * taus[:, np.newaxis]
    denominator = 1.0 + omega_tau**2
    storage = series.equilibrium_pa + np.sum(
        moduli[:, np.newaxis] * omega_tau**2 / denominator, axis=0
    )
    loss = np.sum(moduli[:, np.newaxis] * omega_tau / denominator, axis=0)
    return storage, loss


def _check(frequency_hz: np.ndarray, storage_pa: np.ndarray, loss_pa: np.ndarray) -> None:
    if len(frequency_hz) < 5:
        raise PronyError(
            f"점이 {len(frequency_hz)}개뿐입니다. 계수가 1+2n 개라 최소 5점은 있어야 합니다."
        )
    if len(storage_pa) != len(frequency_hz) or len(loss_pa) != len(frequency_hz):
        raise PronyError("주파수·저장·손실의 길이가 서로 다릅니다.")
    # **겹치는 주파수는 허용한다.** 전에는 엄격히 증가를 요구했는데, 시편
    # 여럿의 마스터커브를 모아 맞출 때(묶음 Prony) 같은 격자에서 잰 점들이
    # 그대로 겹친다 — 그건 오류가 아니라 **한 주파수를 여러 번 잰 것**이고,
    # 최소제곱은 그것을 그대로 받는다. 순서만 지키면 된다.
    if np.any(frequency_hz <= 0) or np.any(np.diff(frequency_hz) < 0):
        raise PronyError("주파수가 0 보다 크고 증가 순이어야 합니다.")
    if np.any(storage_pa <= 0):
        raise PronyError("저장 탄성률에 0 이하가 있습니다.")
    if np.any(loss_pa < 0):
        raise PronyError("손실 탄성률에 음수가 있습니다.")


def _fit_with_taus(
    *,
    omega: np.ndarray,
    observed_storage: np.ndarray,
    observed_loss: np.ndarray,
    scale: float,
    taus: np.ndarray,
) -> PronySeries:
    """τ 를 못 박고 **탄성률만** 맞춘다.

    남는 변수가 `E∞` 와 `Eᵢ` 뿐이고 모형이 그것들에 대해 선형이라, 자유 τ 보다
    훨씬 잘 수렴한다. 그래도 최소제곱을 쓰는 이유는 **음수를 막기 위해서다** —
    닫힌 해로 풀면 음의 탄성률이 나올 수 있고, 그건 물리적으로 없는 값이다.
    """
    if taus.size < 1:
        raise PronyError("고정할 완화시간이 하나도 없습니다.")
    if not np.all(np.isfinite(taus)) or np.any(taus <= 0):
        raise PronyError("완화시간은 모두 0 보다 커야 합니다.")

    terms = int(taus.size)
    omega_tau = omega[np.newaxis, :] * taus[:, np.newaxis]
    denominator = 1.0 + omega_tau**2
    storage_basis = omega_tau**2 / denominator
    loss_basis = omega_tau / denominator

    def predict(parameters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        equilibrium = parameters[0]
        moduli = parameters[1:]
        storage = equilibrium + np.sum(moduli[:, np.newaxis] * storage_basis, axis=0)
        loss = np.sum(moduli[:, np.newaxis] * loss_basis, axis=0)
        return storage, loss

    def residual(parameters: np.ndarray) -> np.ndarray:
        storage, loss = predict(parameters)
        return np.concatenate((storage - observed_storage, loss - observed_loss))

    equilibrium_start = max(float(np.min(observed_storage)) * 0.95, 1e-8)
    spread = max(float(np.max(observed_storage)) - equilibrium_start, 1e-6)
    ceiling = max(float(np.max(observed_storage)) * 2.0, 1.0)
    outcome = least_squares(
        residual,
        x0=np.concatenate((np.asarray([equilibrium_start]), np.full(terms, spread / terms))),
        bounds=(np.full(terms + 1, 1e-12), np.full(terms + 1, ceiling)),
        method="trf",
        ftol=1e-11,
        xtol=1e-11,
        gtol=1e-11,
        max_nfev=MAX_EVALUATIONS,
    )
    if not outcome.success or not np.all(np.isfinite(outcome.x)):
        raise PronyError(
            f"고정 완화시간 {terms}항 적합이 수렴하지 않았습니다({outcome.message})."
        )

    residuals = residual(outcome.x)
    count = len(residuals)
    rss = max(float(np.sum(residuals**2)), np.finfo(float).tiny)
    # **맞춘 것만 센다.** τ 는 사람이 준 값이라 자유도가 아니다 — 자유 τ 와
    # 같은 식으로 세면 BIC 가 고정 쪽을 부당하게 벌준다.
    parameters = 1 + terms
    return PronySeries(
        equilibrium_pa=float(outcome.x[0] * scale),
        terms=tuple(
            PronyTerm(float(modulus * scale), float(tau))
            for modulus, tau in zip(outcome.x[1:], taus, strict=True)
        ),
        normalized_rmse=math.sqrt(rss / count),
        bic=count * math.log(rss / count) + parameters * math.log(count),
        # τ 를 사람이 골랐으므로 경계 경고는 뜻이 없다.
        at_bound=(),
    )


def fit_prony(
    frequency_hz: np.ndarray,
    storage_pa: np.ndarray,
    loss_pa: np.ndarray,
    *,
    terms: int,
    minimum_tau_s: float | None = None,
    maximum_tau_s: float | None = None,
    fixed_taus_s: Sequence[float] | None = None,
) -> PronySeries:
    """항 수를 정해 한 벌 맞춘다. 저장·손실을 **함께** 본다.

    τ 범위를 안 주면 관측 주파수에서 정한다 — `1/ω` 의 범위다. 그 밖의 τ 는
    데이터가 말해 주지 않는다.

    ## `fixed_taus_s` — τ 를 못 박고 탄성률만 맞춘다

    **시편 여럿의 계수를 평균 내려면 이것이 있어야 한다.** τ 가 자유 변수이면
    시편마다 다른 값으로 수렴하고(항 수도 BIC 가 따로 고른다), 그러면 `E₁` 끼리
    평균 낸다는 말 자체가 성립하지 않는다 — 서로 다른 완화시간의 계수를 더하는
    것이 된다.

    τ 를 공통 격자로 못 박으면 각 시편의 스펙트럼이 **같은 축 위에** 놓이고,
    그때 비로소 항끼리 평균이 뜻을 갖는다.

    맞추는 것이 줄어드는 만큼 잔차는 커진다. 그건 당연하고, 대신 **비교할 수
    있는 값**이 나온다 — 무엇을 얻고 무엇을 잃는지 사람이 알아야 하므로
    `normalized_rmse` 를 그대로 돌려준다.
    """
    frequency_hz = np.asarray(frequency_hz, dtype=float)
    storage_pa = np.asarray(storage_pa, dtype=float)
    loss_pa = np.asarray(loss_pa, dtype=float)
    _check(frequency_hz, storage_pa, loss_pa)
    if terms < 1:
        raise PronyError(f"항 수는 1 이상이어야 합니다: {terms}")

    omega = 2.0 * math.pi * frequency_hz
    # **크기를 지운다.** 탄성률이 10¹¹ Pa 이면 잔차도 10¹¹ 스케일이라 최적화가
    # 수렴 판정을 못 한다. 정규화하면 잔차가 O(1) 이 된다.
    scale = float(np.max(storage_pa))
    observed_storage = storage_pa / scale
    observed_loss = loss_pa / scale

    lower_tau = minimum_tau_s if minimum_tau_s else 1.0 / float(np.max(omega))
    upper_tau = maximum_tau_s if maximum_tau_s else 1.0 / float(np.min(omega))
    if not 0 < lower_tau < upper_tau:
        raise PronyError(f"완화시간 범위가 잘못됐습니다: {lower_tau:g}~{upper_tau:g} s")

    if fixed_taus_s is not None:
        return _fit_with_taus(
            omega=omega,
            observed_storage=observed_storage,
            observed_loss=observed_loss,
            scale=scale,
            taus=np.asarray(sorted(float(one) for one in fixed_taus_s), dtype=float),
        )

    equilibrium_start = max(float(np.min(observed_storage)) * 0.95, 1e-8)
    spread = max(float(np.max(observed_storage)) - equilibrium_start, 1e-6)
    start = np.concatenate(
        (
            np.asarray([equilibrium_start]),
            np.full(terms, spread / terms),
            # τ 는 로그로 다룬다 — 자릿수가 여럿 걸쳐 있어서 선형으로 두면
            # 작은 τ 가 최적화에서 무시된다.
            np.log(np.geomspace(lower_tau, upper_tau, terms)),
        )
    )
    ceiling = max(float(np.max(observed_storage)) * 2.0, 1.0)
    lower = np.concatenate(
        (np.asarray([1e-12]), np.full(terms, 1e-12), np.full(terms, math.log(lower_tau)))
    )
    upper = np.concatenate(
        (np.asarray([ceiling]), np.full(terms, ceiling), np.full(terms, math.log(upper_tau)))
    )

    def predict(parameters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        equilibrium = parameters[0]
        moduli = parameters[1 : terms + 1]
        taus = np.exp(parameters[terms + 1 :])
        omega_tau = omega[np.newaxis, :] * taus[:, np.newaxis]
        denominator = 1.0 + omega_tau**2
        storage = equilibrium + np.sum(
            moduli[:, np.newaxis] * omega_tau**2 / denominator, axis=0
        )
        loss = np.sum(moduli[:, np.newaxis] * omega_tau / denominator, axis=0)
        return storage, loss

    def residual(parameters: np.ndarray) -> np.ndarray:
        storage, loss = predict(parameters)
        return np.concatenate((storage - observed_storage, loss - observed_loss))

    outcome = least_squares(
        residual,
        x0=start,
        bounds=(lower, upper),
        method="trf",
        ftol=1e-11,
        xtol=1e-11,
        gtol=1e-11,
        max_nfev=MAX_EVALUATIONS,
    )
    if not outcome.success or not np.all(np.isfinite(outcome.x)):
        raise PronyError(
            f"{terms}항 적합이 수렴하지 않았습니다({outcome.message}). "
            f"항 수를 줄이거나 마스터커브를 확인하세요."
        )

    equilibrium = float(outcome.x[0] * scale)
    moduli = outcome.x[1 : terms + 1] * scale
    taus = np.exp(outcome.x[terms + 1 :])
    order = np.argsort(taus)
    moduli, taus = moduli[order], taus[order]

    residuals = residual(outcome.x)
    count = len(residuals)
    rss = max(float(np.sum(residuals**2)), np.finfo(float).tiny)
    # BIC. 항을 늘리면 잔차는 언제나 줄지만 계수도 는다 — 그 둘을 저울질한다.
    parameters = 1 + 2 * terms
    bic = count * math.log(rss / count) + parameters * math.log(count)

    # **경계에 붙은 τ 는 외삽이다.** 데이터가 그 값을 정하지 못했는데 최적화가
    # 갈 데까지 간 것이다. 실패는 아니지만 말해야 한다.
    at_bound = tuple(
        float(value)
        for value in taus
        if abs(math.log(value) - math.log(lower_tau)) < BOUND_MARGIN
        or abs(math.log(value) - math.log(upper_tau)) < BOUND_MARGIN
    )
    return PronySeries(
        equilibrium_pa=equilibrium,
        terms=tuple(
            PronyTerm(float(modulus), float(tau))
            for modulus, tau in zip(moduli, taus, strict=True)
        ),
        normalized_rmse=math.sqrt(rss / count),
        bic=bic,
        at_bound=at_bound,
    )


def choose_prony(
    frequency_hz: np.ndarray,
    storage_pa: np.ndarray,
    loss_pa: np.ndarray,
    *,
    candidates: tuple[int, ...] = DEFAULT_CANDIDATES,
    minimum_tau_s: float | None = None,
    maximum_tau_s: float | None = None,
) -> tuple[PronySeries, tuple[PronySeries, ...]]:
    """후보를 여럿 맞춰 보고 BIC 로 고른다. `(고른 것, 전부)`.

    **고른 것만 주지 않는다.** 사람이 "3항이면 충분한데 왜 6항을 골랐지" 를 볼
    수 있어야 한다 — 경화식 견주기와 같은 판단이다.

    수렴하지 않은 후보는 건너뛴다. 전부 실패하면 그때 오류다 — 8항이 안 됐다고
    3항까지 못 쓰게 만들 이유가 없다.
    """
    if not candidates:
        raise PronyError("재 볼 항 수가 하나도 없습니다.")
    found: list[PronySeries] = []
    failures: list[str] = []
    for count in sorted(set(candidates)):
        try:
            found.append(
                fit_prony(
                    frequency_hz,
                    storage_pa,
                    loss_pa,
                    terms=count,
                    minimum_tau_s=minimum_tau_s,
                    maximum_tau_s=maximum_tau_s,
                )
            )
        except PronyError as exc:
            failures.append(f"{count}항: {exc}")
    if not found:
        raise PronyError("맞춘 후보가 하나도 없습니다 — " + " / ".join(failures))
    best = min(found, key=lambda item: item.bic)
    return best, tuple(found)
