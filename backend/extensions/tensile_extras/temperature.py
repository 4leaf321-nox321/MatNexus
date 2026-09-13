"""온도별 소성 곡선 — 온도 의존 탄소성.

여러 온도에서 찍은 인장 곡선을 **온도 묶음별로 평균**해 온도별 진응력-진소성변형률
표를 만들고, 기준 온도(가장 낮은 묶음) 대비 응력비를 읽어 온도 연화를 요약한다 —
속도 가족(`matcore/groups/rate.py`)과 같은 모양이고, 축이 속도 대신 온도일 뿐이다.

    온도 묶음   가까운 온도끼리(±`bin_kelvin`) 한 묶음 — 장비가 목표 온도를 정확히
                재현하지 못하므로 296.1 과 297.3 은 같은 온도다
    평균 곡선   묶음 안 시편 곡선을 공통 변형률 구간에 보간해 평균
    응력비      `levels` 의 변형률마다 기준 온도 응력 대비 비
    요약 식     ① 연화 기울기 dσ/dT (Pa/K, 첫 변형률에서, 최소제곱)
                ② Johnson-Cook 온도 항 σ/σ₀ = 1 - T*^m, T* = (T-T₀)/(T_melt-T₀)

표가 잰 것이고 식은 요약이다 — 카드는 표를 싣고 식은 값으로 곁들인다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member

PLASTIC_STRAIN = "strain_true_plastic"
TRUE_STRESS = "stress_true"
TEMPERATURE = "temperature"

MODELS = ("none", "johnson_cook")
DEFAULT_LEVELS = "0.002, 0.02, 0.05, 0.1"
GRID_POINTS = 200
MIN_CURVE_POINTS = 3


class _Curve:
    __slots__ = ("x", "y")

    def __init__(self, x: np.ndarray, y: np.ndarray) -> None:
        self.x = x
        self.y = y


class _Bin:
    __slots__ = ("labels", "temperature", "x", "y")

    def __init__(
        self, labels: Sequence[str], temperature: float, x: np.ndarray, y: np.ndarray
    ) -> None:
        self.labels = tuple(labels)
        self.temperature = temperature
        self.x = x
        self.y = y


def temperature_family(
    members: list[Member],
    *,
    bin_kelvin: float = 5.0,
    levels: str = DEFAULT_LEVELS,
    model: str = "none",
    melt_temperature: float = 0.0,
) -> GroupOutcome:
    """레지스트리가 옵션을 **키워드로** 넘긴다 — 시그니처가 곧 받는 칸이다."""
    bin_kelvin = float(bin_kelvin or 0.0)
    if bin_kelvin < 0:
        raise GroupError(f"같은 온도로 볼 폭은 0 이상이어야 합니다: {bin_kelvin}")
    parsed_levels = _levels(str(levels or DEFAULT_LEVELS))
    model = str(model or "none")
    if model not in MODELS:
        raise GroupError(f"모르는 식입니다: {model}. {', '.join(MODELS)} 중 하나입니다.")
    melt = float(melt_temperature or 0.0)

    warnings: list[str] = []
    curves = {member.label: _curve_of(member) for member in members}
    temperatures = {member.label: _temperature_of(member) for member in members}

    bins = _bins(members, temperatures, bin_kelvin)
    averaged = [
        _average(
            [curves[label] for label in labels],
            labels,
            [temperatures[label] for label in labels],
            warnings,
        )
        for labels in bins
    ]
    if len(averaged) < 2:
        raise GroupError(
            "온도 묶음이 하나뿐입니다 — 온도별로 묶을 것이 없습니다. "
            "다른 온도의 시험을 더하거나 「같은 온도로 볼 폭」 을 줄이세요."
        )
    reference = averaged[0]
    ratios = [_ratios(reference, one, parsed_levels, warnings) for one in averaged]

    values: dict[str, float] = {
        "temperature_count": float(len(averaged)),
        "reference_temperature": reference.temperature,
        "temperature_min": averaged[0].temperature,
        "temperature_max": averaged[-1].temperature,
    }
    values.update(_softening_slope(averaged, parsed_levels[0], warnings))

    detail: dict[str, Any] = {
        "model": model,
        "levels": list(parsed_levels),
        "reference_temperature": reference.temperature,
        "interpolated": True,
        "temperatures": [
            {
                "temperature": one.temperature,
                "members": list(one.labels),
                "count": len(one.labels),
                "ratios": [None if math.isnan(q) else q for q in found],
                "ratio_mean": _nanmean(found),
                "curve": {
                    PLASTIC_STRAIN: [float(v) for v in one.x],
                    TRUE_STRESS: [float(v) for v in one.y],
                },
            }
            for one, found in zip(averaged, ratios, strict=True)
        ],
    }

    if model == "johnson_cook":
        fitted = _johnson_cook(
            averaged[1:],
            [_nanmean(q) for q in ratios[1:]],
            reference.temperature,
            melt,
            warnings,
        )
        values.update(fitted)
        detail["fit"] = dict(fitted)
        if fitted:
            detail["melt_temperature"] = melt

    return GroupOutcome(
        values=values,
        columns={PLASTIC_STRAIN: reference.x, TRUE_STRESS: reference.y},
        detail=detail,
        warnings=warnings,
        used=[member.label for member in members],
    )


# ── 구성원 읽기 ─────────────────────────────────────────────────────────────


def _temperature_of(member: Member) -> float:
    raw = member.values.get(TEMPERATURE)
    if raw is None or not math.isfinite(float(raw)) or float(raw) <= 0:
        raise GroupError(
            f"'{member.label}' 에 시험 온도가 없습니다. 시험 조건의 온도(K)로 묶습니다 — "
            f"시험 편집에서 온도를 적으세요."
        )
    return float(raw)


def _curve_of(member: Member) -> _Curve:
    if PLASTIC_STRAIN not in member.columns or TRUE_STRESS not in member.columns:
        raise GroupError(
            f"'{member.label}' 의 채택된 결과에 진소성변형률·진응력이 없습니다. "
            f"「진응력·진소성변형률」 단계를 거친 결과를 채택하세요."
        )
    x = np.asarray(member.columns[PLASTIC_STRAIN], dtype=np.float64)
    y = np.asarray(member.columns[TRUE_STRESS], dtype=np.float64)
    keep = np.isfinite(x) & np.isfinite(y) & (x >= 0.0)
    x, y = x[keep], y[keep]
    order = np.argsort(x, kind="stable")
    x, y = x[order], y[order]
    x, first = np.unique(x, return_index=True)
    y = y[first]
    if len(x) < MIN_CURVE_POINTS:
        raise GroupError(f"'{member.label}' 의 소성 곡선이 너무 짧습니다({len(x)}점).")
    return _Curve(x, y)


def _levels(raw: str) -> tuple[float, ...]:
    found: list[float] = []
    for token in raw.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError as exc:
            raise GroupError(
                f"응력비를 읽을 변형률을 숫자로 못 읽었습니다: '{token}'"
            ) from exc
        if value < 0:
            raise GroupError(f"응력비를 읽을 변형률은 0 이상이어야 합니다: {value}")
        found.append(value)
    if not found:
        raise GroupError("응력비를 읽을 변형률이 하나도 없습니다.")
    return tuple(sorted(set(found)))


# ── 묶고 평균하기 ───────────────────────────────────────────────────────────


def _bins(
    members: Sequence[Member], temperatures: Mapping[str, float], width: float
) -> list[list[str]]:
    """가까운 온도끼리. **낮은 온도부터** 세우고 앞 묶음의 첫 온도를 기준으로 붙인다."""
    ordered = sorted(members, key=lambda one: temperatures[one.label])
    bins: list[list[str]] = []
    anchor: float | None = None
    for member in ordered:
        t = temperatures[member.label]
        if anchor is not None and t - anchor <= width + 1e-9:
            bins[-1].append(member.label)
        else:
            bins.append([member.label])
            anchor = t
    return bins


def _average(
    curves: Sequence[_Curve],
    labels: Sequence[str],
    member_temperatures: Sequence[float],
    warnings: list[str],
) -> _Bin:
    """한 온도 묶음의 평균 곡선. 묶음의 온도는 구성원 온도의 **산술평균**이다."""
    lo = max(float(one.x[0]) for one in curves)
    hi = min(float(one.x[-1]) for one in curves)
    if hi <= lo:
        raise GroupError(
            f"{' · '.join(labels)} 의 소성 곡선에 겹치는 변형률 구간이 없습니다. "
            f"한 시편이 거의 소성 없이 끊긴 것입니다."
        )
    grid = np.linspace(lo, hi, GRID_POINTS)
    stacked = np.vstack([np.interp(grid, one.x, one.y) for one in curves])
    mean = stacked.mean(axis=0)
    temperature = float(np.mean(np.asarray(member_temperatures, dtype=np.float64)))
    if len(curves) == 1:
        warnings.append(
            f"'{labels[0]}' 은 {temperature:.1f} K 에서 시편 하나뿐입니다 — "
            f"평균이 아니라 그 시편의 곡선입니다."
        )
    else:
        warnings.append(
            f"{' · '.join(labels)} — {temperature:.1f} K 시편 {len(curves)}개를 공통 구간 "
            f"{lo:.4g}~{hi:.4g} 에 보간해 평균했습니다."
        )
    return _Bin(labels, temperature, grid, mean)


def _ratios(
    reference: _Bin, one: _Bin, levels: Sequence[float], warnings: list[str]
) -> list[float]:
    found: list[float] = []
    skipped: list[float] = []
    for level in levels:
        inside_ref = reference.x[0] <= level <= reference.x[-1]
        inside_one = one.x[0] <= level <= one.x[-1]
        if not (inside_ref and inside_one):
            found.append(math.nan)
            skipped.append(level)
            continue
        base = float(np.interp(level, reference.x, reference.y))
        here = float(np.interp(level, one.x, one.y))
        found.append(here / base if base > 0 else math.nan)
    if skipped and one is not reference:
        warnings.append(
            f"{one.temperature:.1f} K 묶음은 변형률 "
            f"{', '.join(f'{v:.3g}' for v in skipped)} 까지 안 가서 그 점의 응력비를 뺐습니다."
        )
    return found


def _nanmean(values: Sequence[float]) -> float | None:
    kept = [v for v in values if not math.isnan(v)]
    return float(np.mean(kept)) if kept else None


# ── 요약 식 ─────────────────────────────────────────────────────────────────


def _softening_slope(
    bins: Sequence[_Bin], level: float, warnings: list[str]
) -> dict[str, float]:
    """첫 변형률에서 읽은 응력의 온도 기울기 dσ/dT (최소제곱). 음수면 연화."""
    points = [
        (one.temperature, float(np.interp(level, one.x, one.y)))
        for one in bins
        if one.x[0] <= level <= one.x[-1]
    ]
    if len(points) < 2:
        warnings.append(
            f"변형률 {level:.4g} 에서 응력을 읽을 수 있는 온도가 둘 미만이라 "
            f"연화 기울기를 내지 않았습니다."
        )
        return {}
    ts = np.asarray([t for t, _ in points])
    ss = np.asarray([s for _, s in points])
    slope, intercept = np.polyfit(ts, ss, 1)
    predicted = slope * ts + intercept
    return {
        "softening_slope": float(slope),
        "softening_r_squared": _r_squared(list(ss), list(predicted)),
    }


def _johnson_cook(
    bins: Sequence[_Bin],
    ratio_means: Sequence[float | None],
    reference_temperature: float,
    melt: float,
    warnings: list[str],
) -> dict[str, float]:
    """σ/σ₀ = 1 - T*^m, T* = (T-T₀)/(T_melt-T₀). 로그에서 직선이다: ln(1-q) = m·ln T*."""
    if melt <= reference_temperature:
        warnings.append(
            f"Johnson-Cook 온도 항에는 녹는점(K)이 기준 온도 {reference_temperature:.1f} K "
            f"보다 커야 합니다 — 식을 맞추지 않았습니다."
        )
        return {}
    points = [
        (one.temperature, float(q))
        for one, q in zip(bins, ratio_means, strict=True)
        if q is not None
    ]
    if not points:
        warnings.append("기준 온도 말고는 묶음이 없어 온도 항을 맞추지 않았습니다.")
        return {}
    usable = [
        ((t - reference_temperature) / (melt - reference_temperature), q)
        for t, q in points
        if 0.0 < q < 1.0 and t > reference_temperature
    ]
    dropped = len(points) - len(usable)
    if dropped:
        warnings.append(
            f"응력비가 1 이상인 온도 묶음 {dropped}개는 Johnson-Cook 에 못 넣습니다 — "
            f"온도가 올라도 응력이 안 내렸다는 뜻입니다."
        )
    if not usable:
        warnings.append(
            "온도가 올라도 응력이 안 내립니다. Johnson-Cook 온도 항으로 표현할 수 없습니다."
        )
        return {}
    xs = np.log([t_star for t_star, _ in usable])
    ys = np.log([1.0 - q for _, q in usable])
    denominator = float(np.dot(xs, xs))
    if denominator <= 0:
        return {}
    m = float(np.dot(xs, ys) / denominator)
    if len(usable) == 1:
        warnings.append(
            "Johnson-Cook m 을 온도 묶음 하나로 맞췄습니다 — 점 하나를 지나는 값입니다."
        )
    predicted = [1.0 - t_star**m for t_star, _ in usable]
    return {"jc_m": m, "model_r_squared": _r_squared([q for _, q in usable], predicted)}


def _r_squared(observed: Sequence[float], predicted: Sequence[float]) -> float:
    obs = np.asarray(observed, dtype=np.float64)
    pred = np.asarray(predicted, dtype=np.float64)
    ss_res = float(np.sum((obs - pred) ** 2))
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    if ss_tot <= 0:
        return 1.0 if ss_res <= 1e-12 else 0.0
    return 1.0 - ss_res / ss_tot


# ── 카드 ────────────────────────────────────────────────────────────────────


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 결과 → 카드 블록. **중심 코드가 부른다**(`/fitting/cards/from-group`).

    `table` 에는 기준 온도의 곡선을, `temperature_table` 에는 온도 전부를 싣는다 —
    온도를 안 받는 솔버는 앞엣것만, 받는 솔버(Abaqus *PLASTIC 온도 열)는 뒤엣것을
    쓴다. 속도 카드와 같은 판단이다.
    """
    bins = list(detail.get("temperatures") or [])
    if not bins:
        raise ValueError("이 묶음에 온도별 곡선이 없습니다.")

    def rows_of(one: Mapping[str, Any]) -> list[dict[str, float]]:
        curve = one.get("curve") or {}
        xs = curve.get(PLASTIC_STRAIN) or []
        ys = curve.get(TRUE_STRESS) or []
        return [
            {
                "temperature": float(one["temperature"]),
                "plastic_strain": float(x),
                "true_stress": float(y),
            }
            for x, y in zip(xs, ys, strict=True)
        ]

    reference_rows = rows_of(bins[0])
    all_rows = [entry for one in bins for entry in rows_of(one)]
    fit = dict(detail.get("fit") or {})
    return {
        "table": {
            "values": {
                "source": "temperature_family",
                "measured_max": max(
                    (r["plastic_strain"] for r in reference_rows), default=0.0
                ),
            },
            "rows": [
                {"plastic_strain": r["plastic_strain"], "true_stress": r["true_stress"]}
                for r in reference_rows
            ],
        },
        "temperature_table": {
            "values": {
                "source": "temperature_family",
                "temperature_count": len(bins),
                "reference_temperature": float(detail.get("reference_temperature") or 0.0),
                "model": str(detail.get("model") or "none"),
                **(
                    {"melt_temperature": float(detail["melt_temperature"])}
                    if detail.get("melt_temperature")
                    else {}
                ),
                **{key: float(value) for key, value in fit.items()},
            },
            "rows": all_rows,
            "notes": list(warnings),
        },
    }
