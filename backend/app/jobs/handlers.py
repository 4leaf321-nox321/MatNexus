"""작업 종류 → 처리 함수 레지스트리.

핸들러는 여기에 등록만 하면 워커가 집어간다. matcore 의 플러그인 레지스트리와
같은 방식이다 — 새 작업 종류를 더할 때 워커 루프를 고치지 않는다.

핸들러 안에서 예외를 삼키지 않는다. 던지면 워커가 잡아서 재시도하고, 한도를
넘기면 `failed` 로 남겨 사람이 보게 한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

Handler = Callable[[Session, dict[str, Any]], None]

_HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        if kind in _HANDLERS:
            raise ValueError(f"작업 종류 중복: {kind}")
        _HANDLERS[kind] = fn
        return fn

    return decorator


def get(kind: str) -> Handler:
    try:
        return _HANDLERS[kind]
    except KeyError:
        raise KeyError(f"등록되지 않은 작업 종류: {kind}") from None


def known_kinds() -> list[str]:
    return sorted(_HANDLERS)


def load_all() -> None:
    """핸들러를 등록하는 모듈들을 불러온다.

    워커와 테스트가 같은 함수를 부르게 해서, "테스트에서는 되는데 워커에서는
    핸들러가 없다"는 어긋남이 생기지 않게 한다.
    """
    from app.modules.notifications import jobs as _notification_jobs  # noqa: F401
    from app.modules.tests import jobs as _test_jobs  # noqa: F401
