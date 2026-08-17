"""프론트의 저장 단위 표가 서버와 어긋나면 실패한다.

프론트는 차원을 고르면 저장 단위를 자동으로 넣는다(`SI_BY_DIMENSION`). 그 표가
서버의 `matcore.units.SI_UNITS` 와 어긋나면 두 가지가 난다.

  - 서버에 있는 차원이 프론트에 없으면 **화면에서 그 채널을 만들 수 없다.**
    실제로 겪었다 — `angular_frequency` 가 빠져 있어서 DMA 종류를 화면에서
    만들 수 없었다. 오류가 아니라 '목록에 없음' 이라 원인을 찾기 어렵다.
  - 단위가 다르면 정의 저장이 422 로 거절된다. 이쪽은 시끄러워서 낫지만,
    사람이 화면에서 막히는 것은 마찬가지다.

프론트 타입은 OpenAPI 에서 생성하지만 이 표는 **값**이라 생성 대상이 아니다.
그래서 검사로 묶는다(개발계획 §8.1 과 같은 취지).
"""

from __future__ import annotations

import re
from pathlib import Path

from matcore import units

UNITS_TS = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "shared" / "units.ts"
)

_BLOCK = re.compile(
    r"export const SI_BY_DIMENSION: Record<string, string> = \{(.*?)\}", re.DOTALL
)
_ENTRY = re.compile(r"^\s*([A-Za-z_]+):\s*'([^']*)'", re.MULTILINE)


def _frontend_table() -> dict[str, str]:
    text = UNITS_TS.read_text(encoding="utf-8")
    block = _BLOCK.search(text)
    assert block, f"{UNITS_TS.name} 에서 SI_BY_DIMENSION 을 찾지 못했습니다."
    return dict(_ENTRY.findall(block.group(1)))


def test_저장_단위_표가_서버와_같다() -> None:
    frontend = _frontend_table()

    missing = sorted(set(units.SI_UNITS) - set(frontend))
    assert not missing, (
        f"프론트 SI_BY_DIMENSION 에 없는 차원: {missing}. "
        f"화면에서 그 차원의 채널을 만들 수 없습니다 — {UNITS_TS.name} 에 더하세요."
    )

    extra = sorted(set(frontend) - set(units.SI_UNITS))
    assert not extra, f"서버에 없는 차원이 프론트에 있습니다: {extra}. 정의 저장이 거절됩니다."

    different = sorted(
        dimension
        for dimension, symbol in units.SI_UNITS.items()
        if frontend[dimension] != symbol
    )
    assert not different, (
        f"저장 단위가 서버와 다릅니다: "
        f"{ {d: (frontend[d], units.SI_UNITS[d]) for d in different} }"
    )


def test_고를_수_있는_단위가_모두_서버_표에_있다() -> None:
    """`UNITS_BY_DIMENSION` 은 서버 표를 **좁혀 옮긴 것**이라 부분집합이면 된다.
    다만 서버에 없는 단위를 고르게 두면 저장할 때 거절당한다."""
    text = UNITS_TS.read_text(encoding="utf-8")
    block = re.search(
        r"export const UNITS_BY_DIMENSION: Record<string, string\[\]> = \{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert block, "UNITS_BY_DIMENSION 을 찾지 못했습니다."

    unknown: list[str] = []
    for dimension, listed in re.findall(r"([A-Za-z_]+):\s*\[([^\]]*)\]", block.group(1)):
        for symbol in re.findall(r"'([^']*)'", listed):
            if symbol not in units.UNITS:
                unknown.append(f"{dimension}:{symbol}")
    assert not unknown, f"서버 단위 표에 없는 단위를 고르게 두고 있습니다: {unknown}"
