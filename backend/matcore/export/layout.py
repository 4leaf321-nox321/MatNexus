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
- 칸 끝은 **숫자 모양**으로 넓혀 잡되, **다른 값을 흔들어 바뀐 칸**에서 멈춘다. 고정폭 칸이 꽉
  차 이웃과 붙어 있으면(`7853.212.0567E+11`) 숫자 모양만으로는 어디서 끊을지 모른다 — 이웃을
  흔들어 바뀐 칸이 그 경계다. 두 값 모두 안 바뀐 글자(이웃의 끝자리 0 같은)는 여전히 한쪽으로
  넘칠 수 있다.

## 자리가 이웃 칸으로 번지던 것 (2026-10-06)

칸 배치에서 SIGY 를 누르면 바로 앞 PR 까지 칠해졌다. 원인 둘:

- 오른쪽 맞춤 칸에서 값이 한 글자 넓어지면 앞 빈칸이 「바뀐 칸」 이 되고, 넓히기가 그 빈칸에서
  왼쪽 숫자(PR 의 `0.3`)로 건너갔다 — 보통 덱에서도 SIGY 의 자리가 `0.3 3.0123E+8` 이었다.
  이제 빈칸은 **넓히기 전에** 뗀다(전에는 넓힌 뒤에 뗐다).
- 꽉 찬 칸끼리 붙은 덱에서는 숫자 모양으로 넓히기가 이웃 숫자를 통째로 먹었다(밀도 · E · PR 이
  한 자리). 이제 넓히기는 다른 값이 바꾼 칸에서 멈추고, 값을 **두 번** 흔들어(0.9 · 0.6
  배) 바뀐 칸을 늘린다 — 0.9 배로는 앞자리가 그대로인 값이 있다(250 → 225 의 「2」).
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
#: 한 번 더 흔드는 배수 — 0.9 배로 안 바뀐 앞자리(250 → 225 의 「2」)를 드러낸다. 그 글자를
#: 넓히기로만 잡으면, 칸이 꽉 차 이웃과 붙어 있을 때 어디서 끊을지 모른다. 이것으로 흔들면 덱이
#: 안 나오거나 줄 짜임이 달라지면(조건이 갈렸다) 첫 번만 쓴다.
SECOND_NUDGE = 0.6

_DIGITS = frozenset("0123456789.")
#: 지수 — 자리는 둘까지만 본다. 꽉 찬 고정폭 칸이 이웃과 붙어 있으면(`E-092.05`) 셋째 자리는
#: 이웃 칸의 것이다.
_EXPONENT = re.compile(r"[eEdD][-+]?\d{1,2}")
_EXPONENT_TAIL = re.compile(r"[-+]?\d{1,2}")
_EXPONENT_DIGITS = re.compile(r"\d{1,2}")
#: 숫자 **하나**의 모양. 넓힌 자리가 이것이 아니면(점이 둘 · 지수 뒤에 또 숫자) 이웃 칸과
#: 붙은 것이다.
_ONE_NUMBER = re.compile(r"[-+]?(\d+\.?\d*|\.\d+)([eEdD][-+]?\d+)?")


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


def _nudged(value: Any, *, alone: bool, factor: float = NUDGE) -> Any:
    if not _number(value):
        return value
    if isinstance(value, int):
        return value + 1
    if value == 0:
        return 1.0 if alone else 0.0
    return value * factor


def nudge(deck: Deck, block: str, key: str, column: bool, factor: float = NUDGE) -> Deck:
    """그 값 하나(열이면 그 열 전부)만 흔든 덱."""
    blocks = dict(deck.blocks)
    payload = dict(blocks[block])
    if column:
        payload["rows"] = [
            {**row, key: _nudged(row.get(key), alone=False, factor=factor)}
            if isinstance(row, Mapping)
            else row
            for row in payload.get("rows") or []
        ]
    else:
        values = dict(payload.get("values") or {})
        values[key] = _nudged(values[key], alone=True, factor=factor)
        payload["values"] = values
    blocks[block] = payload
    return replace(deck, blocks=blocks)


#: 넓히기를 막는 칸 — 칸 번호를 받아 참이면 거기서 멈춘다.
Blocked = Callable[[int], bool]


def _never(_column: int) -> bool:
    return False


