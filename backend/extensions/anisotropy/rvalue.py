"""소성 변형비(r값)와 그 세 방향 묶음 — **계산만.** 등록은 `__init__.py`.

## r값이 무엇인가

인장 중에 시편이 폭으로 줄어드는 정도와 두께로 줄어드는 정도의 비다.

    r = ε_w / ε_t          (폭 변형률 / 두께 변형률, 둘 다 진변형률)

두께는 재기 어려워서 **부피가 일정하다**는 가정으로 뺀다(소성역에서 성립):

    ε_l + ε_w + ε_t = 0    →    ε_t = -(ε_l + ε_w)

그래서 폭과 길이만 재면 된다. 한 점에서 나누지 않고 **구간에서 직선을 맞춘다** —
ε_w 를 ε_l 에 대해 회귀해 기울기 m 을 얻고

    r = -m / (1 + m)

한 점에서 나누면 그 점의 잡음이 값이 된다(ISO 10113 의 회귀법과 같은 이유).

## 세 방향

r 은 방향마다 다르다. 압연 방향(MD)을 0°, 45°(DD), 직각(TD)을 90° 로 보고:

    r̄  = (r₀ + 2·r₄₅ + r₉₀) / 4      평균 이방성 — 깊이 드로잉성
    Δr = (r₀ - 2·r₄₅ + r₉₀) / 2      면내 이방성 — 귀(earing) 발생 경향

Hill48 의 계수도 셋에서 나온다(평면 응력, 등방 경화):

    F = r₀ / (r₉₀·(1+r₀))    G = 1 / (1+r₀)    H = r₀ / (1+r₀)
    N = (r₀+r₉₀)·(1+2·r₄₅) / (2·r₉₀·(1+r₀))

**셋이 다 있어야 낸다.** 하나가 없으면 r̄ 도 Hill48 도 못 낸다 — 빠진 방향을
0 으로 두거나 옆 방향으로 대신하면 그 사실이 숫자 안에 숨는다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member

#: 길이 방향 진변형률. 인장 처리(`tensile.true`)가 내는 열 이름 그대로다.
STRAIN = "strain_true"
#: 폭 채널 — 인장 시험 종류가 선언해 둔 이름(`specimen_width`, 단위 m).
#: **폭 변형률이 아니라 폭 그 자체다.** 변형률은 이 확장이 만든다.
WIDTH = "specimen_width"


def width_strain(width: np.ndarray, initial: float | None = None) -> np.ndarray:
    """폭 진변형률 `ln(w/w0)`. `initial` 이 없으면 **곡선의 첫 점**을 초기 폭으로 본다.

    시편 정의의 폭을 주는 편이 낫다 — 첫 점은 예하중이 걸린 뒤일 수 있다.
    """
    first = float(initial if initial else width[0])
    if first <= 0:
        raise GroupError("초기 폭이 0 이하입니다 — 시편 폭을 확인하세요.")
    return np.log(width / first)


#: 회귀에 쓸 최소 점 수. 모자라면 **값을 내지 않는다** — 세 점짜리 기울기는
#: 기울기가 아니라 잡음이다(탄성계수와 같은 문턱).
MIN_POINTS = 5
#: 이 아래면 그 구간이 직선이 아니다. r 은 소성역에서 일정해야 하고, 아니라면
#: 구간을 잘못 잡았거나 시편이 넥킹에 들어간 것이다.
MIN_R_SQUARED = 0.95

#: 기본 구간. 균일 연신 안쪽의 소성역이다 — 앞은 탄성·항복이 섞이고 뒤는 넥킹이다.
DEFAULT_START = 0.08
DEFAULT_END = 0.15

#: 시편 방향 → 압연 방향에서 잰 각도.
ANGLE_OF: dict[str, int] = {"MD": 0, "DD": 45, "TD": 90}


@dataclass(frozen=True)
class Fitted:
    """한 시험의 r값 — **못 냈으면 `value` 가 없고 `why` 가 있다.**"""

    value: float | None
    slope: float
    r_squared: float
    points: int
    start: float
    end: float
    why: str | None = None


def fit(length: np.ndarray, width: np.ndarray, *, start: float, end: float) -> Fitted:
    """구간 [start, end] 의 점들로 ε_w-ε_l 직선을 맞춰 r 을 낸다.

    **못 믿을 값은 안 낸다.** 점이 모자라거나 직선이 아니면 `value` 는 `None` 이고,
    왜 못 냈는지는 `why` 에 있다 — 부르는 쪽이 그것을 사람에게 그대로 옮긴다.
    """
    if length.size != width.size:
        raise GroupError("길이와 폭 변형률의 점 수가 다릅니다.")
    inside = (length >= start) & (length <= end)
    x = length[inside]
    y = width[inside]
    if x.size < MIN_POINTS:
        return Fitted(
            None,
            0.0,
            0.0,
            int(x.size),
            start,
            end,
            f"{start:.3g}~{end:.3g} 구간에 점이 {x.size}개뿐입니다"
            f"({MIN_POINTS}개 이상이어야 합니다).",
        )
    slope, intercept = (float(one) for one in np.polyfit(x, y, 1))
    predicted = slope * x + intercept
    total = float(np.sum((y - np.mean(y)) ** 2))
    residual = float(np.sum((y - predicted) ** 2))
    r_squared = (
        1.0
        if total == 0 and residual == 0
        else (0.0 if total == 0 else 1.0 - residual / total)
    )
    if r_squared < MIN_R_SQUARED:
        return Fitted(
            None,
            slope,
            r_squared,
            int(x.size),
            start,
            end,
            f"그 구간의 R² 가 {r_squared:.4f} 입니다 — 직선이 아닙니다"
            f"(넥킹에 들어갔거나 구간을 잘못 잡았습니다).",
        )
    if slope >= 0:
        # 인장인데 폭이 안 줄었다 — 채널이 뒤바뀌었거나 부호가 반대다.
        return Fitted(
            None,
            slope,
            r_squared,
            int(x.size),
            start,
            end,
            f"폭 변형률이 늘고 있습니다(기울기 {slope:+.4g}) — 폭 채널의 부호나 "
            f"열 지정을 확인하세요.",
        )
    if math.isclose(slope, -1.0, abs_tol=1e-9):
        return Fitted(
            None, slope, r_squared, int(x.size), start, end, "두께가 안 변합니다(r 이 무한)."
        )
    return Fitted(-slope / (1.0 + slope), slope, r_squared, int(x.size), start, end)


# ── 세 방향 묶음 ──────────────────────────────────────────────────────────────


#: 구성원이 드는 값 이름. 곡선에서 계산됐든 사람이 적었든 **같은 이름**이다 —
#: 어느 쪽인지는 `meta` 가 말한다(아래 `SOURCE_META`).
R_VALUE = "r_value"
#: 구성원의 방향. 수집기가 시편에서 읽어 넣는다.
ORIENTATION_META = "orientation"
#: 그 값이 어디서 왔나 — `measured`(채택된 결과) · `stated`(사람이 표로 적음).
SOURCE_META = "source"


def r_family(members: list[Member], *, hill48: bool = True) -> GroupOutcome:
    """세 방향의 r값을 모아 r̄·Δr(·Hill48)을 낸다.

    **같은 방향에 시편이 여럿이면 평균한다** — 반복 시편의 흩어짐은 통계가 볼 일이고,
    여기서 필요한 것은 방향마다 대표 하나다. 몇 개를 평균했는지는 값으로 남긴다.
    """
    warnings: list[str] = []
    used: list[str] = []
    by_angle: dict[int, list[tuple[str, float, str]]] = {0: [], 45: [], 90: []}

    for member in members:
        orientation = str(member.meta.get(ORIENTATION_META) or "").upper()
        angle = ANGLE_OF.get(orientation)
        value = member.values.get(R_VALUE)
        source = str(member.meta.get(SOURCE_META) or "measured")
        if angle is None:
            warnings.append(
                f"{member.label} 은(는) 방향이 '{orientation or '없음'}' 이라 뺐습니다 — "
                f"r값은 압연 방향 기준(MD·DD·TD)이어야 합니다."
            )
            continue
        if value is None or not math.isfinite(float(value)):
            warnings.append(f"{member.label} 에 r값이 없어 뺐습니다.")
            continue
        by_angle[angle].append((member.label, float(value), source))
        used.append(member.label)

    missing = [angle for angle, rows in by_angle.items() if not rows]
    if missing:
        raise GroupError(
            "r값이 없는 방향이 있습니다: "
            + " · ".join(f"{angle}°" for angle in sorted(missing))
            + ". 세 방향(MD 0° · DD 45° · TD 90°)이 다 있어야 r̄ 와 Δr 을 냅니다 — "
            "빠진 방향을 옆 방향으로 대신하면 그 사실이 숫자 안에 숨습니다."
        )

    means = {
        angle: float(np.mean([one[1] for one in rows])) for angle, rows in by_angle.items()
    }
    r_0, r_45, r_90 = means[0], means[45], means[90]
    stated = [one[0] for rows in by_angle.values() for one in rows if one[2] == "stated"]
    if stated:
        # **섞이면 낮은 쪽을 따른다.** 사람이 적은 값은 우리 곡선으로 되짚을 수 없다.
        warnings.append(
            f"사람이 적어 넣은 r값이 {len(stated)}건 섞였습니다({' · '.join(stated)}) — "
            f"이 묶음의 값은 잰 값이 아니라 **적은 값**으로 셉니다."
        )

    values: dict[str, float] = {
        "r_0": r_0,
        "r_45": r_45,
        "r_90": r_90,
        "r_bar": (r_0 + 2.0 * r_45 + r_90) / 4.0,
        "delta_r": (r_0 - 2.0 * r_45 + r_90) / 2.0,
        "specimen_count": float(len(used)),
        "stated_count": float(len(stated)),
    }

    if hill48:
        if r_90 <= 0 or r_0 <= -1:
            warnings.append(
                f"Hill48 계수를 못 냈습니다 — r₀={r_0:.3g}, r₉₀={r_90:.3g} 로는 식이 성립하지 "
                f"않습니다(둘 다 양수여야 합니다)."
            )
        else:
            values.update(
                {
                    "hill_f": r_0 / (r_90 * (1.0 + r_0)),
                    "hill_g": 1.0 / (1.0 + r_0),
                    "hill_h": r_0 / (1.0 + r_0),
                    "hill_n": (r_0 + r_90) * (1.0 + 2.0 * r_45) / (2.0 * r_90 * (1.0 + r_0)),
                }
            )

    if values["r_bar"] < 1.0:
        warnings.append(
            f"r̄ 가 {values['r_bar']:.3g} 입니다 — 1 보다 작으면 두께가 폭보다 잘 줄어듭니다"
            f"(드로잉에 불리). 강판이면 값이나 폭 채널을 다시 보세요."
        )

    detail: dict[str, Any] = {
        "by_angle": {
            str(angle): {
                "r": means[angle],
                "count": len(rows),
                "members": [one[0] for one in rows],
                "sources": sorted({one[2] for one in rows}),
            }
            for angle, rows in by_angle.items()
        },
        # 카드가 값에 붙일 출처 — 하나라도 사람이 적었으면 그쪽을 따른다.
        "source": "stated" if stated else "measured",
    }
    return GroupOutcome(values=values, detail=detail, warnings=warnings, used=used)


# ── 카드 ──────────────────────────────────────────────────────────────────────

#: 카드 값에 붙는 출처 코드. 등급 판정이 이 낱말을 읽는다(`app/.../card_tiers`):
#: `measured` 는 표본 수로, `manual` 은 4등급으로 매겨진다.
_CARD_SOURCE = {"measured": "measured", "stated": "manual"}


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 결과 → `anisotropy` 블록.

    **값마다 출처를 함께 적는다.** 사람이 적은 r값이 하나라도 섞였으면 이 카드의
    이방성 값은 전부 「적은 값」 이다 — r̄ 는 셋을 다 쓰므로 가장 약한 것을 따른다.
    """
    if "r_bar" not in values:
        raise ValueError("이 묶음에 r̄ 가 없습니다.")
    source = _CARD_SOURCE.get(str(detail.get("source") or "measured"), "manual")
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in ("specimen_count", "stated_count"):
            continue
        out[key] = float(value)
        out[f"{key}_source"] = source
    return {"anisotropy": {"values": out, "notes": list(warnings)}}
