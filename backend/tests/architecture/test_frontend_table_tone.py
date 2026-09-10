"""표 칸의 **글자 크기와 흐림**을 규칙으로 묶는다.

## 왜 (2026-09-10 지적)

*"재료 시편 시험 각 메뉴 리스트와 칼럼에 따라 폰트 달라보이고 흐릿한 폰트 있음.
두께·시료는 진하게 보이지만 번호~소속은 회색계열, 이름은 살짝 작다."*

한 줄 안에서 크기가 세 가지(`text-xs`·`text-sm`·기본)로 갈렸고, 어느 열을
흐리게 할지에 규칙이 없었다. 실제로 재료 목록은 **번호·이름이 작고 회색**인데
**두께·시료는 크고 검정**이었다 — 정작 사람이 먼저 찾는 것은 번호와 이름이다.

## 규칙 둘

    크기는 칸에 안 적는다      표 전체가 작아야 하면 <Table> 에 한 번 적는다
    값 칸을 흐리게 안 한다      흐린 것은 **값이 아닌 것**뿐이다

「값이 아닌 것」은 셋이다 — **빈 목록 안내**(`colSpan` 이 붙은 칸) · **없음
표시**(`Stamp` 의 `—` 처럼 컴포넌트 안에서) · **아이콘**(펼침 표시 따위, 칸이
아니라 아이콘에 준다).

## 왜 크기는 엄격하고 색은 느슨한가

크기는 판단이 필요 없다 — **한 줄 안에서 크기가 갈리면 그것은 위계가 아니라
사고처럼 보인다.** 그래서 칸에 적힌 것은 예외 없이 막는다.

색은 조건부로 쓰는 자리가 정당하다(`row.division === '미지정' ? 'text-muted…'`
— 「값이 없다」 를 말하는 것이다). 그래서 **조건 없이 통째로 흐린 것**만 막는다.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"

#: 칸에 적으면 안 되는 크기.
SIZES = ("text-xs", "text-sm", "text-base", "text-lg")

#: `<TableCell ...>` 여는 태그 하나. 여러 줄에 걸칠 수 있다.
CELL = re.compile(r"<TableCell\b[^>]*>", re.DOTALL)

#: 조건 없이 통째로 적은 className.
PLAIN = re.compile(r'className="([^"]*)"')


def _cells() -> list[tuple[Path, int, str]]:
    """화면 코드의 모든 표 칸 → (파일, 줄, 여는 태그)."""
    found: list[tuple[Path, int, str]] = []
    for path in sorted(SRC.rglob("*.tsx")):
        if ".test." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        if "<TableCell" not in text:
            continue
        for match in CELL.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((path, line, match.group(0)))
    return found


def test_칸에_글자_크기를_적지_않는다() -> None:
    """**표 하나 안에서는 크기가 하나다.**

    여기 걸렸다면 고칠 방법은 그 클래스를 지우는 것이다. 그 표 전체가 작아야
    하는 것이면 `<Table className="text-xs">` 에 **한 번** 적는다 — 칸마다 적으면
    다음 사람이 한 칸을 더할 때 반드시 빠뜨린다.
    """
    found = [
        f"{path.relative_to(SRC)}:{line} — {size}"
        for path, line, tag in _cells()
        for size in SIZES
        if size in tag
    ]
    assert not found, "표 칸에 글자 크기가 적혀 있습니다:\n  " + "\n  ".join(found)


def test_값_칸을_흐리게_하지_않는다() -> None:
    """**흐린 것은 값이 아닌 것뿐이다.**

    값을 흐리게 하면 사람은 그것을 「덜 중요한 것」으로 읽는다. 그런데 표의 열은
    전부 사람이 고른 열이다 — 덜 중요하면 애초에 열이 아니어야 한다.

    빈 목록 안내(`colSpan`)는 값이 아니므로 지나간다. 「없음」 은 값을 그리는
    컴포넌트 안에서 흐리게 한다(`Stamp`).
    """
    found: list[str] = []
    for path, line, tag in _cells():
        if "colSpan" in tag:
            continue
        plain = PLAIN.search(tag)
        if plain and "text-muted-foreground" in plain.group(1).split():
            found.append(f"{path.relative_to(SRC)}:{line}")
    assert not found, (
        "값 칸을 통째로 흐리게 그리고 있습니다:\n  "
        + "\n  ".join(found)
        + "\n「없음」 을 흐리게 하려는 것이면 값이 아니라 그 표시에 주세요."
    )
