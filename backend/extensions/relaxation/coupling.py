"""응력완화와 DMA 마스터커브를 **잇는다** — 짧은 시간은 DMA, 긴 시간은 응력완화.

2026-11-15, VOC 52 · ADR 0087 1단계.

## 왜

응력완화는 하중을 거는 동안(대개 첫 1 s 앞)을 모른다 — 순간 탄성률 E₀ 가 첫 측정 때 강성
근처에 묶인다(ADR 0081). 같은 재료의 DMA 마스터커브는 주파수 영역에서 그 짧은 시간을 잰다.
답을 아는 합성 재료(14항, E₀ 3 GPa)에서 응력완화만이면 E₀ 0.22 GPa(13.8배 낮음), 이으면
2.97 GPa 였다.

## 무엇을 하나 (사용자 결정 — 권장안)

1. 응력완화 시험들은 **한 온도**(±2 K)여야 한다 — T_R. DMA 는 대표 마스터커브 **하나**.
2. 마스터커브를 T_R 로 옮긴다 — 이동 상수(WLF · Arrhenius, 수동이면 잰 이동인자 보간)로
   a_T(T_R). 맞춘 온도 범위 밖이면 외삽이라 막는다. 전단(G′) 마스터커브는 E = 2(1+ν)G 로 옮긴
   뒤 같은 길로 잇는다 — ν 는 묶음 옵션 → 재료의 푸아송비 → 둘 다 없으면 막는다(2026-11-15,
   `dma.to_shear` · DMA 온도별 카드와 같은 규칙 — 값을 지어내지 않는다).
3. DMA Prony 는 **완화시간을 자릿수마다 못 박아** 다시 맞춘다(`pronykit.fit_decades`) — 자유
   τ 적합은 저주파 끝(긴 시간 — 바로 겹치는 쪽)에서 E′ 가 +40 % 틀렸다(VOC 52 조사).
   E_DMA(t, T_R) = E∞ + Σ Eᵢ · exp(-t / (τᵢ · a_T)).
4. **겹친 구간에서 대 본다** — 응력완화 점 중 DMA 가 덮는 시간 안의 것에서 비
   E_응력완화 / E_DMA 의 **중앙값**. 최댓값은 점이 몇 개뿐이라 같은 재료도 58 % 가 나왔다.
   5 % 넘으면 잇되 경고, 25 % 를 넘거나 겹친 점이 셋이 안 되면 막는다(잠정 — 실재료 쌍으로
   다시 정한다).
5. **한 벌로 맞춘다** — DMA 가 덮는 짧은 끝부터 DMA 창 끝의 1/10 까지 DMA 곡선을 자릿수마다
   열 점, 응력완화는 잰 점 전부. 두 쪽의 무게는 점 수와 무관하게 같게. 완화시간은 가장 짧은
   DMA 시간부터 마지막 측정까지 자릿수마다(시간 영역 Prony 와 같은 비음수 최소제곱, 상대 잔차).
6. 선형 구간 근거 — 재료의 선형점탄성 한계 변형률(DMA 변형률 스윕)이 있으면 유지 변형률과
   견주고, 없으면 「근거가 없다」 고 말한다(막지 않는다).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.optimize import nnls

from matcore import prony as pronykit
from matcore import viscoelastic as viscokit
from matcore.groups import GroupError, GroupOutcome, Member

from . import prony_time

#: 구성원이 어느 시험 종류에서 왔는가 — 중심이 `meta` 에 적는다(`grouping.services`).
TEST_TYPE_META = "test_type"
RELAXATION = "stress_relaxation"
#: 마스터커브 구성원의 열 이름 — 중심이 `frequency`·`storage_modulus`… 를 이렇게 옮겨 준다.
FREQUENCY, STORAGE, LOSS = "frequency_hz", "storage_pa", "loss_pa"
#: 마스터커브 구성원의 값 · meta 키.
REFERENCE = "reference_temperature_k"
SHIFT_META = "shift"
SHEAR_META = "shear"
#: 재료에서 모은 선형점탄성 한계 변형률(가장 작은 것) — 중심이 응력완화 구성원 값에 싣는다.
LVE_LIMIT = "lve_strain_limit"
HELD_STRAIN = "held_strain_used"
#: 전단 마스터커브를 E 로 옮길 푸아송비 — 묶음 옵션의 이름이자, 중심이 재료의 기본 칸을 실어
#: 주는 값 이름(`material_fields`). 실렸으면 구성원 `meta["from_material"]` 에 이름이 있다.
POISSON = "poisson_ratio"
#: ν 가 이 위면(고무 쪽) 전단 → E 변환의 오차를 따로 말한다.
NEAR_INCOMPRESSIBLE = 0.45
_POISSON_SOURCES = {"option": "묶음 옵션", "material": "재료에 적힌 값"}

#: 겹친 구간 비의 중앙값이 1 에서 이만큼 넘게 벗어나면 잇되 말한다 — **잠정값**.
OVERLAP_WARN = 0.05
#: 이만큼 넘게 벗어나면 잇지 않는다 — **잠정값**. 합성 실험에서 같은 재료 1.6 %, 로트 10 %
#: 차 13 %, 온도 기록 2 K 오차 12 %, 비선형 46 % 였다.
OVERLAP_BLOCK = 0.25
#: 겹친 구간에 응력완화 점이 이만큼은 있어야 견줄 수 있다.
MIN_OVERLAP_POINTS = 3
#: 이을 때 DMA 곡선을 자릿수마다 몇 점 넣나.
DMA_POINTS_PER_DECADE = 10
#: 완화시간 수 상한 — 이으면 13 자릿수쯤 된다(응력완화만이면 12, `prony_time`).
MAX_TERMS = 24
GAS_CONSTANT = 8.314462618


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _celsius(kelvin: float) -> str:
    return f"{kelvin - 273.15:.1f} °C"


def log10_shift(shift: Mapping[str, Any], reference_k: float, temperature_k: float) -> float:
    """마스터커브의 이동으로 log10 a_T(T). **맞춘 온도 범위 밖이면 막는다**(외삽)."""
    method = str(shift.get("method") or "")
    parameters = shift.get("parameters") or {}
    points = sorted(
        (float(one["temperature_k"]), float(one["log10_a_t"]))
        for one in shift.get("shifts") or []
        if _number(one.get("temperature_k")) is not None
        and _number(one.get("log10_a_t")) is not None
    )
    temperatures = [one for one, _ in points] or [reference_k]
    low, high = min(temperatures), max(temperatures)
    if not low - 0.5 <= temperature_k <= high + 0.5:
        raise GroupError(
            f"응력완화 온도 {_celsius(temperature_k)} 가 마스터커브의 이동을 맞춘 온도 "
            f"범위({_celsius(low)} ~ {_celsius(high)}) 밖입니다 — 옮기면 외삽이라 잇지 "
            "않습니다. 그 온도를 덮는 DMA 를 쓰세요."
        )
    delta = temperature_k - reference_k
    if abs(delta) < 1e-9:
        return 0.0
    if method == "wlf":
        c1, c2 = _number(parameters.get("c1")), _number(parameters.get("c2"))
        if c1 is None or c2 is None or c2 + delta <= 0:
            raise GroupError("마스터커브의 WLF 상수가 없거나 이 온도에서 발산합니다.")
        return -c1 * delta / (c2 + delta)
    if method == "arrhenius":
        energy = _number(parameters.get("activation_energy_j_per_mol"))
        if energy is None:
            raise GroupError("마스터커브의 Arrhenius 활성화 에너지가 없습니다.")
        slope = energy / (GAS_CONSTANT * math.log(10.0))
        return slope * (1 / temperature_k - 1 / reference_k)
    if len(points) < 2:
        raise GroupError("마스터커브의 이동인자를 몰라 응력완화 온도로 옮길 수 없습니다.")
    return float(np.interp(temperature_k, [t for t, _ in points], [a for _, a in points]))


def relaxation_at(series: pronykit.PronySeries, time_s: np.ndarray, a_t: float) -> np.ndarray:
    """주파수 영역 Prony → 그 온도의 시간 영역 E(t). 같은 계수라 변환이 정확하다."""
    time_s = np.asarray(time_s, dtype=float)
    out = np.full_like(time_s, series.equilibrium_pa)
    for term in series.terms:
        out = out + term.modulus_pa * np.exp(-time_s / (term.relaxation_time_s * a_t))
    return out


def _taus(time_min: float, time_max: float) -> np.ndarray:
    """가장 짧은 시간부터 자릿수마다 — `prony_time.taus` 와 같은 규칙, 상한만 넓다."""
    high = math.ceil(math.log10(time_max))
    decades = [
        10.0**power
        for power in range(math.ceil(math.log10(time_min)), high + 1)
        if 10.0**power > 2 * time_min
    ]
    grid = [time_min, *decades]
    return np.asarray(grid[-MAX_TERMS:], float)


def _split(members: Sequence[Member]) -> tuple[list[Member], Member]:
    relaxation = [one for one in members if one.meta.get(TEST_TYPE_META) == RELAXATION]
    curves = [one for one in members if one.meta.get(TEST_TYPE_META) != RELAXATION]
    if not relaxation:
        raise GroupError(
            "응력완화 시험이 없습니다 — 잇는 묶음은 응력완화 시험과 DMA 를 함께 고릅니다."
        )
    if len(curves) != 1:
        raise GroupError(
            f"DMA 마스터커브가 {len(curves)}개입니다 — 1단계는 마스터커브 하나와 잇습니다. "
            "DMA 시험을 하나만 고르세요."
        )
    return relaxation, curves[0]


def _relaxation_points(relaxation: Sequence[Member]) -> tuple[float, np.ndarray, np.ndarray]:
    """`(T_R, 시간, 완화 탄성률)` — 한 온도여야 한다."""
    temperatures = [
        float(one.values[prony_time.TEMPERATURE])
        for one in relaxation
        if _number(one.values.get(prony_time.TEMPERATURE)) is not None
    ]
    if len(temperatures) != len(relaxation):
        raise GroupError(
            "시험 온도를 모르는 응력완화 시험이 있습니다 — 마스터커브를 어느 온도로 옮길지 "
            "정할 수 없습니다. 시험 조건에 온도를 적으세요."
        )
    if max(temperatures) - min(temperatures) > prony_time.SAME_TEMPERATURE:
        raise GroupError(
            f"응력완화 시험 온도가 {min(temperatures):.5g}~{max(temperatures):.5g} K 로 섞여 "
            "있습니다 — 1단계는 한 온도씩 잇습니다."
        )
    times: list[np.ndarray] = []
    moduli: list[np.ndarray] = []
    for one in relaxation:
        time = np.asarray(one.columns.get(prony_time.TIME, ()), float)
        modulus = np.asarray(one.columns.get(prony_time.MODULUS, ()), float)
        keep = np.isfinite(time) & np.isfinite(modulus) & (time > 0) & (modulus > 0)
        if int(keep.sum()) < 2:
            raise GroupError(f"{one.label}: 시간 > 0 인 완화 탄성률 점이 없습니다.")
        times.append(time[keep])
        moduli.append(modulus[keep])
    time = np.concatenate(times)
    modulus = np.concatenate(moduli)
    order = np.argsort(time)
    return float(np.mean(temperatures)), time[order], modulus[order]


def _given_poisson(raw: Any) -> float | None:
    """묶음 옵션의 푸아송비. 비면 `None` — 글자로 온 숫자(MCP)도 읽고, 못 읽으면 막는다."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    value: Any = raw
    if isinstance(raw, str):
        try:
            value = float(raw)
        except ValueError:
            value = None
    found = _number(value)
    if found is None:
        raise GroupError(f"푸아송비 옵션을 숫자로 읽을 수 없습니다: {raw!r}")
    return found


