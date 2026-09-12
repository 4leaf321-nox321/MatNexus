"""거르기 목록(facet)의 공통 조각 — 여러 목록 화면이 같은 규약을 쓴다.

시험 목록이 먼저 만들었고(`tests/routes.py`), 시편 목록이 같은 것을 쓰게 되면서
여기로 올렸다(2026-09-12). 모듈끼리 직접 부르지 않는다는 규칙 때문이다.
"""

from __future__ import annotations

from pydantic import BaseModel

#: 「값이 없는 것」 을 가리키는 거르기 표식.
#:
#: **왜 별도 매개변수가 아니라 표식인가.** 거르기 목록은 서버가 준 `{key, label,
#: count}` 를 그대로 그린다 — 화면은 그 key 를 되돌려 보낼 뿐 뜻을 모른다. 여기에
#: `division_empty=true` 같은 칸을 더하면 거를 수 있는 열마다 매개변수가 하나씩
#: 늘고, 화면이 열마다 다른 길을 알아야 한다.
#:
#: 진짜 값과 겹칠 위험이 있지만, 사업부·시험자·규격에 이 글자를 그대로 적는
#: 일은 없다고 본다. 겹치면 그 값으로 거르는 대신 빈 것이 걸린다 — **틀린 값이
#: 저장되는 종류의 사고는 아니다.**
EMPTY_FILTER_KEY = "__none__"

#: 빈 것을 가리키는 이름. 화면이 그대로 그린다.
EMPTY_FILTER_LABEL = "(없음)"


class FacetOut(BaseModel):
    """거를 수 있는 값 하나와 **그것이 몇 건인가.**

    화면이 한 쪽에서 세면 안 된다 — 50건만 받아 세면 「인장시험 50」이라고
    적히는데 실제로는 300건일 수 있고, 그러면 필터 옆의 숫자가 거짓말을 한다.
    """

    key: str
    label: str
    count: int


def empty_row(pairs: list[tuple[object, int]]) -> FacetOut | None:
    """빈 값의 수. **없으면 줄을 안 낸다** — 0 짜리 줄은 고를 수 없는 선택지다.

    빈 것을 못 고르면 「규격을 안 적은 시편」 을 찾을 길이 목록을 눈으로 훑는
    것뿐이다. 스무 건이면 되지만 이백 건이면 안 된다.
    """
    total = sum(count for value, count in pairs if value is None or value == "")
    if total == 0:
        return None
    return FacetOut(key=EMPTY_FILTER_KEY, label=EMPTY_FILTER_LABEL, count=total)


def with_empty(rows: list[FacetOut], pairs: list[tuple[object, int]]) -> list[FacetOut]:
    """**「없음」 은 늘 끝에 둔다.** 값들 사이에 가나다순에 끼면 눈이 못 찾는다."""
    blank = empty_row(pairs)
    return [*rows, blank] if blank is not None else rows


def plain_rows(pairs: list[tuple[object, int]]) -> list[FacetOut]:
    """값이 곧 이름인 축(로트·규격·방향) — 가나다순, 빈 것은 끝에."""
    rows = sorted(
        (
            FacetOut(key=str(value), label=str(value), count=count)
            for value, count in pairs
            if value
        ),
        key=lambda one: one.label,
    )
    return with_empty(rows, pairs)
