"""받는 쪽 LS-DYNA 덱에서 **재료마다 ro · e · pr** 을 읽는다(`keep_deck_values`).

연결된 플랫폼은 자기 해석 모델의 덱을 이미 갖고 있다. MatNexus 가 같은 MID 의 재료 카드를
새로 내면 그쪽은 재료를 통째로 바꿔 넣고, 그때 모델이 쓰던 밀도 · 탄성계수 · 푸아송비가
MatNexus 의 값으로 **말없이** 바뀌었다(2026-11-17, HWAX 연결). 곡선만 바꾸고 싶은 사람에게는
그 셋이 모델의 것이어야 한다.

## 첫 카드가 `MID RO E PR` 인 키워드만 읽는다

키워드마다 첫 카드의 칸이 다르다 — `*MAT_GENERAL_VISCOELASTIC` 의 셋째 칸은 BULK,
`*MAT_HYPERELASTIC_RUBBER` 의 셋째는 PR 이다. 칸 차례를 짐작해 읽으면 체적탄성률을 탄성계수로
옮긴다. 그래서 차례를 아는 키워드만 받고, 나머지는 「못 읽음」 으로 알린다(값을 지키지 못했다고
말하는 편이 틀린 값보다 낫다).

고정폭(10칸, 키워드 끝 `+` 면 20칸)과 쉼표 구분을 읽는다. `_TITLE` 이면 첫 줄은 이름이다.
숫자가 아닌 칸 (`&ro` 같은 매개변수)은 그 칸만 못 읽은 것으로 둔다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from matcore.export import Deck
from matcore.export.systems import UnitSystem

#: 탄성 블록.
ELASTIC = "elastic"

#: 첫 카드가 `MID RO E PR …` 인 키워드(번호 · 이름 둘 다). `_TITLE` 은 떼고 견준다.
LAYOUT_MID_RO_E_PR: frozenset[str] = frozenset(
    {
        "MAT_001",
        "MAT_ELASTIC",
        "MAT_003",
        "MAT_PLASTIC_KINEMATIC",
        "MAT_018",
        "MAT_POWER_LAW_PLASTICITY",
        "MAT_020",
        "MAT_RIGID",
        "MAT_024",
        "MAT_PIECEWISE_LINEAR_PLASTICITY",
        "MAT_024_LOG_INTERPOLATION",
        "MAT_PIECEWISE_LINEAR_PLASTICITY_LOG_INTERPOLATION",
        "MAT_024_STOCHASTIC",
        "MAT_PIECEWISE_LINEAR_PLASTICITY_STOCHASTIC",
        "MAT_024_MIDFAIL",
        "MAT_PIECEWISE_LINEAR_PLASTICITY_MIDFAIL",
        "MAT_024_2D",
        "MAT_PIECEWISE_LINEAR_PLASTICITY_2D",
        "MAT_098",
        "MAT_SIMPLIFIED_JOHNSON_COOK",
        "MAT_123",
        "MAT_MODIFIED_PIECEWISE_LINEAR_PLASTICITY",
    }
)

#: 지키는 칸 — 덱 칸 이름 → 카드 탄성 블록의 값 이름.
KEPT_FIELDS: tuple[tuple[str, str], ...] = (
    ("ro", "density"),
    ("e", "youngs_modulus"),
    ("pr", "poisson_ratio"),
)


@dataclass(frozen=True)
class BaseMaterial:
    """받은 덱의 재료 카드 하나."""

    mid: int
    keyword: str
    values: dict[str, float] = field(default_factory=dict)
    """읽은 칸(`ro` · `e` · `pr`) — **덱의 단위 그대로**."""
    unread: tuple[str, ...] = ()
    """못 읽은 칸과 그 까닭 — 비었거나 숫자가 아니다."""


@dataclass(frozen=True)
class BaseDeck:
    materials: dict[int, BaseMaterial]
    skipped: tuple[str, ...]
    """재료 카드인데 칸 차례를 몰라 안 읽은 것 — `*MAT_GENERAL_VISCOELASTIC (MID 7)` 처럼."""


_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?$")


def _number(text: str) -> float | None:
    cleaned = text.strip()
    if not _NUMBER.match(cleaned):
        return None
    return float(cleaned.replace("d", "e").replace("D", "e"))


def _fields(line: str, width: int) -> list[str]:
    if "," in line:
        return [part.strip() for part in line.split(",")]
    return [line[i : i + width].strip() for i in range(0, max(len(line), width * 4), width)]


def _data_lines(lines: list[str], start: int) -> list[str]:
    """키워드 다음의 자료 줄 — 주석(`$`)은 건너뛰고 다음 키워드(`*`)에서 멈춘다."""
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("*"):
            break
        if line.startswith("$") or not line.strip():
            continue
        out.append(line.rstrip("\n\r"))
    return out


def read(text: str) -> BaseDeck:
    """덱 글자 → MID 마다 ro · e · pr. 같은 MID 가 두 번이면 뒤엣것(솔버가 그것으로 덮는다)."""
    lines = text.splitlines()
    long_all = any(
        line.upper().startswith("*KEYWORD") and re.search(r"LONG\s*=\s*Y", line, re.IGNORECASE)
        for line in lines[:5]
    )
    materials: dict[int, BaseMaterial] = {}
    skipped: list[str] = []
    for index, line in enumerate(lines):
        if not line.startswith("*MAT"):
            continue
        raw = line[1:].split()[0].upper() if line[1:].split() else ""
        width = 20 if raw.endswith("+") or long_all else 10
        keyword = raw.rstrip("+-")
        titled = keyword.endswith("_TITLE")
        base = keyword.removesuffix("_TITLE")
        data = _data_lines(lines, index + 1)
        if titled:
            data = data[1:]
        if not data:
            continue
        cells = _fields(data[0], width)
        mid_value = _number(cells[0]) if cells else None
        if mid_value is None or mid_value != int(mid_value):
            skipped.append(f"*{keyword} (MID 「{cells[0] if cells else ''}」 — 숫자가 아님)")
            continue
        mid = int(mid_value)
        if base not in LAYOUT_MID_RO_E_PR:
            skipped.append(f"*{keyword} (MID {mid})")
            continue
        values: dict[str, float] = {}
        unread: list[str] = []
        for position, (name, _) in enumerate(KEPT_FIELDS, start=1):
            cell = cells[position] if position < len(cells) else ""
            number = _number(cell) if cell else None
            if number is None:
                unread.append(f"{name}(「{cell}」)" if cell else f"{name}(빈 칸)")
                continue
            values[name] = number
        materials[mid] = BaseMaterial(
            mid=mid, keyword=f"*{keyword}", values=values, unread=tuple(unread)
        )
    return BaseDeck(materials=materials, skipped=tuple(skipped))


#: 덱 칸 → (사람 이름, 탄성 블록 값 이름, SI 단위).
_KEPT_META: dict[str, tuple[str, str, str]] = {
    "ro": ("밀도", "density", "kg/m3"),
    "e": ("탄성계수", "youngs_modulus", "Pa"),
    "pr": ("푸아송비", "poisson_ratio", "1"),
}

#: 덱 머리의 값 출처 줄 — 카드(「탄성계수: 이 시험들에서 잰 값」) · 문헌(「포아송비 = 3.0E-01 —
#: …」). 지킨 값의 출처는 받은 덱이라, 이 줄이 남으면 덱이 거짓 출처를 말한다.
_SOURCE_LINE = re.compile(r"^(탄성계수|영률|푸아송비|포아송비|밀도)\s*[:=]")


@dataclass(frozen=True)
class Kept:
    deck: Deck
    values: dict[str, float]
    """지킨 칸(`ro` · `e` · `pr`) — **받은 덱의 단위 그대로**."""
    notes: tuple[str, ...]


def keep(deck: Deck, base: BaseMaterial, system: UnitSystem) -> Kept:
    """덱의 탄성 블록에 **받은 덱의 ro · e · pr** 을 넣는다. 못 읽은 칸은 MatNexus 값 그대로.

    값은 받은 덱의 단위(= 이 BOM 의 단위계)로 적혀 있어 SI 로 되돌려 넣는다 — 블록은 늘 SI
    다(`Deck`).
    """
    payload = dict(deck.blocks.get(ELASTIC) or {})
    values = dict(payload.get("values") or {})
    kept: dict[str, float] = {}
    for name, number in base.values.items():
        _, key, si_unit = _KEPT_META[name]
        values[key] = number / system.convert(1.0, si_unit)
        values[f"{key}_source"] = "deck"
        kept[name] = number
    notes: list[str] = []
    if base.unread:
        notes.append(
            f"MID {base.mid}: 받은 덱의 {', '.join(base.unread)} 칸을 못 읽어 "
            "MatNexus 값을 실었습니다."
        )
    if not kept:
        return Kept(deck=deck, values={}, notes=tuple(notes))
    if payload.get("rows"):
        # 온도별 탄성 표가 있으면 덱 값 하나와 갈린다 — 받은 덱의 값을 지키기로 했으니 표를
        # 뺀다.
        payload.pop("rows")
        notes.append(
            f"MID {base.mid}: 온도별 탄성 표는 싣지 않았습니다 — 받은 덱의 값 하나로."
        )
    payload["values"] = values
    labels = " · ".join(f"{_KEPT_META[name][0]} {number:g}" for name, number in kept.items())
    provenance = [
        *(line for line in deck.provenance if not _SOURCE_LINE.match(line)),
        f"받은 덱의 값으로 둠(MID {base.mid} {base.keyword}): {labels} — 이 덱의 단위. "
        "MatNexus 는 곡선 · 그 밖의 값만 실었습니다.",
    ]
    return Kept(
        deck=replace(
            deck, blocks={**deck.blocks, ELASTIC: payload}, provenance=tuple(provenance)
        ),
        values=kept,
        notes=tuple(notes),
    )