def _shear_to_e(curve: Member, option: float | None) -> tuple[float, float, str]:
    """전단 마스터커브를 E 로 옮길 `(배수 2(1+ν), ν, 출처)` — 옵션 → 재료 → 없으면 막는다."""
    found = _number(curve.values.get(POISSON))
    if option is not None:
        poisson, source = option, "option"
    elif found is not None:
        poisson, source = found, "material"
    else:
        raise GroupError(
            f"{curve.label} 의 마스터커브는 전단(G′)으로 잰 것입니다 — E = 2(1+ν)G 로 "
            "옮기려면 푸아송비가 필요합니다. 묶음 옵션 「푸아송비」 에 넣거나 재료에 적으세요"
            "(값을 지어 넣지 않습니다)."
        )
    try:
        factor = viscokit.youngs_from_shear(poisson)
    except viscokit.ViscoelasticError as exc:
        raise GroupError(str(exc)) from exc
    return factor, poisson, source


def _master_curve(
    curve: Member, warnings: list[str], poisson_option: float | None = None
) -> tuple[pronykit.PronySeries, float, float, float, Mapping[str, Any], dict[str, Any]]:
    """`(자릿수마다 맞춘 Prony, 기준 온도, 최저 · 최고 주파수, 이동, 잰 탄성률)`.

    전단(G′)이면 저장 · 손실 탄성률에 2(1+ν) 를 곱해 E′ · E″ 로 옮긴 뒤 맞춘다 — 그 뒤는 인장 ·
    굽힘으로 잰 것과 같은 길이다. 잰 탄성률(`basis`)은 무엇을 어떻게 옮겼는지다.
    """
    basis: dict[str, Any] = {"shear": False, "label": "E′ (인장 · 굽힘 DMA)"}
    factor = 1.0
    if curve.meta.get(SHEAR_META):
        factor, poisson, source = _shear_to_e(curve, poisson_option)
        named = _POISSON_SOURCES[source]
        basis = {
            "shear": True,
            "poisson_ratio": poisson,
            "poisson_source": source,
            "label": f"G′ (전단 DMA) → E = 2(1+ν)G, ν = {poisson:g}({named})",
        }
        warnings.append(
            f"DMA 마스터커브({curve.label})는 전단(G′)으로 잰 것입니다 — E = 2(1+ν)G, "
            f"ν = {poisson:g}({named}) 로 옮겨 이었습니다. 등방 · 선형 탄성을 가정하고 ν 를 "
            "시간 · 온도에 상수로 둔 변환입니다. 카드를 만들 때 푸아송비를 같은 ν 로 두세요 "
            "— 덱이 카드의 ν 로 G = E/2(1+ν) 를 다시 만들어, 다르면 짧은 시간의 전단 탄성률이 "
            "잰 G′ 와 어긋납니다."
        )
        if poisson >= NEAR_INCOMPRESSIBLE:
            warnings.append(
                f"ν = {poisson:g} 는 0.5 에 가깝습니다(고무) — 이 변환의 오차가 커질 수 "
                "있습니다. 점탄성 재료의 ν 는 짧은 시간(유리질, 0.35 안팎)에서 긴 시간"
                "(고무질, 0.5 가까이)으로 변하는데 상수로 두었고, 덱이 E · ν 로 만드는 "
                "체적 탄성률 K = E/3(1-2ν) 은 ν 의 작은 차에도 크게 달라집니다."
            )
    elif poisson_option is not None:
        warnings.append(
            f"푸아송비 옵션({poisson_option:g})은 쓰지 않았습니다 — {curve.label} 의 "
            "마스터커브는 인장 · 굽힘(E′)으로 잰 것이라 E 로 옮길 것이 없습니다."
        )
    frequency = np.asarray(curve.columns.get(FREQUENCY, ()), float)
    storage = np.asarray(curve.columns.get(STORAGE, ()), float)
    loss = np.asarray(curve.columns.get(LOSS, ()), float)
    keep = np.isfinite(frequency) & np.isfinite(storage) & np.isfinite(loss) & (frequency > 0)
    frequency, storage, loss = frequency[keep], storage[keep], loss[keep]
    if len(frequency) < 5:
        raise GroupError(f"{curve.label} 의 마스터커브 점이 다섯이 안 됩니다.")
    order = np.argsort(frequency)
    frequency, storage, loss = frequency[order], storage[order], loss[order]
    storage, loss = storage * factor, loss * factor
    reference_k = _number(curve.values.get(REFERENCE))
    shift = curve.meta.get(SHIFT_META)
    if reference_k is None or not isinstance(shift, Mapping):
        raise GroupError(f"{curve.label} 의 마스터커브에 기준 온도 · 이동이 없습니다.")
    try:
        series = pronykit.fit_decades(frequency, storage, loss)
        if series is None:
            series, _ = pronykit.choose_prony(frequency, storage, loss)
            warnings.append(
                "마스터커브의 주파수 창이 좁아 완화시간을 자릿수마다 못 박지 못했습니다 — "
                "완화시간도 맞춘 적합으로 이었습니다(낮은 주파수 끝이 어긋날 수 있습니다)."
            )
    except pronykit.PronyError as exc:
        raise GroupError(
            f"{curve.label} 의 마스터커브에 Prony 를 맞추지 못했습니다: {exc}"
        ) from exc
    return series, reference_k, float(frequency.min()), float(frequency.max()), shift, basis


