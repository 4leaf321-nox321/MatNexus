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

## 방향별 항복응력도 함께 걷는다

r 만으로 맞출 수 있는 항복면은 Hill48 까지다. 그 위(Yld2000-2d 등)는 방향별 항복응력
σ₀·σ₄₅·σ₉₀ 를 r 셋과 **함께** 요구하는데, 그 값은 이미 같은 시험 안에 있었다 —
묶음이 안 걷어서 카드 한 장에 같이 앉지 못했을 뿐이다(2026-09-23).

**있으면 싣고 없으면 그만이다.** r 은 셋이 다 있어야 하지만 σ 는 없어도 r̄·Δr 은
나온다 — σ 를 필수로 두면 항복응력을 안 적은 옛 시험이 통째로 안 묶인다.

**응력으로 Hill48 을 다시 맞추지는 않는다.** F·G·H 를 응력에서 얻으려면 이축 항복응력
σ_b 가 있어야 한다(F+G = 1/σ_b²) — 단축 인장 셋만으로는 안 나온다. 여기서는 모아서
적어 둘 뿐이고, 맞추는 것은 σ_b 를 재는 시험이 생긴 뒤다. 함께 내는 σ₄₅/σ₀ · σ₉₀/σ₀
는 솔버들이 이방성 계수로 받는 그 모양이다.
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
#: 방향별 항복응력이 들어올 수 있는 이름. **셋 다 본다.**
#:
#: 곡선을 처리했으면 오프셋 항복이 `proof_stress` 로 나오고, 표로 적었으면 **열 이름이
#: 그대로 키가 된다**(`tests/importing.py` 의 `_slug` — 한글 이름은 한글 그대로다).
#: 그래서 같은 물성이 세 이름으로 들어온다. 하나만 보면 「분명히 적었는데 카드에 없다」
#: 가 되고, 그때 사람은 자기가 적은 열 이름을 의심하지 않는다.
YIELD_KEYS = ("proof_stress", "yield_strength", "항복강도")

#: 구성원의 방향. 수집기가 시편에서 읽어 넣는다.
ORIENTATION_META = "orientation"
#: 그 값이 어디서 왔나 — `measured`(채택된 결과) · `stated`(사람이 표로 적음).
SOURCE_META = "source"
#: 그중 **사람이 적은 값의 이름들.** 한 시험에서 r 은 곡선에서 나오고 항복응력만
#: 적은 것일 수 있다 — 구성원 하나를 통째로 `stated` 로 세면 잰 r 까지 내려간다.
STATED_KEYS_META = "stated_keys"


@dataclass(frozen=True)
class _Row:
    """한 시편에서 꺼낸 것. 방향은 밖(`by_angle`)이 쥔다."""

    label: str
    r: float
    r_stated: bool
    sigma: float | None
    """방향별 항복응력(Pa). 없을 수 있다 — 그래도 r 묶음은 선다."""
    sigma_stated: bool


def _stated(member: Member, key: str) -> bool:
    """이 **값 하나**가 사람이 적은 것인가.

    이름 목록이 있으면 그것을 보고, 없으면(옛 수집기) 구성원 전체의 출처를 본다 —
    r 은 곡선에서 나오고 항복응력만 적은 시험이 실제로 있다.
    """
    names = member.meta.get(STATED_KEYS_META)
    if isinstance(names, list | tuple | set):
        return key in names
    return str(member.meta.get(SOURCE_META) or "measured") == "stated"


def _yield_of(member: Member) -> tuple[float, bool] | None:
    """이 구성원의 항복응력과 그 출처. 없으면 `None` — **막지 않는다.**

    이름이 셋이라 먼저 나오는 것을 쓴다(`YIELD_KEYS`). 0 이하는 값이 아니다 —
    비운 칸이 0 으로 들어온 것이고, 그걸 나누면 비가 무한이 된다.
    """
    for key in YIELD_KEYS:
        value = member.values.get(key)
        if isinstance(value, int | float) and math.isfinite(float(value)) and float(value) > 0:
            return float(value), _stated(member, key)
    return None


