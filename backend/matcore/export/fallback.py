"""덱이 **소성 없이** 나가는가 — BOM 덱의 대체 보고(`fallbacks`)와 거절(`on_missing_yield`).

실측(2026-11-17, HWAX 연결): 재료 id 로 덱을 받으면 서버가 `소성 → 점탄성 → 탄성` 차례로 되는
첫 형식을 골랐고, 소성 표가 없는 재료는 *MAT_ELASTIC 으로 **말없이** 나갔다. 문헌 줄은 「곡선
합성」 을 안 켜면 항복이 있어도 늘 탄성이었다. 받는 쪽은 곡선 재료를 기대했는데 탄성 재료가
들어와 해석이 돌았다 — 덱은 틀려도 오류 없이 돈다.

두 가지를 대체로 본다.

    elastic          구조 형식인데 소성 표가 없다 — 서버가 탄성 형식을 골랐거나, 형식이
                     소성 표를 선택으로 받는데 재료에 없었다. **사람이 탄성 형식을 직접
                     골랐으면 대체가 아니다.**
    yield_from_uts   소성 표는 있는데 항복이 없어 인장강도를 평탄부로 지은 것(`synth`) —
                     소성 개시를 과대평가한다

점탄성 · 초탄성 형식은 다른 거동을 싣는 것이라 대체가 아니다(고무가 초탄성으로 가는 것은
맞는 길이다).
"""

from __future__ import annotations

from typing import Literal

from matcore import synth
from matcore.export import Deck, Renderer

Kind = Literal["elastic", "yield_from_uts"]

#: 소성 표 블록.
PLASTIC_BLOCK = "table"
#: 탄성 블록 — 이것만 반드시 요구하는 형식이 「탄성 형식」 이다.
ELASTIC_BLOCK = "elastic"


def is_plastic(target: Renderer) -> bool:
    """소성 표를 읽는 형식인가(선택이어도)."""
    return any(need.block == PLASTIC_BLOCK for need in target.needs)


def is_elastic_only(target: Renderer) -> bool:
    """반드시 요구하는 것이 탄성 블록 하나뿐인 형식 — *MAT_ELASTIC · *ELASTIC 같은 것.

    열 형식(탄성이 선택)은 구조 형식이 아니라 대체를 말할 자리가 아니다.
    """
    required = {need.block for need in target.needs if not need.optional}
    return required == {ELASTIC_BLOCK} and not is_plastic(target)


def yield_from_uts(deck: Deck) -> bool:
    """항복 없이 인장강도를 평탄부로 지은 소성 표인가 — 덱 머리의 합성 모델 이름으로 안다."""
    return any(synth.YIELD_FROM_UTS_MODEL in line for line in deck.provenance)


def kind(target: Renderer, deck: Deck, *, server_chose: bool) -> Kind | None:
    """이 덱이 이 형식으로 나가면 대체인가 — 아니면 None.

    `server_chose` 는 형식을 **서버가 골랐는가**다. 사람이 탄성 형식을 고른 줄은 대체가 아니다
    — 그 사람이 원한 것이다. 다만 형식이 소성 표를 선택으로 받는데 재료에 없으면, 고른 사람도
    모른 채 탄성만 나간다.
    """
    if is_plastic(target):
        optional_only = all(
            need.optional for need in target.needs if need.block == PLASTIC_BLOCK
        )
        if optional_only and not deck.has(PLASTIC_BLOCK):
            return "elastic"
        if deck.has(PLASTIC_BLOCK) and yield_from_uts(deck):
            return "yield_from_uts"
        return None
    if server_chose and is_elastic_only(target):
        return "elastic"
    return None
