"""목록 정렬 — **서버가 정렬한다.**

## 왜 화면이 하면 안 되나

거르기와 같은 이유다. 화면에서 정렬하면 **그 쪽에 실린 것만** 정렬된다 — 50건짜리
화면에서 「등록 일시 오래된 순」 을 눌렀는데 두 번째 쪽에 더 오래된 것이 있으면,
사람은 첫 줄을 「가장 오래된 것」 으로 읽는다. 그건 조용히 틀리는 자리다.

## 고를 수 있는 열을 화면이 정하지 않는다

각 목록이 **자기가 정렬할 수 있는 열**을 표로 들고, 모르는 이름이 오면 거절한다.
자유 문자열을 그대로 `order_by` 에 넣으면 그것은 SQL 주입의 자리이고, 오타가
조용히 「기본 정렬」 로 떨어지면 사람은 눌렀는데 아무 일이 없다고 느낀다.

## 늘 결정적이다

정렬 키가 같은 행이 여럿이면 DB 는 순서를 보장하지 않는다 — 그러면 **같은 요청이
쪽마다 다른 것을 준다.** 2쪽에서 봤던 줄이 3쪽에 또 나오고 어떤 줄은 아예 안
보인다. 그래서 마지막에 항상 `id` 를 덧붙인다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import UnaryExpression

from app.shared.errors import AppError


def order_by(
    columns: Mapping[str, Any],
    *,
    sort: str | None,
    desc: bool,
    default: str,
    tiebreaker: Any,
) -> Sequence[UnaryExpression[Any]]:
    """정렬 절을 만든다. `columns` 가 **고를 수 있는 열의 전부**다.

    `default` 는 `sort` 가 비었을 때 쓴다 — 목록마다 「아무것도 안 골랐을 때
    무엇이 위에 오는가」 가 다르다.
    """
    key = (sort or default).strip()
    target = columns.get(key)
    if target is None:
        raise AppError(
            "MNX-COMMON-0007",
            f"'{key}' 로는 정렬할 수 없습니다. 고를 수 있는 것: {', '.join(sorted(columns))}",
            status=422,
        )
    first = target.desc() if desc else target.asc()
    # **마지막은 늘 id 다.** 같은 값이 여럿일 때 순서가 흔들리면 쪽 넘김이 깨진다.
    return (first, tiebreaker.asc())