def r_family(members: list[Member], *, hill48: bool = True) -> GroupOutcome:
    """세 방향의 r값을 모아 r̄·Δr(·Hill48)을 낸다. **항복응력이 있으면 함께 싣는다.**

    **같은 방향에 시편이 여럿이면 평균한다** — 반복 시편의 흩어짐은 통계가 볼 일이고,
    여기서 필요한 것은 방향마다 대표 하나다. 몇 개를 평균했는지는 값으로 남긴다.
    """
    warnings: list[str] = []
    used: list[str] = []
    by_angle: dict[int, list[_Row]] = {0: [], 45: [], 90: []}

    for member in members:
        orientation = str(member.meta.get(ORIENTATION_META) or "").upper()
        angle = ANGLE_OF.get(orientation)
        value = member.values.get(R_VALUE)
        if angle is None:
            warnings.append(
                f"{member.label} 은(는) 방향이 '{orientation or '없음'}' 이라 뺐습니다 — "
                f"r값은 압연 방향 기준(MD·DD·TD)이어야 합니다."
            )
            continue
        if value is None or not math.isfinite(float(value)):
            warnings.append(f"{member.label} 에 r값이 없어 뺐습니다.")
            continue
        found = _yield_of(member)
        by_angle[angle].append(
            _Row(
                label=member.label,
                r=float(value),
                r_stated=_stated(member, R_VALUE),
                sigma=found[0] if found else None,
                sigma_stated=bool(found and found[1]),
            )
        )
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
        angle: float(np.mean([one.r for one in rows])) for angle, rows in by_angle.items()
    }
    r_0, r_45, r_90 = means[0], means[45], means[90]
    stated = [one.label for rows in by_angle.values() for one in rows if one.r_stated]
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

    sigma_rows = {
        angle: [one for one in rows if one.sigma is not None]
        for angle, rows in by_angle.items()
    }
    sigma_means = {
        angle: float(np.mean([one.sigma for one in rows]))
        for angle, rows in sigma_rows.items()
        if rows
    }
    sigma_stated = [
        one.label for rows in sigma_rows.values() for one in rows if one.sigma_stated
    ]
    if len(sigma_means) == 3:
        s_0, s_45, s_90 = sigma_means[0], sigma_means[45], sigma_means[90]
        values.update(
            {
                "sigma_0": s_0,
                "sigma_45": s_45,
                "sigma_90": s_90,
                # 솔버가 이방성 계수로 받는 모양 — 0° 를 1 로 두고 견준다.
                "sigma_ratio_45": s_45 / s_0,
                "sigma_ratio_90": s_90 / s_0,
            }
        )
        if sigma_stated:
            warnings.append(
                f"사람이 적어 넣은 항복응력이 {len(sigma_stated)}건 섞였습니다"
                f"({' · '.join(sigma_stated)}) — σ 값은 **적은 값**으로 셉니다."
            )
    elif sigma_means:
        # **반쪽으로 내지 않는다.** 두 방향만 있는 σ 로는 항복면을 못 맞추는데,
        # 카드에 두 개가 앉아 있으면 셋인 줄 알고 가져간다.
        empty = " · ".join(f"{angle}°" for angle in sorted(set(by_angle) - set(sigma_means)))
        warnings.append(
            f"항복응력이 {empty} 에 없어 σ 는 안 실었습니다 — 이방성 항복면은 세 방향이 "
            f"다 있어야 맞춥니다. 「표로 시험 입력」 에서 항복강도 열을 함께 적으세요."
        )

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
                "sigma": sigma_means.get(angle),
                "count": len(rows),
                "sigma_count": len(sigma_rows[angle]),
                "members": [one.label for one in rows],
                "sources": sorted({"stated" if one.r_stated else "measured" for one in rows}),
            }
            for angle, rows in by_angle.items()
        },
        # 카드가 값에 붙일 출처 — 하나라도 사람이 적었으면 그쪽을 따른다.
        # **r 과 σ 를 따로 센다.** 한쪽이 적은 값이라고 다른 쪽 등급까지 내리면,
        # 잰 r 로 만든 카드가 항복강도 한 줄 때문에 4등급이 된다.
        "source": "stated" if stated else "measured",
        "sigma_source": "stated" if sigma_stated else "measured",
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
    r 계열 값은 전부 「적은 값」 이다 — r̄ 는 셋을 다 쓰므로 가장 약한 것을 따른다.

    **σ 는 따로 센다.** r 은 곡선에서 나오고 항복응력만 표로 적은 시험이 있는데, 그때
    한쪽 때문에 다른 쪽 등급까지 내리면 잰 값이 적은 값으로 보인다.
    """
    if "r_bar" not in values:
        raise ValueError("이 묶음에 r̄ 가 없습니다.")
    source = _CARD_SOURCE.get(str(detail.get("source") or "measured"), "manual")
    sigma_source = _CARD_SOURCE.get(str(detail.get("sigma_source") or "measured"), "manual")
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in ("specimen_count", "stated_count"):
            continue
        out[key] = float(value)
        out[f"{key}_source"] = sigma_source if key.startswith("sigma") else source
    return {"anisotropy": {"values": out, "notes": list(warnings)}}
