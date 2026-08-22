"""시편 단면적 — **모양마다 식이 다르다.**

처리 파이프라인은 하중을 단면적으로 나눠 응력을 만든다. 그런데 그 단면적을 어떻게
내는지가 시편 모양마다 다르다.

    평판   폭 곱하기 두께
    환봉   π (직경/2)²
    관     π/4 (외경 제곱 빼기 내경 제곱)

**틀리면 응력이 자릿수째로 어긋나는데 숫자는 그럴듯해 보인다.** 12.5 mm 환봉을
평판 식으로 계산하면 단면적이 없어서 실패하거나, 폭 자리에 직경을 넣었다면 두께를
곱해 엉뚱한 값이 나온다.

## 왜 여기 있는가

식은 계산이다. 어느 식을 쓸지는 **규격이 정한다**(`ASTM E8 R1` 은 환봉이다) —
정의는 데이터, 계산은 플러그인(D7). 규격이 이름을 고르고 이 표가 식을 갖는다.

## 왜 시편 분류가 아닌가

분류(인장·DMA)에 두면 "인장 평판" 과 "인장 환봉" 처럼 분류를 모양별로 쪼개야
한다. 규격은 어차피 자기 치수 칸을 갖고 있고(`ASTM E8 R1` 에는 직경이 있다),
식이 요구하는 칸이 거기 있는지 서버가 검사할 수 있다.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass


class SpecimenError(Exception):
    """단면적을 낼 수 없다. 메시지는 **사용자가 읽는다.**"""


@dataclass(frozen=True)
class CrossSection:
    """단면적 내는 법 하나."""

    key: str
    label: str
    #: 이 식이 요구하는 치수 칸. 규격에 이 칸들이 있어야 고를 수 있다.
    needs: tuple[str, ...]
    fn: Callable[[Mapping[str, float]], float]
    help: str | None = None


def _rectangle(values: Mapping[str, float]) -> float:
    return float(values["width"]) * float(values["thickness"])


def _circle(values: Mapping[str, float]) -> float:
    return math.pi * (float(values["diameter"]) / 2.0) ** 2


def _tube(values: Mapping[str, float]) -> float:
    outer = float(values["outer_diameter"])
    inner = float(values["inner_diameter"])
    if inner >= outer:
        raise SpecimenError(f"내경({inner} m)이 외경({outer} m)보다 작아야 합니다.")
    return math.pi / 4.0 * (outer**2 - inner**2)


def _manual(values: Mapping[str, float]) -> float:
    return float(values["area"])


#: 고를 수 있는 식. **키는 계약이다** — 규격에 저장된다.
CROSS_SECTIONS: dict[str, CrossSection] = {
    item.key: item
    for item in (
        CrossSection(
            key="rectangle",
            label="평판 (폭 곱하기 두께)",
            needs=("width", "thickness"),
            fn=_rectangle,
            help="판재에서 자른 시편. Zwick 이 주는 a0·b0 가 이것입니다.",
        ),
        CrossSection(
            key="circle",
            label="환봉 (직경)",
            needs=("diameter",),
            fn=_circle,
            help="봉재를 깎은 시편. 폭·두께가 아니라 직경 하나입니다.",
        ),
        CrossSection(
            key="tube",
            label="관 (외경 · 내경)",
            needs=("outer_diameter", "inner_diameter"),
            fn=_tube,
        ),
        CrossSection(
            key="manual",
            label="직접 적음",
            needs=("area",),
            fn=_manual,
            help="식으로 안 되는 모양. 단면적을 사람이 재서 적습니다.",
        ),
    )
}


def area(key: str, values: Mapping[str, float]) -> float:
    """단면적(m²). 값이 모자라면 **무엇이 없는지 말하고 실패한다.**

    0 이나 어림값으로 채우지 않는다 — 단면적이 틀리면 응력이 자릿수째로 어긋나고
    그 숫자는 그럴듯해 보인다.
    """
    shape = CROSS_SECTIONS.get(key)
    if shape is None:
        raise SpecimenError(f"모르는 단면 모양입니다: {key!r}")
    missing = [name for name in shape.needs if not values.get(name)]
    if missing:
        raise SpecimenError(
            f"'{shape.label}' 로 단면적을 내려면 {', '.join(missing)} 이(가) 필요합니다."
        )
    value = shape.fn(values)
    if not math.isfinite(value) or value <= 0:
        raise SpecimenError(f"단면적이 0 보다 커야 합니다: {value}")
    return value
