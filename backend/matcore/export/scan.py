"""**예제 덱을 읽어 정의 초안을 만든다.**

빈 폼에서 시작하면 막연하다 — 무슨 줄을 몇 개 쌓아야 하는지, 칸 폭을 얼마로
둬야 하는지 화면 어디에도 없다. 그런데 **덱을 붙이려는 사람에게는 대개 그
솔버의 덱 파일이 이미 있다.** 해석을 돌려 본 사람이니까.

인풋 파일 정의가 같은 문제를 이미 풀었다(ADR 0006): 실제 파일을 올리면 구조는
코드가 읽고, **「이 열이 무엇인가」 만 사람이 정한다.** 여기도 같은 선을 긋는다.

## 읽는 것과 못 읽는 것

    읽는다                            못 읽는다
    ────────────────────────────     ──────────────────────────────
    키워드 줄인가 숫자 줄인가            어느 숫자가 탄성계수인가
    연속된 같은 모양 = 표               이 줄이 언제 빠지는가(`when`)
    구분자(쉼표냐 칸이냐)                이 표가 소성인가 Prony 인가
    **칸 폭과 지수 자릿수**

못 읽는 쪽이 곧 사람이 할 일이고, 그것이 이 화면의 요점이다.

## 칸 폭을 읽는 것이 이 파일의 값이다

`_fixed` 가 20칸을 쓰는 이유가 주석에 적혀 있다 — *「칸이 어긋나면 다른 필드로
읽힌다」*. 사람이 남의 덱을 보고 폭을 **세는** 것은 틀리기 쉽고, 틀려도 덱은
멀쩡히 나온다. 그러니 세는 일을 코드가 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: 덱에 나오는 숫자.
#:
#: **Nastran 은 지수의 `E` 를 생략한다** — `7.85-9` 가 `7.85e-9` 다. 실측
#: (2026-08-30): 그것을 `7.85` 와 `-9` 두 개로 읽어 칸이 하나 늘고 값도 틀렸다.
#:
#: 다만 **소수점이 있을 때만** 축약으로 본다. `1-2` 를 `1e-2` 로 읽으면 범위나
#: 뺄셈을 지수로 오해하는데, Nastran 관례가 `1.-2` 라 소수점이 그 경계로 쓸 만하다.
NUMBER = re.compile(
    r"[-+]?(?:"
    r"(?:\d+\.\d*|\.\d+)(?:[eEdD][-+]?\d+|[-+]\d+)?"
    r"|\d+(?:[eEdD][-+]?\d+)?"
    r")"
)

#: 이보다 좁으면 고정폭으로 안 본다. 실제 솔버 폭은 8(Nastran)·10(LS-DYNA)·
#: 16·20(Radioss) 이다. **좁은 폭까지 고정폭으로 보면** 자유 형식 덱이 고정폭
#: 정의가 되고, 값이 칸을 넘쳐 옆 필드를 밀어낸다.
MIN_FIXED_WIDTH = 8

#: 이 값 안이면 「같은 값」 으로 본다. 덱은 유효숫자를 잘라 적으므로 정확히
#: 같을 수 없다 — `2.000000000000E+11` 과 `2e11` 은 같은 값이다.
TOLERANCE = 1e-6

#: 줄 첫머리가 이것이면 **숫자가 있어도 키워드·주석이다.**
#:
#: 실측(2026-08-30): `*MATERIAL, NAME=DP600_MD` 의 `600` 이 값으로 잡혔다.
#: **재료 이름에 숫자가 흔하다** — DP600 · SPCC270 · PP_TALC20. 숫자 유무로
#: 가르면 키워드 줄이 값 줄이 되고, 사람은 그 줄을 지우고 다시 적어야 한다.
#:
#:     *   Abaqus · LS-DYNA 키워드      **  Abaqus 주석
#:     /   OpenRadioss 키워드           #   Radioss 주석
#:     $   Nastran 주석                 !   일부 솔버 주석
KEYWORD_STARTS = ("*", "/", "#", "$", "!")

#: 표로 보려면 같은 모양이 몇 줄이어야 하나. **둘이면 표라고 하기 이르다** —
#: 탄성 줄 두 개가 나란히 있는 것과 구별이 안 된다.
MIN_TABLE_ROWS = 3


@dataclass
class Cell:
    """숫자 칸 하나."""

    text: str
    value: float
    empty: bool = False
    """비운 칸인가. Nastran 자유 필드의 `,,` 가 그렇다 — **자리는 지켜야 한다.**"""
    suggested: str | None = None
    """카드의 어느 값과 같아 보이는가. **제안일 뿐이다** — 사람이 고른다."""


@dataclass
class ScannedLine:
    """읽어 낸 줄 하나. 화면의 줄 폼과 같은 모양으로 나간다."""

    kind: str
    text: str | None = None
    prefix: str = ""
    """값 앞에 붙는 글자. `MP,EX,` · `MAT1    ` 처럼."""
    cells: list[Cell] = field(default_factory=list)
    join: str = ", "
    suffix: str = ""
    width: int | None = None
    """고정폭이면 칸 폭. `None` 이면 자유 형식."""
    align: str = "right"
    """`right` 는 LS-DYNA·Radioss, `left` 는 Nastran·OptiStruct 벌크.

    **맞춤을 안 옮기면 폭만 맞고 값이 반대쪽으로 붙는다** — 그러면 이웃 필드와
    붙어 버려 솔버가 둘을 한 값으로 읽는다."""
    precision: int | None = None
    rows: int = 0
    """표라면 몇 줄이었나. 사람이 「이게 정말 표인가」 를 판단할 근거다."""


@dataclass
class Scanned:
    lines: list[ScannedLine]
    notes: list[str]
    """읽으면서 사람에게 할 말. **짐작한 자리를 숨기지 않는다.**"""


def _glued(line: str, start: int, end: int) -> bool:
    """숫자가 **글자에 붙어 있나.** 붙어 있으면 값이 아니라 이름의 일부다.

    실측(2026-08-30): HyperMesh 가 낸 OptiStruct 덱에서 `MAT1` 의 `1` 과
    `TABLES1` 의 `1` 이 값으로 잡혔다. **Nastran 벌크 데이터는 키워드 이름 안에
    숫자가 있고**(`MAT1`·`MATT1`·`TABLES1`·`PSHELL`), 주석과 달리 `$` 로 시작하지도
    않는다 — 그러면 칸이 하나 늘어난 채로 정의가 만들어지고, 그 덱은 모든 값이
    한 칸씩 밀린다.

    이 검사는 키워드 접두사보다 넓다. `NAME=DP600_MD` 의 `600` 도 여기서 걸린다.
    """
    before = line[start - 1] if start > 0 else " "
    after = line[end] if end < len(line) else " "
    return before.isalpha() or before == "_" or after.isalpha() or after == "_"


def _numbers(text: str) -> list[str]:
    """글자에 안 붙은 숫자만."""
    return [
        found.group()
        for found in NUMBER.finditer(text)
        if not _glued(text, found.start(), found.end())
    ]


def _cells(line: str) -> list[tuple[str, float | None]]:
    """줄에서 값 칸들. **빈 칸은 빈 채로 센다.**

    쉼표로 가르는 줄은 **쉼표가 칸을 정한다.** `MAT1,1,210000.,,0.3,7.85E-9` 의
    네 번째는 비어 있는데(전단탄성계수 자리 — 「기본값을 쓰라」 는 뜻), 그것을
    빼고 세면 **뒤 값이 한 칸씩 당겨져** `0.3` 이 그 자리로 간다. 솔버는 그것을
    오류로 알려 주지 않는다.

    쉼표가 없으면 공백이 가르므로 빈 칸이라는 것이 없다 — 숫자만 센다.
    """
    if "," not in line:
        out: list[tuple[str, float | None]] = []
        for raw in _numbers(line):
            try:
                out.append((raw, _value(raw)))
            except ValueError:
                continue
        return out

    pieces = line.split(",")
    if pieces and not pieces[-1].strip():
        # 줄 끝 쉼표는 칸이 아니라 꼬리다(`*DENSITY` 다음 줄이 그렇다).
        pieces.pop()

    cells: list[tuple[str, float | None]] = []
    for piece in pieces:
        found = _numbers(piece)
        if not found:
            # **첫 숫자 앞의 조각들은 접두다** — ANSYS 의 `MP,EX,` 가 그렇다.
            # 그 뒤에 나오는 빈 조각은 비운 칸이므로 자리를 지킨다.
            if not cells:
                continue
            cells.append(("", None))
            continue
        try:
            cells.append((found[0], _value(found[0])))
        except ValueError:
            cells.append(("", None))
    return cells


def _value(raw: str) -> float:
    """글자를 수로. 포트란 `D` 지수와 **Nastran 의 생략된 `E`** 를 편다."""
    text = raw.replace("D", "E").replace("d", "e")
    if "E" not in text.upper():
        # `7.85-9` → `7.85E-9`. 맨 앞 부호는 값의 부호라 건드리지 않는다.
        found = re.search(r"(?<=[\d.])[-+]\d+$", text)
        if found:
            text = f"{text[: found.start()]}E{text[found.start() :]}"
    return float(text)


def _is_keyword(line: str) -> bool:
    """키워드·주석 줄인가. **숫자 유무보다 이것이 먼저다.**"""
    return line.lstrip().startswith(KEYWORD_STARTS)


def _shape(line: str) -> tuple[int, bool, str] | None:
    """줄의 「모양」. 숫자 개수·쉼표 유무·**앞에 붙은 글자** — 표를 묶는 기준이다.

    **접두 글자가 다르면 다른 줄이다.** 실측(2026-08-30): ANSYS APDL 의
    `MP,EX,1,2.1E5` · `MP,PRXY,1,0.3` · `MP,DENS,1,7.85E-9` 가 숫자 개수만 같아
    한 표로 묶였다 — **서로 다른 물성인데 두 줄이 사라졌다.**
    """
    if _is_keyword(line):
        return None
    found = _cells(line)
    if not found:
        return None
    return len(found), "," in line, _prefix(line).strip()


def _spans(line: str) -> list[tuple[int, int]]:
    """값으로 볼 숫자들의 (시작, 끝)."""
    return [
        (found.start(), found.end())
        for found in NUMBER.finditer(line)
        if not _glued(line, found.start(), found.end())
    ]


def _widths(
    line: str, cells: list[tuple[str, float | None]]
) -> tuple[int | None, int | None, str]:
    """고정폭인가, 그렇다면 몇 칸인가.

    **간격으로 잰다.** 처음에는 줄 길이를 칸 수로 나눴는데, 그러면 `MAT1` 처럼
    **키워드가 첫 칸을 차지하는** Nastran 벌크 데이터에서 폭이 안 맞았다. 그리고
    맞춤이 두 가지다:

        오른쪽 맞춤   LS-DYNA · Radioss · 우리 `_fixed`. 숫자의 **끝**이 폭 배수.
        왼쪽 맞춤     Nastran · OptiStruct 벌크. 숫자의 **시작**이 폭 배수.

    그래서 끝 간격과 시작 간격을 차례로 보고, 어느 한쪽이 일정하면 그것이 폭이다.
    오른쪽을 먼저 보는 것은 우리가 내는 덱이 그쪽이기 때문이다.

    **쉼표가 있으면 자유 형식으로 본다.** 고정폭 덱은 칸으로만 가른다.
    """
    if "," in line:
        return None, None, "right"
    spans = _spans(line.rstrip())
    if not spans:
        return None, None, "right"
    digits = [
        len(raw.partition(".")[2].split("E")[0].split("e")[0]) for raw, _ in cells if raw
    ]
    precision = max(digits) if digits else None

    if len(spans) == 1:
        # 하나뿐이면 간격이 없다. 줄 전체를 한 칸으로 본다 — 오른쪽 맞춤이면 그것이 폭이다.
        #
        # **다만 앞에 글자가 있으면 포기한다.** `TABLES1        2` 를 16칸으로
        # 쟀었는데(2026-08-30), 실제로는 8칸 둘이고 앞칸이 키워드다. 값 하나로는
        # 알 수 없고, **틀린 폭보다 자유 형식이 안전하다** — 자유 형식은 넘치지 않는다.
        if line[: spans[0][0]].strip():
            return None, None, "right"
        width = spans[0][1]
        return (
            (width, precision, "right") if width >= MIN_FIXED_WIDTH else (None, None, "right")
        )

    for at in (1, 0):  # 끝 먼저, 그다음 시작
        gaps = {spans[i + 1][at] - spans[i][at] for i in range(len(spans) - 1)}
        if len(gaps) != 1:
            continue
        width = gaps.pop()
        # **간격만으로는 모자란다.** 첫 칸이 그 폭이 아닐 수 있다 —
        # `1.0E+00 22.0E+00` 은 끝 간격이 9지만 첫 숫자가 7에서 끝난다. 자리마다
        # 폭의 배수여야 진짜 칸이고, 아니면 값이 한 칸씩 밀린 채로 나간다.
        if width >= MIN_FIXED_WIDTH and all(span[at] % width == 0 for span in spans):
            return width, precision, "right" if at == 1 else "left"
    return None, None, "right"


def _prefix(line: str) -> str:
    """첫 숫자 앞에 붙은 글자.

    **값 앞에 글자가 붙는 솔버가 있다.** ANSYS APDL 은 `MP,EX,1,2.1E5` 처럼
    명령·물성 이름이 같은 줄에 오고, Nastran 벌크는 `MAT1` 이 첫 칸을 차지한다.
    그것을 못 담으면 그 솔버는 **아예 정의로 못 붙인다.**

    공백까지 그대로 둔다 — 고정폭에서는 그 공백이 칸을 채우는 몫이다.
    """
    spans = _spans(line)
    return line[: spans[0][0]] if spans else ""


def _suggest(value: float, known: dict[str, float]) -> str | None:
    """이 숫자가 카드의 어느 값인가.

    **이것이 「막연하다」 를 실제로 없애는 자리다.** 덱을 올린 사람은 그 덱이
    자기 재료의 것임을 아는데, 화면은 숫자만 본다 — 카드 값과 맞춰 보면 이름을
    붙일 수 있다.

    맞는 것이 여럿이면 **아무것도 제안하지 않는다.** 0 이나 1 같은 값은 여러
    자리에 나오고, 그때 하나를 고르는 것은 짐작이다.
    """
    hits = [
        name
        for name, other in known.items()
        if other != 0 and abs(value - other) <= abs(other) * TOLERANCE
    ]
    return hits[0] if len(hits) == 1 else None


def scan(text: str, known: dict[str, float] | None = None) -> Scanned:
    """예제 덱 하나를 줄 초안으로.

    `known` 은 카드에서 뽑은 `{"elastic.density": 7850.0, ...}`. **`matcore` 는
    카드를 모른다** — 앱이 뽑아서 dict 로 준다(인풋 프로파일과 같은 규칙).
    """
    known = known or {}
    raw_lines = text.replace("\r\n", "\n").split("\n")
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()

    lines: list[ScannedLine] = []
    notes: list[str] = []
    index = 0
    while index < len(raw_lines):
        line = raw_lines[index]
        shape = _shape(line)
        if shape is None:
            # 키워드·주석이거나 숫자가 없다. **그대로 쓴다.**
            lines.append(ScannedLine(kind="text", text=line))
            index += 1
            continue

        # 같은 모양이 이어지면 표다.
        run = index
        while run + 1 < len(raw_lines) and _shape(raw_lines[run + 1]) == shape:
            run += 1
        count = run - index + 1
        if count < MIN_TABLE_ROWS:
            # **표가 아니면 묶지 않는다.** 묶어 놓고 한 줄만 내면 나머지가 조용히
            # 사라진다 — 값 줄 둘이 하나가 되고, 없어진 줄은 화면 어디에도 없다.
            run = index
            count = 1

        cells = _cells(line)
        width, precision, align = _widths(line, cells)
        prefix = _prefix(line)
        if width is not None and not prefix.strip():
            # **고정폭에서 앞 공백은 접두 글자가 아니라 첫 칸의 패딩이다.**
            # 그대로 접두로 내면 패딩이 두 번 들어가 줄 전체가 밀린다.
            prefix = ""

        made = ScannedLine(
            kind="rows" if count >= MIN_TABLE_ROWS else "fields",
            prefix=prefix,
            cells=[
                Cell(
                    text=raw,
                    value=value if value is not None else 0.0,
                    empty=value is None,
                    # **빈 칸에는 이름을 안 붙인다.** 0 으로 읽어 「0 인 값」 을
                    # 제안하면 비워 둔 자리가 값으로 채워진다.
                    suggested=None if value is None else _suggest(value, known),
                )
                for raw, value in cells
            ],
            join=", " if "," in line else "",
            suffix="," if line.rstrip().endswith(",") and len(cells) == 1 else "",
            width=width,
            align=align,
            precision=precision,
            rows=count if count >= MIN_TABLE_ROWS else 0,
        )
        lines.append(made)

        if made.kind == "rows":
            notes.append(
                f"{index + 1}번째 줄부터 {count}줄이 같은 모양이라 **표 한 벌**로 봤습니다 — "
                f"아니면 줄 종류를 '값' 으로 바꾸세요."
            )
        if width is not None:
            notes.append(
                f"{index + 1}번째 줄은 쉼표가 없고 {width}칸으로 나뉘어 **고정폭**으로 "
                f"봤습니다. 칸이 어긋나면 솔버가 다른 필드로 읽으니 확인해 주세요."
            )
        index = run + 1

    # **주석이 표를 두 동강 낼 수 있다.** HyperMesh 는 카드마다 이름·색 주석을
    # 넣는다 — 그러면 같은 모양의 줄이 주석으로 갈려 표로 안 묶인다.
    #
    # 그렇다고 주석을 건너뛰고 이어 붙이지는 **않는다**: 그 주석은 덱에 있던
    # 것이라 정의에도 남아야 하고, 무엇보다 **거기가 진짜 경계일 수 있다**(다른
    # 재료의 표가 이어지는 자리). 대신 그런 자리가 있으면 말한다.
    tally: dict[tuple[int, bool, str], int] = {}
    for one in lines:
        if one.kind == "fields" and one.cells:
            shape = (len(one.cells), one.join == ", ", one.prefix.strip())
            tally[shape] = tally.get(shape, 0) + 1
    scattered = sum(count for count in tally.values() if count >= MIN_TABLE_ROWS)
    if scattered:
        notes.append(
            f"같은 모양의 값 줄 {scattered}개가 주석이나 빈 줄로 나뉘어 있어 **표로 묶지 "
            f"않았습니다.** 한 표가 맞으면 줄 종류를 '표' 로 바꾸고 나머지를 지우세요 — "
            f"주석이 거기서 표를 가르는 것이 맞을 수도 있어 이쪽이 판단하지 않았습니다."
        )

    named = sum(1 for one in lines for cell in one.cells if cell.suggested)
    if named:
        notes.append(
            f"고른 카드의 값과 같은 숫자 {named}개에 이름을 붙였습니다 — **짐작입니다.** "
            f"맞는지 보고 나머지는 직접 채워 주세요."
        )
    elif known:
        notes.append(
            "덱의 숫자 중 고른 카드의 값과 같은 것이 없습니다 — 다른 재료의 덱이거나 "
            "단위계가 다를 수 있습니다."
        )
    return Scanned(lines=lines, notes=notes)


def as_payload(found: Scanned) -> dict[str, Any]:
    """응답 모양으로. 화면의 줄 폼이 그대로 받는다."""
    return {
        "lines": [
            {
                "kind": one.kind,
                "text": one.text,
                "prefix": one.prefix,
                "join": one.join,
                "suffix": one.suffix,
                "width": one.width,
                "align": one.align,
                "precision": one.precision,
                "rows": one.rows,
                "cells": [
                    {
                        "text": cell.text,
                        "value": cell.value,
                        "empty": cell.empty,
                        "suggested": cell.suggested,
                    }
                    for cell in one.cells
                ],
            }
            for one in found.lines
        ],
        "notes": found.notes,
    }