def _widen(line: str, start: int, end: int, blocked: Blocked = _never) -> tuple[int, int]:
    """바뀐 글자를 **숫자 하나**로 넓힌다 — 앞의 자리 · 부호, 뒤의 자리 · 지수.

    `blocked` 는 **다른 값이 바꾼 칸**이다. 넓히다 거기 닿으면 멈춘다 — 꽉 찬 고정폭 칸끼리
    붙어 있으면(`7853.212.0567E+11`) 숫자 모양만으로는 어디서 끊을지 모른다.
    """
    start = max(0, min(start, len(line)))
    end = max(start, min(end, len(line)))
    while True:
        while start > 0 and line[start - 1] in _DIGITS and not blocked(start - 1):
            start -= 1
        # 지수 안에서 시작했으면(`E-09` 의 `09`) 가수까지 간다 — 그 가수가 남의 것이 아닐 때만.
        if (
            start >= 3
            and line[start - 1] in "+-"
            and line[start - 2] in "eEdD"
            and line[start - 3] in _DIGITS
            and not any(blocked(column) for column in (start - 1, start - 2, start - 3))
        ):
            start -= 2
            continue
        if (
            start >= 2
            and line[start - 1] in "eEdD"
            and line[start - 2] in _DIGITS
            and not (blocked(start - 1) or blocked(start - 2))
        ):
            start -= 1
            continue
        break
    # 앞의 부호 — 이웃 지수의 부호(`E-` 의 `-`)는 아니다.
    if (
        start > 0
        and line[start - 1] in "+-"
        and not blocked(start - 1)
        and not (start >= 2 and line[start - 2] in "eEdD")
    ):
        start -= 1
    while end < len(line) and line[end] in _DIGITS and not blocked(end):
        end += 1
    # 지수 — 바뀐 칸이 지수 한가운데서 끝났으면(`…946341E` | `-01`) 그 지수를 마저 잡는다.
    # 줄 전체를 맞춰 보는 비교가 그렇게 끊는다(Nastran 소성 표, 2026-10-06).
    if end >= 2 and line[end - 1] in "+-" and line[end - 2] in "eEdD":
        exponent = _EXPONENT_DIGITS.match(line, end)
    elif end >= 1 and line[end - 1] in "eEdD":
        exponent = _EXPONENT_TAIL.match(line, end)
    else:
        exponent = _EXPONENT.match(line, end)
    if exponent is not None and not any(
        blocked(column) for column in range(end, exponent.end())
    ):
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


def _runs(before: str, after: str) -> list[tuple[int, int]]:
    """한 줄에서 **글자가 바뀐 칸**(앞 줄의 칸으로) — 아직 넓히지 않는다."""
    runs: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i1 == i2:
            # 끼워 넣기 — 그 자리 글자에, 줄 끝이면 앞 글자에 붙인다.
            i1, i2 = (i1, i1 + 1) if i1 < len(before) else (max(0, i1 - 1), max(1, i1))
        runs.append((i1, i2))
    return runs


def _raw(
    before: list[str], after: list[str]
) -> tuple[dict[int, list[tuple[int, int]]], set[int]]:
    """두 덱에서 바뀐 칸(앞 덱의 줄 · 칸, 넓히기 전)과 **줄째 바뀐 줄**(줄 수가 달라졌다)."""
    runs: dict[int, list[tuple[int, int]]] = {}
    whole: set[int] = set()
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
                    runs.setdefault(i1 + offset, []).extend(_runs(old, new))
        else:
            # 줄 수가 달라졌다(조건이 갈렸다) — 줄째 짚는다.
            whole.update(range(i1, i2))
    return runs, whole


