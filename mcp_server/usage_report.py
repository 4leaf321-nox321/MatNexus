"""MCP 도구 호출을 **센다** — 백엔드 사용 현황(「관리 → 사용 현황」, 2026-10-02).

백엔드는 MCP 가 보낸 API 요청을 `X-Client: mcp` 로 가려 세지만, 그것으로는 **도구 수**를 못 센다.
도구 하나가 백엔드를 여러 번 부르고(`property_coverage`), 백엔드를 안 부르는 도구도 있다
(`get_guide`). 그래서 도구가 끝날 때마다 이 서버가 직접 알린다 — 도구 이름 · 성공 여부 · 걸린 시간.

**보고가 도구를 막지 않는다.** 보고가 실패해도(백엔드가 꺼졌거나 토큰이 없다) 도구의 답은 그대로
나간다. 셈 하나 놓치는 것이 대화를 끊는 것보다 낫다.

`server.py` 는 mcp SDK 를 불러 백엔드 시험이 못 연다 — 판단은 여기 두고
`backend/tests/unit/test_mcp_usage_report.py` 가 문다(`declared_points` 와 같은 자리).
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

#: `(ctx, 도구 이름, 성공했나, 걸린 ms)` 를 받아 백엔드에 알리는 함수.
Report = Callable[[Any, str, bool, int], Awaitable[None]]


def failed(result: Any) -> bool:
    """도구가 **오류로 끝났나** — 이 서버의 도구는 오류를 `{"error": …}` 로 돌려준다.

    미리보기 안쪽의 오류(`{"dry_run": true, "item": {"error": …}}`)는 도구가 실패한 것이 아니다 —
    물은 대상이 없었다는 답이다. 맨 위만 본다.
    """
    return isinstance(result, dict) and "error" in result


def counted(
    fn: Callable[..., Awaitable[Any]],
    report: Report,
    is_context: Callable[[Any], bool],
) -> Callable[..., Awaitable[Any]]:
    """도구 함수를 감싸 **끝날 때마다** 알린다. 서명은 그대로 둔다(`functools.wraps`) — SDK 가
    인자 모양과 `ctx` 자리를 원래 함수에서 읽는다."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        ok = False
        try:
            result = await fn(*args, **kwargs)
            ok = not failed(result)
            return result
        finally:
            ctx = next(
                (one for one in (*args, *kwargs.values()) if is_context(one)),
                None,
            )
            if ctx is not None:
                elapsed = int((time.monotonic() - started) * 1000)
                try:
                    await report(ctx, fn.__name__, ok, elapsed)
                except Exception:  # noqa: BLE001 — 보고는 도구를 막지 않는다
                    pass

    return wrapper


__all__ = ["Report", "counted", "failed"]