def _linear_range(relaxation: Sequence[Member], warnings: list[str]) -> None:
    """유지 변형률이 재료의 선형점탄성 한계 안인가 — 막지 않고 말한다."""
    held = [_number(one.values.get(HELD_STRAIN)) for one in relaxation]
    limits = [
        value
        for value in (_number(one.values.get(LVE_LIMIT)) for one in relaxation)
        if value is not None
    ]
    if not limits:
        warnings.append(
            "선형 구간 근거가 없습니다 — 이 재료의 DMA 변형률 스윕(선형점탄성 한계)이 채택돼 "
            "있지 않아, 응력완화의 유지 변형률이 선형 범위 안인지 확인하지 못했습니다."
        )
        return
    limit = min(limits)
    over = [value for value in held if value is not None and value > limit]
    if over:
        warnings.append(
            f"응력완화 유지 변형률 {max(over):.3g} 가 선형점탄성 한계 {limit:.3g} 를 넘습니다 "
            "— 비선형이면 응력완화가 더 빨리 풀려 두 곡선을 한 벌로 잇는 것이 맞지 않습니다."
        )


def couple(members: list[Member], poisson_ratio: Any = None) -> GroupOutcome:
    """응력완화 E(t) + DMA 마스터커브 → 짧은 시간부터 긴 시간까지 시간 영역 Prony 한 벌.

    `poisson_ratio` 는 전단(G′) 마스터커브를 E 로 옮길 ν — 비우면 재료에 적힌 값(중심이
    `material_fields` 로 싣는다)이고, 둘 다 없으면 막는다.
    """
    relaxation, curve = _split(members)
    warnings: list[str] = []
    target_k, relax_t, relax_e = _relaxation_points(relaxation)
    series, reference_k, f_low, f_high, shift, measured = _master_curve(
        curve, warnings, _given_poisson(poisson_ratio)
    )
    log_a = log10_shift(shift, reference_k, target_k)
    a_t = 10.0**log_a
    dma_lo = a_t / (2 * math.pi * f_high)
    dma_hi = a_t / (2 * math.pi * f_low)

    # ── 겹친 구간에서 대 본다 ──────────────────────────────────────────
    inside = (relax_t >= dma_lo) & (relax_t <= dma_hi)
    overlap = int(inside.sum())
    if overlap < MIN_OVERLAP_POINTS:
        raise GroupError(
            f"두 시험이 겹치는 시간대에 응력완화 점이 {overlap}개뿐입니다 — DMA 가 "
            f"{_celsius(target_k)} 에서 덮는 시간은 {dma_lo:.3g}~{dma_hi:.3g} s, 응력완화는 "
            f"{relax_t.min():.3g}~{relax_t.max():.3g} s 입니다. {MIN_OVERLAP_POINTS}개는 "
            "있어야 같은 것을 쟀는지 견줄 수 있습니다(응력완화 온도가 DMA 의 높은 온도 끝에 "
            "가까우면 겹침이 사라집니다)."
        )
    ratio = float(np.median(relax_e[inside] / relaxation_at(series, relax_t[inside], a_t)))
    gap = abs(ratio - 1.0)
    where = (
        f"겹친 시간대 {relax_t[inside].min():.3g}~{relax_t[inside].max():.3g} s"
        f"(응력완화 점 {overlap}개)"
    )
    if gap > OVERLAP_BLOCK:
        raise GroupError(
            f"{where}에서 응력완화가 DMA 의 {ratio:.3g}배입니다(차 {gap:.0%}, 막는 선 "
            f"{OVERLAP_BLOCK:.0%}) — 시편 · 로트 · 온도 기록 · 유지 변형률(선형 구간)이 "
            "같은지 보세요. 같은 것을 잰 두 곡선이 아니면 잇지 않습니다."
        )
    if gap > OVERLAP_WARN:
        warnings.append(
            f"{where}에서 응력완화가 DMA 의 {ratio:.3g}배입니다(차 {gap:.0%}) — 잇기는 "
            "했지만 시편 · 로트 · 온도 기록 · 유지 변형률이 같은지 확인하세요."
        )
    _linear_range(relaxation, warnings)

    # ── 한 벌로 맞춘다 ─────────────────────────────────────────────────
    join_hi = max(dma_hi / 10.0, min(dma_hi, dma_lo * 10.0))
    decades = max(math.log10(join_hi / dma_lo), 0.5)
    count = max(5, round(decades * DMA_POINTS_PER_DECADE) + 1)
    dma_t = np.geomspace(dma_lo, join_hi, count)
    dma_e = relaxation_at(series, dma_t, a_t)
    time = np.concatenate([dma_t, relax_t])
    modulus = np.concatenate([dma_e, relax_e])
    # 두 쪽의 무게를 점 수와 무관하게 같게 — 응력완화 점이 수천이면 DMA 쪽이 묻힌다.
    share = [np.full(len(dma_t), 1.0 / len(dma_t)), np.full(len(relax_t), 1.0 / len(relax_t))]
    weight = np.sqrt(np.concatenate(share))
    grid = _taus(float(time.min()), float(time.max()))
    basis = np.column_stack([np.ones_like(time), *(np.exp(-time / tau) for tau in grid)])
    design = basis / modulus[:, np.newaxis] * weight[:, np.newaxis]
    solution, _ = nnls(design, weight)
    model = (basis @ solution) / modulus
    rmse = float(np.sqrt(np.mean((model - 1.0) ** 2)))
    rmse_dma = float(np.sqrt(np.mean((model[: len(dma_t)] - 1.0) ** 2)))
    rmse_relax = float(np.sqrt(np.mean((model[len(dma_t) :] - 1.0) ** 2)))
    terms = [
        (float(tau), float(e)) for tau, e in zip(grid, solution[1:], strict=True) if e > 0
    ]
    if not terms:
        raise GroupError(
            "이은 곡선에 완화가 보이지 않습니다 — 응력이 시간에 따라 줄지 않습니다."
        )
    equilibrium = float(solution[0])
    instantaneous = equilibrium + sum(e for _, e in terms)
    earliest = float(time.min())
    at_earliest = equilibrium + sum(e * math.exp(-earliest / tau) for tau, e in terms)
    # 응력완화만으로 맞췄다면의 순간 탄성률 — 잇는 것이 얼마나 바꿨는지 보인다.
    alone, alone_terms, _ = prony_time.fit(relax_t, relax_e)
    alone_instantaneous = alone + sum(e for _, e in alone_terms)

    warnings.insert(
        0,
        f"짧은 시간(t < {join_hi:.3g} s)은 DMA 마스터커브({curve.label}, 기준 "
        f"{_celsius(reference_k)} → {_celsius(target_k)} 로 옮김, log a_T = {log_a:.3g})"
        "에서, "
        f"긴 시간은 응력완화(시험 {len(relaxation)}건)에서 왔습니다. "
        f"겹친 구간 비 {ratio:.3g}.",
    )
    if alone_instantaneous > 0:
        warnings.append(
            f"응력완화만으로 맞췄다면 순간 탄성률은 {alone_instantaneous / 1e9:.4g} GPa — "
            f"이어서 {instantaneous / 1e9:.4g} GPa 입니다."
        )
    values = {
        "equilibrium_pa": equilibrium,
        "instantaneous_pa": instantaneous,
        "normalized_rmse": rmse,
        "normalized_rmse_dma": rmse_dma,
        "normalized_rmse_relaxation": rmse_relax,
        "term_count": float(len(terms)),
        "point_count": float(len(time)),
        "time_min": earliest,
        "time_max": float(time.max()),
        "instantaneous_ratio": (
            instantaneous / at_earliest if at_earliest > 0 else float("inf")
        ),
        "reference_temperature_k": target_k,
        "overlap_ratio": ratio,
        "overlap_points": float(overlap),
        "dma_join_time_s": join_hi,
        "dma_log10_shift": log_a,
        "dma_reference_temperature_k": reference_k,
        "relaxation_only_instantaneous_pa": alone_instantaneous,
    }
    # 전단에서 옮겼으면 쓴 ν 를 값으로, 그 출처(옵션 · 재료)를 상세로 남긴다.
    if measured["shear"]:
        values["dma_poisson_ratio"] = float(measured["poisson_ratio"])
    return GroupOutcome(
        values=values,
        detail={
            "terms": [{"relaxation_time_s": tau, "modulus_pa": e} for tau, e in terms],
            "short_time_source": curve.label,
            "long_time_sources": [one.label for one in relaxation],
            "dma_modulus_basis": measured["label"],
            **(
                {"dma_poisson_source": measured["poisson_source"]} if measured["shear"] else {}
            ),
        },
        warnings=warnings,
        used=[curve.label, *(one.label for one in relaxation)],
    )


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """이은 결과 → 점탄성 블록 + 탄성계수(순간 탄성률). 응력완화 카드와 같은 모양에 이음 근거
    (DMA 로 메운 시간 끝 · 겹친 구간 비 · 잰 탄성률, 전단이면 쓴 ν)를 더한다."""
    blocks = prony_time.card_blocks(values, detail, warnings)
    extra = ("dma_join_time_s", "overlap_ratio", "dma_poisson_ratio")
    shown = blocks["viscoelastic"]["values"]
    shown.update(
        {key: float(values[key]) for key in extra if isinstance(values.get(key), int | float)}
    )
    # **무엇을 잰 것인가** — 판 1 은 E′ 만 받았으므로 상세가 없으면 E′ 다.
    dma_basis = str(detail.get("dma_modulus_basis") or "E′ (인장 · 굽힘 DMA)")
    shown["modulus_basis"] = f"{dma_basis} · 긴 시간은 응력완화 E(t)"
    return blocks
