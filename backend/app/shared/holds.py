"""시험의 **물성 사용 보류** — 판정 하나(2026-11-14, VOC 60).

문제가 의심되는 시험을 「쓰지 말라」 고 표시할 자리가 없었다. 메모에 적어도 채택 · 카드 ·
통계는 몰랐고, 시험 메모는 MCP 응답에 실리지 않아 AI 도 몰랐다. 이제 `TestRun.hold_reason` 이
그 자리다.

- **걸고 푸는 것은 자료 관리자다**(`permissions.require_steward`) — 등록자가 자기 시험을 풀 수
  있으면 보류가 뜻이 없다.
- 걸리면 **채택 · 카드 생성을 막고**(`require_usable`), 통계 · 분석 · 글로벌 피팅에서 **뺀다**
  (`usable`). 이미 만든 카드는 값이 불변이라 **비고**를 붙인다(`tests.routes`).
- 사람과 AI 에 같은 규칙이다 — 판정이 여기 하나라 경로마다 갈리지 않는다.
"""

from __future__ import annotations

from typing import Protocol

from app.shared.errors import Conflict


class _Run(Protocol):
    record_name: str
    hold_reason: str | None


def held(run: _Run) -> bool:
    return bool((run.hold_reason or "").strip())


def usable(run: _Run) -> bool:
    """물성으로 쓸 수 있나 — 보류가 아니면."""
    return not held(run)


def message(run: _Run) -> str:
    return (
        f"'{run.record_name}' 은 물성 사용 보류 중입니다 — {run.hold_reason}. 자료 관리자가 "
        "보류를 "
        "풀어야 채택 · 카드에 쓸 수 있습니다."
    )


def require_usable(run: _Run, *, code: str) -> None:
    """보류 중이면 막는다 — 채택 · 카드 생성이 부른다."""
    if held(run):
        raise Conflict(code, message(run))
