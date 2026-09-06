"""속도별 곡선 묶기 — **인장 시험 여럿을 변형률 속도로 묶어 속도 의존 소성을 낸다.**

## 왜 묶음인가

시험 조건에 속도(`speed_plastic`)는 적혔는데 아무 계산도 그것을 안 썼다. 통계
묶음은 재료·시험 종류·방향으로만 가르므로 속도가 다른 시편이 **한 평균에 섞였고**,
그 평균은 어느 속도의 물성도 아니었다. 속도별로 갈라 곡선을 내는 것은 시험 하나
안에서 끝나지 않고(처리도 아니고) 값을 평균 내는 것도 아니다(통계도 아니다) —
곡선 n벌 → 곡선 몇 벌 + 계수 한 벌, 묶음이다(ADR 0020).

## 무엇을 내나

1. **속도 묶음(bin)** — 가까운 속도끼리 한 묶음. 장비가 같은 속도를 정확히 재현하지
   못하므로 `bin_ratio` 안이면 같은 속도로 본다.
2. **묶음별 평균 곡선** — 진소성변형률·진응력. 격자가 달라도 **공통 구간에 보간해**
   평균한다. 통계 커널은 보간을 거부하지만(`matcore.statistics`), 여기서는 그것이
   목적이다 — 다만 그 사실을 경고로 남긴다.
3. **속도 민감도** — 기준 속도(가장 느린 묶음) 대비 응력비를 몇 개 변형률에서 읽고,
   원하면 Cowper-Symonds 또는 Johnson-Cook 식으로 맞춘다.

## 무엇을 안 하나

**온도는 안 가른다.** 속도와 온도를 함께 가르면 한 재료에 시편이 수십 개 있어야
한다. 온도가 섞여 있으면 경고만 한다 — 조용히 평균에 넣지 않는다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member
from matcore.processing.tensile import PLASTIC_STRAIN, TRUE_STRESS
from matcore.registry import ParamSpec, Produced, register

#: 구성원이 드는 값. 단위는 1/s.
RATE = "strain_rate"
#: 있으면 경고에 쓴다(K). 없어도 된다.
TEMPERATURE = "temperature"

MODELS = ("none", "cowper_symonds", "johnson_cook")
DEFAULT_LEVELS = "0.002, 0.02, 0.05, 0.1"
#: 묶음별 평균 곡선의 점 수.
GRID_POINTS = 200
#: 곡선 하나가 이보다 짧으면 보간할 수 없다.
MIN_CURVE_POINTS = 3


@register(
    id="tensile.rate_family",
    kind="grouping",
    label="속도별 소성 곡선",
    applies_to=("tensile",),
    # **키만으로 거르면 부서가 만든 인장 종류에서 이 방법이 사라진다.** 변위·하중을
    # 재는 시험이면 진응력을 낼 수 있고, 그러면 속도로 가를 수 있다.
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="bin_ratio",
            label="같은 속도로 볼 폭",
            type="float",
            default=0.3,
            help=(
                "속도가 이 비율 안에서 다르면 같은 속도로 묶음. 0.3 이면 0.001 과 "
                "0.0013 은 한 묶음, 0.001 과 0.01 은 다른 묶음. 장비가 같은 속도를 "
                "정확히 재현하지 못하므로 0 이면 시편마다 따로 섬."
            ),
        ),
        ParamSpec(
            name="levels",
            label="응력비를 읽을 변형률",
            type="str",
            default=DEFAULT_LEVELS,
            dimension="strain",
            help=(
                "이 진소성변형률들에서 기준 속도 대비 응력비를 읽음. 쉼표로 구분. "
                "어느 묶음의 곡선이 거기까지 못 가면 그 점은 제외되고 경고 기록."
            ),
        ),
        ParamSpec(
            name="model",
            label="속도 민감도 식",
            type="choice",
            choices=MODELS,
            default="none",
            choice_labels={
                "none": "식 없이 표만",
                "cowper_symonds": "Cowper-Symonds",
                "johnson_cook": "Johnson-Cook (C 만)",
            },
            choice_help={
                "none": "속도별 표만 산출. 솔버가 표를 그대로 받으면 충분.",
                "cowper_symonds": (
                    "σ/σ₀ = 1 + (ε̇/D)^(1/p). 속도 묶음 셋 이상(기준 빼고 둘 이상)일 때 "
                    "D·p 결정. **σ₀ 는 가장 느린 시험 속도의 응력**이지 준정적 값이 "
                    "아님 — 기준 속도가 빠를수록 D·p 가 문헌값과 벌어짐."
                ),
                "johnson_cook": (
                    "σ/σ₀ = 1 + C·ln(ε̇/ε̇₀). 기준 속도 ε̇₀ 는 가장 느린 묶음. 묶음이 "
                    "둘이어도 C 산출 — 다만 점 하나로 맞춘 값."
                ),
            },
            help="속도별 표에 더해 응력비를 식으로 요약할지 여부.",
        ),
    ),
    makes_values=(
        Produced(key="rate_count", label="속도 묶음 수", si_unit="1"),
        Produced(key="reference_rate", label="기준 속도", si_unit="1/s"),
        Produced(key="rate_min", label="가장 느린 속도", si_unit="1/s"),
        Produced(key="rate_max", label="가장 빠른 속도", si_unit="1/s"),
        Produced(key="cs_d", label="Cowper-Symonds D", si_unit="1/s"),
        Produced(key="cs_p", label="Cowper-Symonds p", si_unit="1"),
        Produced(key="jc_c", label="Johnson-Cook C", si_unit="1"),
        Produced(key="model_r_squared", label="식의 R²", si_unit="1"),
    ),
    order=20,
    version="1",
)
def rate_family(
    members: list[Member],
    *,
    bin_ratio: float = 0.3,
    levels: str = DEFAULT_LEVELS,
    model: str = "none",
) -> GroupOutcome:
    """레지스트리가 옵션을 **키워드로** 넘긴다 — 시그니처가 곧 받는 칸이다."""
    bin_ratio = float(bin_ratio or 0.0)
    if bin_ratio < 0:
        raise GroupError(f"같은 속도로 볼 폭은 0 이상이어야 합니다: {bin_ratio}")
    parsed_levels = _levels(str(levels or DEFAULT_LEVELS))
    model = str(model or "none")
    if model not in MODELS:
        raise GroupError(f"모르는 식입니다: {model}. {', '.join(MODELS)} 중 하나입니다.")

    warnings: list[str] = []
    curves = {member.label: _curve_of(member) for member in members}
    rates = {member.label: _rate_of(member) for member in members}
    _warn_temperature(members, warnings)

    bins = _bins(members, rates, bin_ratio)
    averaged = [
        _average(
            [curves[label] for label in labels],
            labels,
            [rates[label] for label in labels],
            warnings,
        )
        for labels in bins
    ]
    reference = averaged[0]
    ratios = [_ratios(reference, one, parsed_levels, warnings) for one in averaged]

    values: dict[str, float] = {
        "rate_count": float(len(bins)),
        "reference_rate": reference.rate,
        "rate_min": averaged[0].rate,
        "rate_max": averaged[-1].rate,
    }
    detail: dict[str, Any] = {
        "model": model,
        "levels": list(parsed_levels),
        "reference_rate": reference.rate,
        "interpolated": True,
        "rates": [
            {
                "rate": one.rate,
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

    if model != "none":
        fitted = _fit(
            model, averaged[1:], [_nanmean(q) for q in ratios[1:]], reference.rate, warnings
        )
        values.update(fitted)
        detail["fit"] = dict(fitted)

    return GroupOutcome(
        values=values,
        columns={PLASTIC_STRAIN: reference.x, TRUE_STRESS: reference.y},
        detail=detail,
        warnings=warnings,
        used=[member.label for member in members],
    )


# ── 구성원 읽기 ─────────────────────────────────────────────────────────────


class _Curve:
    __slots__ = ("x", "y")

    def __init__(self, x: np.ndarray, y: np.ndarray) -> None:
        self.x = x
        self.y = y


class _Averaged:
    __slots__ = ("labels", "rate", "x", "y")

    def __init__(
        self, labels: Sequence[str], rate: float, x: np.ndarray, y: np.ndarray
    ) -> None:
        self.labels = tuple(labels)
        self.rate = rate
        self.x = x
        self.y = y


def _rate_of(member: Member) -> float:
    raw = member.values.get(RATE)
    if raw is None or not math.isfinite(float(raw)) or float(raw) <= 0:
        raise GroupError(
            f"'{member.label}' 의 변형률 속도가 없거나 0 이하입니다. 시험 조건의 "
            f"소성역 속도와 시편의 게이지 길이에서 오는 값입니다 — 둘 중 하나가 비었습니다."
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
    # 같은 x 는 뒤엣것을 버린다 — 탄성 구간을 0 으로 자른 자국이 여럿일 수 있다.
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


def _warn_temperature(members: Sequence[Member], warnings: list[str]) -> None:
    seen = {
        float(member.values[TEMPERATURE])
        for member in members
        if member.values.get(TEMPERATURE) is not None
    }
    if len(seen) > 1:
        lo, hi = min(seen), max(seen)
        warnings.append(
            f"시험 온도가 {lo:.1f}~{hi:.1f} K 로 섞여 있습니다. 이 묶음은 속도로만 "
            f"가르므로 온도 차이는 곡선에 그대로 남습니다."
        )


# ── 묶고 평균하기 ───────────────────────────────────────────────────────────


def _bins(
    members: Sequence[Member], rates: Mapping[str, float], ratio: float
) -> list[list[str]]:
    """가까운 속도끼리. **느린 것부터** 세우고 앞 묶음의 첫 속도를 기준으로 붙인다."""
    ordered = sorted(members, key=lambda one: rates[one.label])
    span = math.log10(1.0 + ratio) if ratio > 0 else 0.0
    bins: list[list[str]] = []
    anchor: float | None = None
    for member in ordered:
        rate = rates[member.label]
        if anchor is not None and math.log10(rate / anchor) <= span + 1e-12:
            bins[-1].append(member.label)
        else:
            bins.append([member.label])
            anchor = rate
    return bins


def _average(
    curves: Sequence[_Curve],
    labels: Sequence[str],
    member_rates: Sequence[float],
    warnings: list[str],
) -> _Averaged:
    """한 속도 묶음의 평균 곡선. 묶음의 속도는 구성원 속도의 **기하평균**이다 —
    0.0009 와 0.0011 을 묶었으면 0.001 이라고 부르는 것이 맞다."""
    rates_note = ""
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
    if len(curves) == 1:
        warnings.append(
            f"'{labels[0]}' 은 그 속도에서 시편 하나뿐입니다 — "
            f"평균이 아니라 그 시편의 곡선입니다."
        )
    else:
        shortest = min(float(one.x[-1]) for one in curves)
        longest = max(float(one.x[-1]) for one in curves)
        if longest > shortest * 1.2:
            rates_note = f" 가장 짧은 곡선({shortest:.4g})까지만 평균했습니다."
        warnings.append(
            f"{' · '.join(labels)} — 시편 {len(curves)}개를 공통 구간 "
            f"{lo:.4g}~{hi:.4g} 에 보간해 평균했습니다.{rates_note}"
        )
    rate = float(math.exp(np.mean(np.log(np.asarray(member_rates, dtype=np.float64)))))
    return _Averaged(labels, rate, grid, mean)


def _ratios(
    reference: _Averaged, one: _Averaged, levels: Sequence[float], warnings: list[str]
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
            f"속도 {one.rate:.3g} 1/s 묶음은 변형률 "
            f"{', '.join(f'{v:.3g}' for v in skipped)} 까지 안 가서 그 점의 응력비를 뺐습니다."
        )
    return found


def _nanmean(values: Sequence[float]) -> float | None:
    kept = [v for v in values if not math.isnan(v)]
    return float(np.mean(kept)) if kept else None


# ── 속도 민감도 식 ──────────────────────────────────────────────────────────


def _fit(
    model: str,
    bins: Sequence[_Averaged],
    ratio_means: Sequence[float | None],
    reference_rate: float,
    warnings: list[str],
) -> dict[str, float]:
    points = [
        (one.rate, float(q)) for one, q in zip(bins, ratio_means, strict=True) if q is not None
    ]
    if not points:
        warnings.append("기준 속도 말고는 묶음이 없어 속도 민감도 식을 맞추지 않았습니다.")
        return {}
    if model == "cowper_symonds":
        return _cowper_symonds(points, warnings)
    return _johnson_cook(points, reference_rate, warnings)


def _cowper_symonds(
    points: Sequence[tuple[float, float]], warnings: list[str]
) -> dict[str, float]:
    """σ/σ₀ = 1 + (ε̇/D)^(1/p). 로그-로그에서 직선이다: ln(q-1) = (1/p)·ln ε̇ - ln D/p."""
    usable = [(r, q) for r, q in points if q > 1.0]
    dropped = len(points) - len(usable)
    if dropped:
        warnings.append(
            f"응력비가 1 이하인 속도 묶음 {dropped}개는 Cowper-Symonds 에 못 넣습니다 — "
            f"속도가 올라도 응력이 안 올랐다는 뜻입니다."
        )
    if len(usable) < 2:
        warnings.append(
            "Cowper-Symonds 는 기준 말고 둘 이상의 속도 묶음이 있어야 D·p 가 정해집니다. "
            "식을 맞추지 않았습니다."
        )
        return {}
    lx = np.log([r for r, _ in usable])
    ly = np.log([q - 1.0 for _, q in usable])
    slope, intercept = np.polyfit(lx, ly, 1)
    if slope <= 0:
        warnings.append(
            "속도가 올라도 응력비가 안 오릅니다. Cowper-Symonds 로 표현할 수 없습니다."
        )
        return {}
    p = 1.0 / float(slope)
    d = math.exp(-float(intercept) * p)
    predicted = [1.0 + (r / d) ** (1.0 / p) for r, _ in usable]
    return {
        "cs_d": d,
        "cs_p": p,
        "model_r_squared": _r_squared([q for _, q in usable], predicted),
    }


def _johnson_cook(
    points: Sequence[tuple[float, float]], reference_rate: float, warnings: list[str]
) -> dict[str, float]:
    """σ/σ₀ = 1 + C·ln(ε̇/ε̇₀). 원점을 지나는 직선이라 점 하나로도 C 가 나온다."""
    xs = np.array([math.log(r / reference_rate) for r, _ in points])
    ys = np.array([q - 1.0 for _, q in points])
    denominator = float(np.dot(xs, xs))
    if denominator <= 0:
        warnings.append("속도 묶음이 기준과 같아 Johnson-Cook C 를 정할 수 없습니다.")
        return {}
    c = float(np.dot(xs, ys) / denominator)
    if len(points) == 1:
        warnings.append(
            "Johnson-Cook C 를 속도 묶음 하나로 맞췄습니다 — 점 하나를 지나는 값입니다."
        )
    predicted = [1.0 + c * x for x in xs]
    return {"jc_c": c, "model_r_squared": _r_squared([q for _, q in points], predicted)}


def _r_squared(observed: Sequence[float], predicted: Sequence[float]) -> float:
    obs = np.asarray(observed, dtype=np.float64)
    pred = np.asarray(predicted, dtype=np.float64)
    ss_res = float(np.sum((obs - pred) ** 2))
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    if ss_tot <= 0:
        return 1.0 if ss_res <= 1e-12 else 0.0
    return 1.0 - ss_res / ss_tot
