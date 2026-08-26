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

UNITS_TS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "shared" / "units.ts"

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


#: 환산을 손으로 적은 자리를 찾는 지문.
#:
#: **이 부류가 반복됐다.** `formatScalar` 의 머리말이 「같은 코드가 세 번
#: 복제돼 있었다」 고 적어 두고 그것을 모았는데, 그 뒤로도 두 곳이 더 나왔다 —
#: 점탄성 패널(`kelvin - 273.15`·`value / 1e6`)과 시편 편집(`area * 1e6`).
#: 모으는 것만으로는 안 되고, **새로 생기는 것을 막아야** 한다.
#:
#: 왜 위험한가: 표 바깥에 환산이 하나라도 남으면 표를 바꾼 날 그 자리만 옛
#: 값을 낸다. 그리고 그 화면은 오류를 내지 않는다 — 숫자가 그럴듯하게 틀린다.
_HANDMADE = (
    "273.15",  # K ↔ °C
    "/ 1e6",  # Pa → MPa
    "/ 1e9",  # Pa → GPa
    "* 1e6",  # m² → mm²
    "* 1e-12",  # kg/m³ → tonne/mm³
    "* 1e12",
)

SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"


def test_환산을_화면에서_손으로_하지_않는다() -> None:
    """정본은 `shared/units.ts` 하나다(ADR 0004).

    여기 걸렸다면 고칠 방법은 그 파일의 `toDisplay`·`fromDisplay`·`formatScalar`
    를 쓰는 것이다. 표에 없는 환산이 필요하면 **표에 더한다.**
    """
    found: list[str] = []
    for path in SRC.rglob("*.ts*"):
        if path.name.endswith(".test.ts") or path.name.endswith(".test.tsx"):
            continue
        if path.resolve() == UNITS_TS.resolve():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.strip()
            # 주석은 뺀다 — 왜 그렇게 하지 않는지 적어 둔 자리가 있다.
            if code.startswith(("//", "*", "/*")):
                continue
            for mark in _HANDMADE:
                if mark in code:
                    found.append(f"{path.relative_to(SRC)}:{number} — {mark}")
    assert not found, "화면에서 단위를 손으로 환산하고 있습니다:\n" + "\n".join(found)
