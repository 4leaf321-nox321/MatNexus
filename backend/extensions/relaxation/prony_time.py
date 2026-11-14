"""응력완화 → 완화 탄성률 E(t)(처리), 여러 시험 → 시간 영역 Prony(묶음). 2026-10-12.

    E(t) = σ(t) / ε₀                                   ε₀ 는 유지 변형률
    E(t) = E∞ + Σ Eᵢ · exp(-t/τᵢ)                      일반화 Maxwell — DMA 의 Prony 와
                                                       같은 계수

## τ 를 못 박고 Eᵢ 만 맞춘다

τ 를 관측 시간 범위에 **자릿수마다 하나** 깔고, E∞ · Eᵢ ≥ 0 을 비음수 최소제곱(NNLS)으로 푼다.
τ 까지 자유롭게 두는 비선형 적합은 출발점마다 다른 답으로 가고 항 수도 사람이 골라야 한다 —
자릿수 격자는 그 둘을 없애고, 쓸모없는 항은 Eᵢ = 0 으로 저절로 빠진다. 잔차는 **상대**로 본다
(E 로 나눈다) — 완화가 두세 자릿수 진행되면 절대 잔차로는 긴 시간 쪽이 안 보인다.

## 순간 탄성률은 첫 측정까지만 안다

하중을 거는 동안 풀린 몫은 파일에 없다. 그래서 가장 짧은 τ 는 **첫 측정 시각**이고, 그보다
빠른 완화는 이 카드에 없다 — 그 사실을 경고로 남긴다. 순간 탄성률이 첫 측정 때 강성의 몇 배인지
(`instantaneous_ratio`)를 값으로 내고, 1.5배를 넘으면 카드 · 덱 머리말에 외삽이라고 적는다
(2026-11-14, VOC 52). 카드의 탄성계수는 이 Prony 의 순간
탄성률(E∞ + ΣEᵢ)이다 — 점탄성 덱이 E 를 순간 값으로 읽고 gᵢ 를 곱하기 때문에, 다른 E 가
서면 장기 탄성률이 조용히 다른 배수가 된다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.optimize import nnls

from matcore.cards.viscoelastic import INSTANTANEOUS_RATIO_WARN
from matcore.groups import GroupError, GroupOutcome, Member
from matcore.processing import Frame, ProcessingError, Scalar, StepResult

TIME = "time"
STRESS = "stress"
STRAIN = "strain"
MODULUS = "relaxation_modulus"
NORMALIZED = "normalized_stress"
TEMPERATURE = "temperature"

#: 자릿수마다 τ 하나. 항이 이보다 많으면 점이 모자라기 시작한다.
MAX_TERMS = 12
MIN_POINTS = 8
#: 같은 온도로 보는 폭(K) — 넘으면 **묶지 않는다**(2026-11-15).
SAME_TEMPERATURE = 2.0
#: 가장 긴 τ 의 몫이 이보다 크면 「아직 다 안 풀렸다」 — 장기 탄성률이 외삽이다.
LONG_TAIL = 0.05


# ── 시험 하나 ─────────────────────────────────────────────────────────────


def relaxation_modulus(frame: Frame, options: dict[str, Any]) -> StepResult:
    """처리 단계 — E(t) = σ/ε₀ 와 σ/σ₀."""
    time = np.asarray(frame.require(str(options.get("time") or TIME), what="시간"), float)
    stress = np.asarray(
        frame.require(str(options.get("stress") or STRESS), what="응력"), float
    )
    order = np.argsort(time, kind="stable")
    time, stress = time[order], stress[order]
    notes: list[str] = []
    held = options.get("held_strain")
    measured = frame.columns.get(str(options.get("strain") or STRAIN))
    if measured is not None and len(measured):
        strain = float(np.mean(np.asarray(measured, float)))
        notes.append(f"유지 변형률은 변형률 열의 평균 {strain:.5g} 입니다.")
        if isinstance(held, int | float) and held > 0 and abs(strain - held) > 0.05 * held:
            notes.append(
                f"조건의 유지 변형률 {held:.5g} 과 5% 넘게 다릅니다 — 잰 값(열)을 썼습니다."
            )
    elif isinstance(held, int | float):
        strain = float(held)
        notes.append(f"유지 변형률은 시험 조건의 {strain:.5g} 입니다.")
    else:
        raise ProcessingError(
            "유지 변형률을 모릅니다 — 변형률 열이 없으면 시험 조건 「유지 변형률」 을 "
            "적으세요."
        )
    if strain <= 0:
        raise ProcessingError(f"유지 변형률이 {strain:g} 입니다 — 0 보다 커야 합니다.")
    if stress[0] <= 0:
        raise ProcessingError(
            "첫 응력이 0 이하입니다 — 완화가 시작되는 점을 찾을 수 없습니다."
        )
    modulus = stress / strain
    normalized = stress / stress[0]
    notes.append(
        "시간은 파일 그대로입니다 — 변형률 유지를 시작한 때가 0 이어야 Prony 의 τ 가 맞습니다."
    )
    sorted_frame = Frame(
        {key: np.asarray(value)[order] for key, value in frame.columns.items()},
        dict(frame.units),
    )
    return StepResult(
        frame=sorted_frame.with_columns(
            {MODULUS: modulus, NORMALIZED: normalized}, {MODULUS: "Pa", NORMALIZED: "1"}
        ),
        notes=tuple(notes),
        scalars=(
            Scalar(
                "relaxation_initial_modulus", "첫 측정의 완화 탄성률", float(modulus[0]), "Pa"
            ),
            Scalar("relaxation_final_modulus", "마지막 완화 탄성률", float(modulus[-1]), "Pa"),
            Scalar("relaxed_fraction", "풀린 몫", float(1.0 - normalized[-1]), "1"),
            Scalar("hold_time", "유지 시간", float(time[-1] - time[0]), "s", "time"),
            Scalar("held_strain_used", "쓴 유지 변형률", strain, "1", "strain"),
        ),
    )


# ── 여러 시험 ─────────────────────────────────────────────────────────────


def taus(time_min: float, time_max: float) -> np.ndarray:
    """가장 짧은 τ 는 첫 측정 시각, 그 위로 자릿수마다 하나 — t_min, 10^k … 10^⌈log t_max⌉.

    **첫 측정보다 짧은 τ 를 깔지 않는다**(2026-11-14, VOC 52). 전에는 10^⌊log t_min⌋ 부터라
    측정 구간에서 거의 다 풀린 항이 생겼고, 그 크기를 데이터가 못 정해 적합이 마음대로 키웠다 —
    첫 측정이 0.95 s 면 E₀ 1145 GPa, 1.0 s 면 2.19 GPa(539배)였다. 가장 짧은 τ 가 t_min
    이상이면 E₀ / E(t_min) 은 e(≈2.7) 를 넘지 못하고, 첫 측정 시각이 조금 달라도 결과가 뛰지
    않는다. t_min 에 너무 붙은 자릿수(2배 안)는 뺀다 — 거의 같은 두 항은 서로를 못 가른다.
    """
    high = math.ceil(math.log10(time_max))
    decades = [
        10.0**power
        for power in range(math.ceil(math.log10(time_min)), high + 1)
        if 10.0**power > 2 * time_min
    ]
    grid = [time_min, *decades]
    if len(grid) > MAX_TERMS:
        grid = grid[-MAX_TERMS:]
    return np.asarray(grid, float)


def fit(
    time: np.ndarray, modulus: np.ndarray
) -> tuple[float, list[tuple[float, float]], float]:
    """`(E∞, [(τ, Eᵢ)], 상대 RMSE)` — Eᵢ = 0 인 항은 뺀다."""
    grid = taus(float(time.min()), float(time.max()))
    design = (
        np.column_stack([np.ones_like(time), *(np.exp(-time / tau) for tau in grid)])
        / modulus[:, np.newaxis]
    )
    solution, _ = nnls(design, np.ones_like(time))
    model = design @ solution
    rmse = float(np.sqrt(np.mean((model - 1.0) ** 2)))
    terms = [
        (float(tau), float(e)) for tau, e in zip(grid, solution[1:], strict=True) if e > 0
    ]
    return float(solution[0]), terms, rmse


def relaxation_prony(members: list[Member]) -> GroupOutcome:
    """시편들의 E(t) 를 모아 Prony 한 벌."""
    times: list[np.ndarray] = []
    moduli: list[np.ndarray] = []
    temperatures: list[float] = []
    used: list[str] = []
    for member in members:
        time = np.asarray(member.columns.get(TIME, ()), float)
        modulus = np.asarray(member.columns.get(MODULUS, ()), float)
        keep = (time > 0) & (modulus > 0)
        if int(keep.sum()) < 2:
            raise GroupError(f"{member.label}: 시간 > 0 인 완화 탄성률 점이 없습니다.")
        times.append(time[keep])
        moduli.append(modulus[keep])
        found = member.values.get(TEMPERATURE)
        if isinstance(found, int | float):
            temperatures.append(float(found))
        used.append(member.label)
    # **온도가 섞이면 묶지 않는다**(2026-11-15, VOC 52). 전에는 옮기지 않은 채 한데 맞추고
    # 경고만 달아 카드까지 냈다 — 20 · 40 · 60 °C 를 넣으면 40 °C 로 적힌 카드가 그 온도의
    # 참값과 1.72배 틀렸다(합성 실측, 상대 RMSE 37 %). DMA 묶음은 0.5 K 만 달라도 막는다.
    if temperatures and max(temperatures) - min(temperatures) > SAME_TEMPERATURE:
        raise GroupError(
            f"시험 온도가 {min(temperatures):.5g}~{max(temperatures):.5g} K 로 섞여 "
            f"있습니다({SAME_TEMPERATURE:g} K 넘게 다름) — 한 Prony 는 한 온도의 것입니다. "
            "온도마다 따로 묶으세요."
        )
    time = np.concatenate(times)
    modulus = np.concatenate(moduli)
    if len(time) < MIN_POINTS:
        raise GroupError(
            f"완화 탄성률 점이 {len(time)}개입니다 — {MIN_POINTS}개 이상 있어야 합니다."
        )
    if float(time.max()) / float(time.min()) < 10:
        raise GroupError("관측 시간이 한 자릿수가 안 됩니다 — 완화시간을 정할 수 없습니다.")
    equilibrium, terms, rmse = fit(time, modulus)
    if not terms:
        raise GroupError("완화가 보이지 않습니다 — 응력이 시간에 따라 줄지 않습니다.")
    instantaneous = equilibrium + sum(e for _, e in terms)
    earliest = float(time.min())
    at_earliest = equilibrium + sum(e * math.exp(-earliest / tau) for tau, e in terms)
    ratio = instantaneous / at_earliest if at_earliest > 0 else float("inf")
    warnings = [
        f"순간 탄성률은 가장 이른 측정(t = {earliest:.3g} s)까지만 압니다 — 하중을 거는 "
        "동안 풀린 몫은 이 카드에 없습니다."
    ]
    if ratio > INSTANTANEOUS_RATIO_WARN:
        warnings.append(
            f"순간 탄성률 E₀ 가 첫 측정(t = {earliest:.3g} s) 때 강성의 {ratio:.2f}배입니다 — "
            "그 앞은 외삽입니다. 짧은 시간(충격) 해석에는 DMA 마스터커브로 짧은 시간을 메워야 "
            "합니다."
        )
    longest_tau, longest = max(terms)
    if longest_tau >= float(time.max()) and longest / instantaneous > LONG_TAIL:
        warnings.append(
            f"가장 긴 완화시간({longest_tau:.3g} s)이 관측 끝을 넘고 몫이 "
            f"{longest / instantaneous:.0%} "
            "입니다 — 아직 다 안 풀렸습니다. 장기 탄성률은 외삽입니다."
        )
    values: dict[str, float] = {
        "equilibrium_pa": equilibrium,
        "instantaneous_pa": instantaneous,
        "normalized_rmse": rmse,
        "term_count": float(len(terms)),
        "point_count": float(len(time)),
        "time_min": float(time.min()),
        "time_max": float(time.max()),
        "instantaneous_ratio": float(ratio),
    }
    if temperatures:
        values["reference_temperature_k"] = float(np.mean(temperatures))
    return GroupOutcome(
        values=values,
        detail={"terms": [{"relaxation_time_s": tau, "modulus_pa": e} for tau, e in terms]},
        warnings=warnings,
        used=used,
    )


# ── 카드 ──────────────────────────────────────────────────────────────────


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 결과 → 점탄성 블록 + 탄성계수(순간 탄성률). gᵢ = Eᵢ / E₀."""
    terms = list(detail.get("terms") or [])
    instantaneous = values.get("instantaneous_pa")
    if not terms or not isinstance(instantaneous, int | float) or instantaneous <= 0:
        raise ValueError("이 묶음에 Prony 항이 없습니다.")
    kept = ("equilibrium_pa", "instantaneous_pa", "reference_temperature_k", "normalized_rmse")
    # **잰 시간 범위와 외삽 배수를 카드에 둔다**(2026-11-14, VOC 52) — 묶음 값에만 있고
    # 카드에서 버려져, 덱을 받은 사람은 이 Prony 가 몇 초부터 몇 초까지 잰 것인지 몰랐다.
    renamed = {
        "time_min": "time_min_s",
        "time_max": "time_max_s",
        "instantaneous_ratio": "instantaneous_ratio",
    }
    measured = {
        new: float(values[old])
        for old, new in renamed.items()
        if isinstance(values.get(old), int | float)
    }
    return {
        "viscoelastic": {
            "values": {
                **{key: float(values[key]) for key in kept if key in values},
                **measured,
            },
            "rows": [
                {
                    "relaxation_time_s": float(one["relaxation_time_s"]),
                    "modulus_pa": float(one["modulus_pa"]),
                    "relative_modulus": float(one["modulus_pa"]) / float(instantaneous),
                }
                for one in terms
            ],
            "notes": list(warnings),
        },
        # 점탄성 덱이 E 를 순간 값으로 읽는다 — 이 Prony 의 순간 탄성률이 그 E 다. 푸아송비 ·
        # 밀도는 중심이 물려받는다(이 블록은 E 칸만 이긴다).
        "elastic": {
            "values": {"youngs_modulus": float(instantaneous)},
        },
    }
