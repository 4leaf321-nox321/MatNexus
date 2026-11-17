"""문헌 값이 **범위의 끝**(하한 · 상한)인가 — 조건 글자에 흩어진 표기를 하나로 읽는다.

문헌 카탈로그에는 하한 · 상한을 담는 칸이 없다. 원문이 「400 to 700」 처럼 범위를 적으면
이관이 그것을 **두 줄**로 나누고, 어느 끝인지를 조건 글자에 적었다(2026-11-17 개발 DB 실측,
값 103,968줄):

    bound        1,456줄 — lower 725 · upper 520 · min 50 · max 41 · range_lower 15 · …
    value_type   35줄   — minimum (guaranteed spec floor) · maximum (spec ceiling)
    statistic    약 90줄 — minimum · maximum · minimum of 8 measurements · …

읽는 코드가 없어서, 하한 · 상한 줄만 있는 재료 · 물성 748쌍은 **대표값이 곧 하한이나
상한**이었다 — 영률 63쌍 · 선팽창계수 214쌍이 그대로 덱에 실렸다. 대표값
순위(`representative`)와 허용치 조회가 이 판정 하나를 쓴다.

**「최솟값」 이 다 하한은 아니다.** `statistic` 의 「minimum of the alpha_i vs T curve」 는
곡선의 극값(물리량)이고, 「3P-Weibull minimum life parameter」 는 분포의 모수다. 그래서
`statistic` 은 **측정값들의 최소 · 최대**라고 읽히는 꼴만 받는다.
"""

from __future__ import annotations

import re
from typing import Any, Literal

Side = Literal["lower", "upper"]

#: 사람이 읽는 이름 — 덱 각주 · 주의 문구가 쓴다.
LABELS: dict[str, str] = {"lower": "하한", "upper": "상한"}

_LOWER = re.compile(r"^\s*(lower|min|minimum|range_lower|lower_limit)\b", re.IGNORECASE)
_UPPER = re.compile(r"^\s*(upper|max|maximum|range_upper|upper_limit)\b", re.IGNORECASE)
#: `value_type` — 보증 하한 · 규격 상한. 「typical」 은 대표값이다.
_GUARANTEED_LOWER = re.compile(r"^\s*(guaranteed\s+)?minimum\b", re.IGNORECASE)
_SPEC_UPPER = re.compile(r"^\s*maximum\b", re.IGNORECASE)
#: `statistic` — **측정값들의** 최소 · 최대만(곡선의 극값 · 분포의 모수는 아니다).
_STAT = re.compile(
    r"^\s*(minimum|maximum)"
    r"(\s+of\s+(the\s+printed\s+pair|\d+\s+(individual\s+)?(measurements|specimens|readings)))?\s*$",
    re.IGNORECASE,
)


def side(conditions: Any) -> Side | None:
    """하한이면 `lower`, 상한이면 `upper`, 범위의 끝이 아니면 None."""
    if not isinstance(conditions, dict):
        return None
    bound = conditions.get("bound")
    if isinstance(bound, str):
        if _LOWER.match(bound):
            return "lower"
        if _UPPER.match(bound):
            return "upper"
    kind = conditions.get("value_type")
    if isinstance(kind, str):
        if _GUARANTEED_LOWER.match(kind):
            return "lower"
        if _SPEC_UPPER.match(kind):
            return "upper"
    statistic = conditions.get("statistic")
    if isinstance(statistic, str):
        found = _STAT.match(statistic)
        if found:
            return "lower" if found.group(1).lower() == "minimum" else "upper"
    return None


def note(conditions: Any) -> str:
    """덱 각주에 붙일 말 — 범위의 끝이 아니면 빈 글자."""
    found = side(conditions)
    if found is None:
        return ""
    return f" — 문헌 범위의 {LABELS[found]}값(범위 가운데 값이 아님)"