def _spans(line: str, runs: list[tuple[int, int]], blocked: Blocked) -> list[tuple[int, int]]:
    """바뀐 칸을 자리로 — **빈칸을 먼저 떼고** 글자 덩어리마다 숫자 하나로 넓힌다.

    오른쪽 맞춤 칸에서 값이 넓어지면 앞 빈칸이 바뀐 칸에 든다. 그 빈칸에서 넓히기를 시작하면
    왼쪽 이웃의 숫자로 건너간다(2026-10-06: SIGY 의 자리가 `0.3 3.0123E+8`).

    경계(`blocked`)는 넓힌 것이 **숫자 하나의 모양이 아닐 때만** 쓴다 — 이웃 칸과 붙은 것이다.
    처음부터 쓰면 여러 값에서 셈한 칸(Nastran 소성 표의 총변형률 = 소성 변형률 + 응력/E)이
    값마다 다른 자릿수에서 끊겨, 한 칸이 조각난다.
    """
    found: list[tuple[int, int]] = []
    for start, end in runs:
        at = start
        while at < end:
            if line[at].isspace():
                at += 1
                continue
            piece = at
            while at < end and not line[at].isspace():
                at += 1
            wide = _widen(line, piece, at)
            if not _ONE_NUMBER.fullmatch(line[wide[0] : wide[1]]):
                wide = _widen(line, piece, at, blocked)
            found.append(wide)
    return _merge(found)


def changed(before: list[str], after: list[str]) -> list[Span]:
    """두 덱에서 바뀐 자리(앞 덱의 줄 · 칸으로). 다른 값의 경계는 모른다 — `locate` 가 안다."""
    runs, whole = _raw(before, after)
    spans = [Span(line, 0, max(1, len(before[line]))) for line in sorted(whole)]
    for line in sorted(runs):
        spans.extend(
            Span(line, start, end) for start, end in _spans(before[line], runs[line], _never)
        )
    return sorted(spans, key=lambda one: (one.line, one.start))


def locate(render: Callable[[Deck], Rendered], deck: Deck) -> Layout:
    """카드 값마다 덱의 자리를 짚는다. `render` 는 **내려받기와 같은** 그리기여야 한다."""
    base = render(deck).text.splitlines()
    again = render(deck).text.splitlines()
    unstable = tuple(
        index for index, line in enumerate(base) if index >= len(again) or again[index] != line
    )
    skip = set(unstable)

    # 1) 값마다 바뀐 칸 — 넓히기 전. 두 번 흔든다(`SECOND_NUDGE`).
    found: dict[tuple[str, str, bool], tuple[dict[int, list[tuple[int, int]]], set[int]]] = {}
    unused: list[tuple[str, str, bool]] = []
    failed: list[tuple[str, str, bool, str]] = []
    for block, key, column in candidates(deck):
        try:
            moved = render(nudge(deck, block, key, column)).text.splitlines()
        except ExportError as exc:
            failed.append((block, key, column, str(exc)))
            continue
        runs, whole = _raw(base, moved)
        if not whole:
            try:
                more = render(nudge(deck, block, key, column, SECOND_NUDGE)).text.splitlines()
            except ExportError:
                more = None
            if more is not None:
                extra, extra_whole = _raw(base, more)
                if not extra_whole:
                    for line, found_runs in extra.items():
                        runs.setdefault(line, []).extend(found_runs)
        runs = {line: _merge(cut) for line, cut in runs.items() if line not in skip}
        whole -= skip
        if runs or whole:
            found[(block, key, column)] = (runs, whole)
        else:
            unused.append((block, key, column))

    # 2) 칸마다 그 칸을 바꾼 값들 — 넓히기의 경계다.
    owners: dict[int, list[tuple[int, int, tuple[str, str, bool]]]] = {}
    for name, (runs, _whole) in found.items():
        for line, cut in runs.items():
            owners.setdefault(line, []).extend((start, end, name) for start, end in cut)

    def blocked_for(name: tuple[str, str, bool], line: int) -> Blocked:
        marks = owners.get(line, [])

        def blocked(column: int) -> bool:
            mine = False
            other = False
            for start, end, owner in marks:
                if start <= column < end:
                    if owner == name:
                        mine = True
                    else:
                        other = True
            return other and not mine

        return blocked

    # 3) 자리 — 바뀐 칸을 숫자 하나로 넓히되 남이 바꾼 칸에서 멈춘다.
    placed: list[Placed] = []
    for (block, key, column), (runs, whole) in found.items():
        spans = [Span(line, 0, max(1, len(base[line]))) for line in sorted(whole)]
        for line in sorted(runs):
            spans.extend(
                Span(line, start, end)
                for start, end in _spans(
                    base[line], runs[line], blocked_for((block, key, column), line)
                )
            )
        placed.append(
            Placed(
                block, key, column, tuple(sorted(spans, key=lambda one: (one.line, one.start)))
            )
        )
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
