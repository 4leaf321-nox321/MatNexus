"""묶음 Prony — **시편 여럿에서 계수 한 벌.**

시편마다 마스터커브가 하나씩 나온다. 해석에 넣을 계수는 한 벌이어야 하는데,
여럿을 하나로 만드는 방법이 셋이고 **셋 다 쓸 자리가 있다.**

    representative  대표 하나를 고른다        시편이 한둘이거나, 하나가 확실히 좋을 때
    pooled          점을 모아 한 번에 맞춘다  흩어짐까지 계수에 담고 싶을 때
    averaged        시편마다 맞춰 평균 낸다   시편별 값을 따로 보고 싶을 때

## averaged 에는 조건이 있다

**τ 를 못 박아야 한다.** 자유 τ 로 맞추면 시편마다 다른 값으로 수렴하고 항 수도
BIC 가 따로 고른다 — 그러면 `E₁` 끼리 평균 낸다는 말 자체가 성립하지 않는다.
서로 다른 완화시간의 계수를 더하는 것이 되기 때문이다.

그래서 공통 τ 격자를 먼저 정하고(`fixed_taus_s`) 탄성률만 맞춘다. 맞추는 것이
줄어드는 만큼 잔차는 커지고, 대신 **비교할 수 있는 값**이 나온다.

## pooled 는 흩어짐을 계수에 담는다

점을 다 모아 한 번에 맞추므로, 시편 사이의 차이가 잔차로 들어간다. 그 잔차가
크면 **그 재료를 계수 한 벌로 표현하기 어렵다는 뜻**이고, 그건 사람이 알아야
하는 정보다 — 평균은 그것을 지운다.

## 기준 온도가 다르면 안 묶는다

마스터커브는 **기준 온도 하나에서만 유효하다**(카드 블록이 그렇게 적어 뒀다).
20 °C 것과 30 °C 것을 겹치면 물리적으로 뜻이 없는 곡선이 나오는데, 그것도
그럴듯하게 생겼다. 막고, 무엇이 다른지 말한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member
from matcore.prony import PronySeries, PronyTerm, choose_prony, fit_prony
from matcore.registry import ParamSpec, Produced, register

#: 기준 온도가 이보다 더 벌어지면 안 묶는다(K). 0.5 K 는 장비의 표기 반올림
#: 정도이고, 그 이상은 사람이 다른 온도로 만든 것이다.
REFERENCE_TOLERANCE_K = 0.5

METHODS = ("pooled", "averaged", "representative")


def _series_of(member: Member) -> PronySeries | None:
    """이미 맞춰 둔 계수. 없으면 `None`."""
    raw = member.meta.get("prony")
    if not isinstance(raw, PronySeries):
        return None
    return raw


def _curve_of(member: Member) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        frequency = np.asarray(member.columns["frequency_hz"], dtype=float)
        storage = np.asarray(member.columns["storage_pa"], dtype=float)
        loss = np.asarray(member.columns["loss_pa"], dtype=float)
    except KeyError as exc:
        raise GroupError(
            f"{member.label} 에 마스터커브 열이 없습니다({exc}). "
            f"주파수·저장·손실이 있어야 묶을 수 있습니다."
        ) from exc
    if frequency.size == 0:
        raise GroupError(f"{member.label} 의 마스터커브가 비어 있습니다.")
    return frequency, storage, loss


def _same_reference(members: Sequence[Member]) -> tuple[float, list[str]]:
    """기준 온도가 하나인지 본다. `(기준 온도, 경고)`."""
    found = [
        (item.label, float(item.values["reference_temperature_k"]))
        for item in members
        if "reference_temperature_k" in item.values
    ]
    if len(found) != len(members):
        missing = {item.label for item in members} - {label for label, _ in found}
        raise GroupError(
            f"기준 온도를 모르는 것이 있습니다: {', '.join(sorted(missing))}. "
            f"마스터커브를 먼저 만드세요."
        )
    temperatures = [value for _, value in found]
    spread = max(temperatures) - min(temperatures)
    if spread > REFERENCE_TOLERANCE_K:
        said = ", ".join(f"{label} {value:.1f} K" for label, value in found)
        raise GroupError(
            f"기준 온도가 다릅니다({said}). 마스터커브는 기준 온도 하나에서만 "
            f"유효합니다 — 같은 온도로 다시 겹친 뒤에 묶으세요."
        )
    warnings: list[str] = []
    if spread > 0:
        warnings.append(f"기준 온도가 {spread:.2f} K 만큼 다릅니다. 같은 것으로 봅니다.")
    return float(np.mean(temperatures)), warnings


def _tau_grid(members: Sequence[Member], terms: int) -> np.ndarray:
    """공통 τ 격자. **모두가 관측한 구간 안에서만** 잡는다.

    한 시편만 본 주파수까지 τ 를 늘리면, 나머지 시편에게는 데이터가 말해 주지
    않는 값을 맞추라고 하는 셈이 된다.
    """
    lowest = max(1.0 / float(np.max(_curve_of(item)[0]) * 2.0 * np.pi) for item in members)
    highest = min(1.0 / float(np.min(_curve_of(item)[0]) * 2.0 * np.pi) for item in members)
    if not 0 < lowest < highest:
        raise GroupError(
            "겹치는 주파수 구간이 없습니다. 시편들이 서로 다른 범위를 재고 있습니다."
        )
    return np.geomspace(lowest, highest, terms)


def _outcome(
    series: PronySeries,
    *,
    reference_k: float,
    used: list[str],
    method: str,
    warnings: list[str],
) -> GroupOutcome:
    return GroupOutcome(
        values={
            "equilibrium_pa": series.equilibrium_pa,
            "instantaneous_pa": series.equilibrium_pa
            + sum(term.modulus_pa for term in series.terms),
            "reference_temperature_k": reference_k,
            "term_count": float(len(series.terms)),
            "normalized_rmse": series.normalized_rmse,
        },
        detail={
            "method": method,
            "terms": [
                {"modulus_pa": term.modulus_pa, "relaxation_time_s": term.relaxation_time_s}
                for term in series.terms
            ],
        },
        warnings=warnings,
        used=used,
    )


@register(
    id="viscoelastic.prony_group",
    kind="grouping",
    label="묶음 Prony",
    applies_to=("dma_temperature_sweep",),
    params=(
        ParamSpec(
            name="method",
            label="묶는 방법",
            type="choice",
            choices=METHODS,
            default="pooled",
            help=(
                "pooled: 점을 모아 한 번에 맞춘다(흩어짐이 잔차에 남는다) · "
                "averaged: 시편마다 맞춰 평균(τ 를 못 박는다) · "
                "representative: 대표 하나를 고른다"
            ),
        ),
        ParamSpec(
            name="terms",
            label="항 수",
            type="int",
            default=0,
            help="0 이면 BIC 가 고른다. averaged 는 공통 격자가 필요해 0 이면 4 를 쓴다.",
        ),
        ParamSpec(
            name="representative",
            label="대표",
            type="str",
            default="",
            help="representative 일 때 고를 구성원의 이름. 비우면 잔차가 가장 작은 것.",
        ),
    ),
    makes_values=(
        Produced(key="equilibrium_pa", label="평형 탄성률", si_unit="Pa"),
        Produced(key="instantaneous_pa", label="순간 탄성률", si_unit="Pa"),
        Produced(key="reference_temperature_k", label="기준 온도", si_unit="K"),
        Produced(key="term_count", label="항 수", si_unit="1"),
        Produced(key="normalized_rmse", label="정규화 잔차", si_unit="1"),
    ),
    order=10,
)
def prony_group(
    members: list[Member],
    *,
    method: str = "pooled",
    terms: int = 0,
    representative: str = "",
) -> GroupOutcome:
    """시편 여럿의 마스터커브에서 Prony 계수 한 벌."""
    if method not in METHODS:
        raise GroupError(f"모르는 방법입니다: {method}. {', '.join(METHODS)} 중 하나입니다.")
    reference_k, warnings = _same_reference(members)

    if method == "representative":
        return _representative(members, reference_k, warnings, representative)
    if method == "pooled":
        return _pooled(members, reference_k, warnings, terms)
    return _averaged(members, reference_k, warnings, terms)


def _representative(
    members: list[Member], reference_k: float, warnings: list[str], wanted: str
) -> GroupOutcome:
    """대표 하나를 고른다. **고른 이유를 남긴다.**

    이름을 주면 그것을, 안 주면 **잔차가 가장 작은 것**을 고른다. 「아무거나
    첫째」 로 두면 파일 순서가 물성을 정하게 된다.
    """
    fitted = [(item, _series_of(item)) for item in members]
    ready = [(item, series) for item, series in fitted if series is not None]
    if not ready:
        raise GroupError(
            "맞춰 둔 Prony 가 하나도 없습니다. 대표를 고르려면 시편별로 먼저 맞추세요."
        )

    if wanted:
        picked = next((pair for pair in ready if pair[0].label == wanted), None)
        if picked is None:
            raise GroupError(
                f"{wanted} 는 맞춰 둔 Prony 가 없습니다. "
                f"고를 수 있는 것: {', '.join(item.label for item, _ in ready)}"
            )
    else:
        picked = min(ready, key=lambda pair: pair[1].normalized_rmse)
        warnings.append(f"잔차가 가장 작은 {picked[0].label} 을 대표로 골랐습니다.")

    if len(ready) < len(members):
        skipped = {item.label for item in members} - {item.label for item, _ in ready}
        warnings.append(
            f"맞춰 둔 Prony 가 없어 후보에서 빠진 것: {', '.join(sorted(skipped))}"
        )

    return _outcome(
        picked[1],
        reference_k=reference_k,
        used=[picked[0].label],
        method="representative",
        warnings=warnings,
    )


def _pooled(
    members: list[Member], reference_k: float, warnings: list[str], terms: int
) -> GroupOutcome:
    """점을 모아 한 번에 맞춘다.

    **시편 사이의 차이가 잔차로 들어간다.** 그 잔차가 크면 그 재료를 계수 한
    벌로 표현하기 어렵다는 뜻이고, 그건 지워지면 안 되는 정보다.
    """
    frequency: list[np.ndarray] = []
    storage: list[np.ndarray] = []
    loss: list[np.ndarray] = []
    for item in members:
        one, two, three = _curve_of(item)
        frequency.append(one)
        storage.append(two)
        loss.append(three)

    # **주파수 순으로 다시 세운다.** 적합은 증가 순을 요구하고, 이어 붙인 것은
    # 시편 경계에서 되돌아간다.
    order = np.argsort(np.concatenate(frequency))
    pooled_frequency = np.concatenate(frequency)[order]
    pooled_storage = np.concatenate(storage)[order]
    pooled_loss = np.concatenate(loss)[order]

    if terms > 0:
        series = fit_prony(pooled_frequency, pooled_storage, pooled_loss, terms=terms)
    else:
        series, _ = choose_prony(pooled_frequency, pooled_storage, pooled_loss)
    return _outcome(
        series,
        reference_k=reference_k,
        used=[item.label for item in members],
        method="pooled",
        warnings=warnings,
    )


def _averaged(
    members: list[Member], reference_k: float, warnings: list[str], terms: int
) -> GroupOutcome:
    """시편마다 맞춰 계수를 평균 낸다. **τ 를 못 박고서만 뜻이 있다.**"""
    count = terms if terms > 0 else 4
    taus = _tau_grid(members, count)

    fits: list[PronySeries] = []
    used: list[str] = []
    for item in members:
        one, two, three = _curve_of(item)
        try:
            fits.append(
                fit_prony(one, two, three, terms=count, fixed_taus_s=[float(x) for x in taus])
            )
        except Exception as exc:  # 한 시편이 안 맞아도 나머지는 간다
            warnings.append(f"{item.label} 은 못 맞춰 평균에서 뺐습니다: {exc}")
            continue
        used.append(item.label)

    if len(fits) < 2:
        raise GroupError(
            f"평균 낼 수 있는 것이 {len(fits)}개뿐입니다. pooled 로 묶거나 대표를 고르세요."
        )

    equilibrium = float(np.mean([one.equilibrium_pa for one in fits]))
    moduli = np.mean([[term.modulus_pa for term in one.terms] for one in fits], axis=0)
    # **잔차는 평균 내지 않는다.** 시편별 적합의 잔차이지 평균 계수의 잔차가
    # 아니다 — 그 둘을 같은 칸에 담으면 「평균이 잘 맞는다」 로 읽힌다.
    worst = max(one.normalized_rmse for one in fits)
    warnings.append(
        f"시편별 적합의 잔차 중 가장 큰 것은 {worst:.4f} 입니다"
        f"(평균 계수 자체의 잔차가 아닙니다)."
    )

    return _outcome(
        PronySeries(
            equilibrium_pa=equilibrium,
            terms=tuple(
                PronyTerm(float(modulus), float(tau))
                for modulus, tau in zip(moduli, taus, strict=True)
            ),
            normalized_rmse=worst,
            bic=float("nan"),
        ),
        reference_k=reference_k,
        used=used,
        method="averaged",
        warnings=warnings,
    )
