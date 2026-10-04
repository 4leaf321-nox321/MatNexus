"""덱의 **어느 자리에 카드의 어느 값이 들어가나** — 값을 하나씩 흔들어 본다(2026-10-04).

「내보내기」 가 누르자마자 파일을 내려받던 것을, 형식마다 「이 칸에는 이 값」 을 보이고
고른 뒤에 받게 바꾸면서 생겼다. 사람이 덱을 받기 전에 「탄성계수가 어느 줄 몇째 칸으로 가나」 ·
「G 는 어디서 셈하나」 를 볼 수 있어야 한다 — 고정폭 칸이 하나 밀리면 솔버는 다른 값을
**조용히** 읽는다.

## 왜 정의를 읽지 않나

정의판(ADR 0038)이 칸 배치를 적고 있지만 셋이 모자란다.

    머리 · 탄성 · 열 줄은 정의도 코드에 맡긴다(`{"block": "elastic"}`)
    정의판이 없는 형식이 있다 — 확장이 등록한 렌더러 · 코드판만 있는 형식
    정의가 말하는 것과 실제로 나가는 것이 다를 수 있다 — 보여야 하는 것은 **나가는 것**이다

그래서 형식을 모르는 방법을 쓴다. 카드 값 하나를 0.9 배로 흔들어 덱을 다시 그리고, 글자가
바뀐 자리를 그 값의 자리로 짚는다. 표는 열 하나를 통째로 흔든다. 코드판이든 정의판이든
확장이든 **실제로 내려받을 덱 그대로**를 짚고, E 와 ν 로 셈한 G 처럼 **여러 값에서 셈한 칸**은
흔든 값 여럿이 함께 짚어서 드러난다.

## 한계 — 적어 둔다

- **0 인 값은 흔들어도 0 이다.** 표의 첫 점(소성 변형률 0)은 그 열로 안 짚힌다. 홀로 0 인
  값은 1 로 흔든다.
- **흔들면 덱이 안 나오는 값이 있다**(범위 검사). 그 값은 자리를 못 짚었다고 말한다.
- 칸 끝은 **숫자 모양**으로 넓혀 잡는다. 고정폭 칸이 꽉 차 이웃과 붙어 있으면
  (`7.85E-092.05E+05`) 지수 두 자리 뒤에서 끊는다 — 드물지만 한 글자가 이웃으로 넘칠 수 있다.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Any

from matcore.export import Deck, ExportError, Rendered, _unit_of, block_spec

#: 흔드는 배수. 자릿수가 대부분 바뀌어 칸이 통째로 드러나고, 줄이는 쪽이라 범위 검사
#: (ν < 0.5 · 단조 증가 표)를 덜 건드린다.
NUDGE = 0.9

_DIGITS = frozenset("0123456789.")
#: 지수 — 자리는 둘까지만 본다. 꽉 찬 고정폭 칸이 이웃과 붙어 있으면(`E-092.05`) 셋째 자리는
#: 이웃 칸의 것이다.
_EXPONENT = re.compile(r"[eEdD][-+]?\d{1,2}")


@dataclass(frozen=True)
class Span:
    """덱의 한 자리 — 줄은 0 부터, 칸은 `[start, end)`."""

    line: int
    start: int
    end: int


@dataclass(frozen=True)
class Placed:
    block: str
    key: str
    column: bool
    """표의 열이면 참 — 행마다 한 자리씩 짚힌다."""
    spans: tuple[Span, ...]


@dataclass(frozen=True)
class Layout:
    placed: tuple[Placed, ...]
    unused: tuple[tuple[str, str, bool], ...]
    """카드에 있는데 이 덱은 안 쓰는 값 — (블록, 키, 열)."""
    failed: tuple[tuple[str, str, bool, str], ...]
    """흔들었더니 덱이 안 나온 값 — 자리를 못 짚었다. 마지막이 그 까닭."""
    unstable: tuple[int, ...]
    """두 번 그려도 글자가 다른 줄. 그 줄은 짚지 않는다."""


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def candidates(deck: Deck) -> Iterator[tuple[str, str, bool]]:
    """흔들어 볼 값 — 블록의 숫자 값과 표의 숫자 열. `_` 로 시작하는 블록(내부 주석)은 뺀다."""
    for name, payload in deck.blocks.items():
        if name.startswith("_") or not isinstance(payload, Mapping):
            continue
        for key, value in (payload.get("values") or {}).items():
            if _number(value):
                yield name, key, False
        columns: dict[str, None] = {}
        for row in payload.get("rows") or []:
            if isinstance(row, Mapping):
                for key, value in row.items():
                    if _number(value):
                        columns.setdefault(key, None)
        for key in columns:
            yield name, key, True


def _nudged(value: Any, *, alone: bool) -> Any:
    if not _number(value):
        return value
    if isinstance(value, int):
        return value + 1
    if value == 0:
        return 1.0 if alone else 0.0
    return value * NUDGE


def nudge(deck: Deck, block: str, key: str, column: bool) -> Deck:
    """그 값 하나(열이면 그 열 전부)만 흔든 덱."""
    blocks = dict(deck.blocks)
    payload = dict(blocks[block])
    if column:
        payload["rows"] = [
            {**row, key: _nudged(row.get(key), alone=False)}
            if isinstance(row, Mapping)
            else row
            for row in payload.get("rows") or []
        ]
    else:
        values = dict(payload.get("values") or {})
        values[key] = _nudged(values[key], alone=True)
        payload["values"] = values
    blocks[block] = payload
    return replace(deck, blocks=blocks)


def _widen(line: str, start: int, end: int) -> tuple[int, int]:
    """바뀐 글자를 **숫자 하나**로 넓힌다 — 앞의 자리 · 부호, 뒤의 자리 · 지수."""
    start = max(0, min(start, len(line)))
    end = max(start, min(end, len(line)))
    while True:
        while start > 0 and line[start - 1] in _DIGITS:
            start -= 1
        # 지수 안에서 시작했으면(`E-09` 의 `09`) 가수까지 간다.
        if (
            start >= 2
            and line[start - 1] in "+-"
            and line[start - 2] in "eEdD"
            and start >= 3
            and line[start - 3] in _DIGITS
        ):
            start -= 2
            continue
        if start >= 2 and line[start - 1] in "eEdD" and line[start - 2] in _DIGITS:
            start -= 1
            continue
        break
    if start > 0 and line[start - 1] in "+-":
        start -= 1
    while end < len(line) and line[end] in _DIGITS:
        end += 1
    exponent = _EXPONENT.match(line, end)
    if exponent is not None:
        end = exponent.end()
    # 오른쪽 맞춤 칸의 앞 빈칸이 끼워 넣기로 잡힐 수 있다 — 자리는 글자만이다.
    while start < end - 1 and line[start].isspace():
        start += 1
    while end > start + 1 and line[end - 1].isspace():
        end -= 1
    return start, max(end, start + 1)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _in_line(before: str, after: str) -> list[tuple[int, int]]:
    """한 줄 안에서 바뀐 자리(앞 줄의 칸으로)."""
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    found: list[tuple[int, int]] = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i1 == i2:
            # 끼워 넣기 — 그 자리 글자에, 줄 끝이면 앞 글자에 붙인다.
            i1, i2 = (i1, i1 + 1) if i1 < len(before) else (max(0, i1 - 1), max(1, i1))
        start, end = _widen(before, i1, i2)
        # 오른쪽 맞춤 칸에서 값이 한 글자 넓어지면 앞 빈칸 하나가 「지워진 것」 으로 잡힌다 —
        # 진짜 자리는 다른 조각이 짚는다. 빈칸뿐인 자리는 버린다(LS-DYNA 열 덱에서 실측).
        if before[start:end].strip():
            found.append((start, end))
    return _merge(found)


def changed(before: list[str], after: list[str]) -> list[Span]:
    """두 덱에서 바뀐 자리(앞 덱의 줄 · 칸으로)."""
    spans: list[Span] = []
    if len(before) == len(after):
        blocks = [
            ("replace", index, index + 1, index, index + 1) for index in range(len(before))
        ]
    else:
        blocks = list(
            difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
        )
    for tag, i1, i2, j1, j2 in blocks:
        if tag == "equal" or i1 == i2:
            continue
        if i2 - i1 == j2 - j1:
            for offset in range(i2 - i1):
                old, new = before[i1 + offset], after[j1 + offset]
                if old != new:
                    spans.extend(
                        Span(i1 + offset, start, end) for start, end in _in_line(old, new)
                    )
        else:
            # 줄 수가 달라졌다(조건이 갈렸다) — 줄째 짚는다.
            spans.extend(Span(line, 0, max(1, len(before[line]))) for line in range(i1, i2))
    return spans


def locate(render: Callable[[Deck], Rendered], deck: Deck) -> Layout:
    """카드 값마다 덱의 자리를 짚는다. `render` 는 **내려받기와 같은** 그리기여야 한다."""
    base = render(deck).text.splitlines()
    again = render(deck).text.splitlines()
    unstable = tuple(
        index for index, line in enumerate(base) if index >= len(again) or again[index] != line
    )
    skip = set(unstable)

    placed: list[Placed] = []
    unused: list[tuple[str, str, bool]] = []
    failed: list[tuple[str, str, bool, str]] = []
    for block, key, column in candidates(deck):
        try:
            moved = render(nudge(deck, block, key, column)).text.splitlines()
        except ExportError as exc:
            failed.append((block, key, column, str(exc)))
            continue
        spans = tuple(span for span in changed(base, moved) if span.line not in skip)
        if spans:
            placed.append(Placed(block, key, column, spans))
        else:
            unused.append((block, key, column))
    return Layout(tuple(placed), tuple(unused), tuple(failed), unstable)


def describe(
    block: str, key: str, row: Mapping[str, Any] | None = None
) -> tuple[str, str, str | None]:
    """(블록 이름, 값 이름, SI 단위) — 블록 선언에서. 선언 안 된 값은 키 그대로다."""
    spec = block_spec(block)
    block_label = spec.label if spec is not None else block
    label = key
    if spec is not None:
        for item in (*spec.produces, *spec.rows):
            if item.key == key:
                label = item.label
                break
    return block_label, label, _unit_of(spec, key, row)
