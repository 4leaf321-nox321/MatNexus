"""파일을 다 읽고 나서 **다른 모듈이 할 일.**

## 왜 훅인가

읽기가 끝나면 도메인마다 따라올 일이 생긴다. 점탄성이 그렇다 — 장비가 이미 겹쳐
준 표가 파일에 들어 있으면, 그것을 `MasterCurve` 로 등록해 둬야 Prony 도 글로벌
피팅도 쓸 수 있다.

그 일을 **`tests` 모듈이 직접 하면 안 된다.** 파싱이 점탄성 서비스를 부르는 순간
모듈이 서로를 부르게 되고(`tests/architecture` 가 막는다), 도메인이 늘 때마다
파싱이 새 도메인을 알아야 한다.

그래서 반대로 한다 — **할 일이 있는 쪽이 자기를 등록한다.** 파싱은 「이 시험을 다
읽었다」 만 알리고, 무엇을 할지는 등록한 쪽이 안다(`vocabulary_hooks` 와 같은 판단).

## 훅은 읽기를 실패시키지 않는다

훅에서 난 예외는 잡아서 **경고로 바꾼다.** 마스터커브 자동 등록이 실패했다고 파일
읽기 자체를 실패로 만들면, 곡선도 요약값도 다 있는 시험이 「읽지 못했습니다」 가
된다 — 잃는 것이 훨씬 크다.

대신 **조용히 넘기지 않는다.** 훅이 돌려준 말과 예외 메시지는 시험의 경고로 남아
상세 화면에 그대로 뜬다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.modules.tests.models import TestRun

logger = logging.getLogger(__name__)

#: 훅 하나. 남길 말이 있으면 돌려준다 — 그것이 시험의 경고가 된다.
Hook = Callable[[Session, TestRun], list[str]]

_HOOKS: list[tuple[str, Hook]] = []


def on_parsed(name: str, hook: Hook) -> None:
    """읽기가 끝나면 부를 일을 등록한다. `name` 은 로그와 오류 문구에 쓴다.

    같은 이름을 두 번 등록하면 뒤엣것으로 바꾼다 — 모듈이 두 번 import 되는
    경로(테스트가 앱을 여러 번 만든다)에서 훅이 쌓이면 같은 일을 두 번 한다.
    """
    for index, (existing, _) in enumerate(_HOOKS):
        if existing == name:
            _HOOKS[index] = (name, hook)
            return
    _HOOKS.append((name, hook))


def fire_parsed(db: Session, run: TestRun) -> list[str]:
    """등록된 훅을 전부 부르고, 남길 말을 모아 돌려준다."""
    notes: list[str] = []
    for name, hook in _HOOKS:
        try:
            notes.extend(hook(db, run))
        except Exception as exc:  # 훅의 버그가 읽기를 죽이지 않는다
            logger.exception("파싱 훅 실패 (%s, run=%s)", name, run.id)
            notes.append(f"{name} 처리 중 오류가 났습니다: {exc}")
    return notes


def clear() -> None:
    """테스트 전용."""
    _HOOKS.clear()
