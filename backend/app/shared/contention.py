"""동시에 만들면 부딪히는 자리 — **번호를 다시 받는다.**

## 무엇이 부딪히나

번호를 `max(seq_no) + 1` 로 받는 자리가 셋이다(시료·시편·시험 회차). 두 사람이
같은 순간에 만들면 **둘 다 같은 번호를 읽는다** — 실측으로 확인했다(2026-08-28):

    두 세션이 읽은 다음 번호: A=1 B=1
    A 커밋: 성공
    B 커밋: IntegrityError — 중복된 키 "uq_samples_material_seq_no"

**데이터는 안전하다.** 유니크 제약이 막으므로 같은 번호가 둘 생기지는 않는다.
문제는 **두 번째 사람이 500 을 본다**는 것이다 — 자기가 뭘 잘못했는지 알 수 없고,
다시 눌러 보는 것 말고 할 수 있는 일이 없다.

## 왜 잠그지 않나

`SELECT ... FOR UPDATE` 로 재료 행을 잠그면 안 부딪힌다. 그런데 그러면 **한 재료
아래 시료를 만드는 동안 그 재료 전체가 잠긴다** — 일괄 등록이 수백 건을 넣는
동안 다른 사람은 그 재료를 못 만진다. 부딪히는 일은 드물고 잠그는 비용은 늘
드므로, 부딪혔을 때만 다시 하는 편이 싸다.

## 왜 그냥 재시도가 맞나

**번호는 사람이 고른 값이 아니다.** 「그 방향에서 몇 번째로 자른 것인가」 이므로,
다시 받아도 사람이 기대한 것과 다르지 않다. 이름은 다르다 — 사람이 정한 값이라
말없이 바꾸면 안 되고, 그때는 읽을 수 있는 409 를 낸다.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.shared.errors import Conflict

#: 몇 번까지 다시 해 보나. **넉넉할 이유가 없다** — 세 번 연속 부딪히면 동시
#: 사용자가 아니라 다른 문제다(같은 번호를 우겨 넣고 있거나).
ATTEMPTS = 3


def with_retry[T](
    db: Session,
    make: Callable[[], T],
    *,
    code: str,
    message: str,
    attempts: int = ATTEMPTS,
) -> T:
    """번호가 부딪히면 **다시 받아 만든다.**

    `make` 는 번호를 읽는 것부터 `flush` 까지를 한다 — 다시 부를 때 **번호도 다시
    읽어야** 하기 때문이다. 바깥에서 번호를 정해 넘기면 재시도가 같은 번호로
    또 부딪힌다.

    커밋은 부르는 쪽이 한다. 여기서 커밋하면 한 요청 안의 다른 변경이 함께
    나가 버린다.
    """
    for remaining in range(attempts - 1, -1, -1):
        try:
            return make()
        except IntegrityError:
            # **세션을 되돌린다.** 실패한 flush 뒤에는 그 세션으로 아무것도 못 한다.
            db.rollback()
            if remaining == 0:
                raise Conflict(code, message) from None
    raise AssertionError("닿지 않는다")  # pragma: no cover
