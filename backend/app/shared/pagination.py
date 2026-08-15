"""목록 응답 — **상한을 서버가 강제한다.**

클라이언트가 보낸 `limit` 을 그대로 믿으면 `?limit=1000000` 한 번에 서버가 죽는다.
악의가 없어도 그렇게 된다 — 화면이 "전부 보기"를 구현하면서 큰 수를 넣는다.

`total` 을 함께 주는 이유: 없으면 화면이 "다음 페이지가 있는지" 를 알기 위해
한 건 더 요청하는 식의 편법을 쓰게 되고, 그 편법은 화면마다 달라진다.
"""

from __future__ import annotations

from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
