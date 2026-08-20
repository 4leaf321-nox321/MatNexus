"""어휘 값 이름이 바뀔 때 따라와야 하는 일.

## 왜 훅인가

어휘 값의 표기를 고치면 그 값을 쓰는 쪽에서 할 일이 생길 수 있다. 강종이
그렇다 — 강종은 재료 이름을 만들므로(ADR 0004) 값이 바뀌면 재료·시료·시편·
시험 이름을 전부 다시 계산해야 한다.

그 일을 **어휘 모듈이 직접 하면 안 된다.** 어휘가 재료 서비스를 부르는 순간
모듈이 서로를 부르게 되고(`tests/architecture` 가 막는다), 축이 늘어날 때마다
어휘 모듈이 새 도메인을 알아야 한다.

그래서 반대로 한다 — **쓰는 쪽이 자기 뒤처리를 등록한다.** 어휘는 "이 축의
값 이름이 바뀌었다" 만 알리고, 무엇을 해야 하는지는 등록한 쪽이 안다.

## 왜 `shared` 인가

훅 표가 어느 한 모듈에 있으면 다른 모듈이 그것을 import 해야 한다. 공통 규칙은
`shared` 를 거친다(CLAUDE.md).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

#: 축 slug → 그 축의 값 이름이 바뀌었을 때 부를 것들.
#:
#: 인자는 (세션, 바뀐 값의 id). **값 자체는 안 넘긴다** — 받는 쪽이 필요하면
#: 자기가 읽는다. 넘기기 시작하면 어휘의 모양이 훅 계약에 스며든다.
RenameHook = Callable[[Session, uuid.UUID], None]

_HOOKS: dict[str, list[RenameHook]] = {}


def on_rename(slug: str, hook: RenameHook) -> None:
    """이 축의 값 이름이 바뀌면 이것도 해 달라고 등록한다.

    등록은 모듈이 import 될 때 한 번 일어난다 — 라우터를 조립하는 `app.main`
    이 그 시점을 만든다.
    """
    _HOOKS.setdefault(slug, []).append(hook)


def fire_rename(db: Session, slug: str, term_id: uuid.UUID) -> None:
    """등록된 것들을 부른다. 없으면 아무 일도 안 한다."""
    for hook in _HOOKS.get(slug, ()):
        hook(db, term_id)
