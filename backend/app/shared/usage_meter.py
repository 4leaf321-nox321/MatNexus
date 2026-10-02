"""사용 계량기 — 로그인한 API 요청을 **센다**(2026-10-02, `modules/usage`).

접근 로그 미들웨어와 나란히 선다. 그쪽은 쓰기 요청을 **행으로** 남기고(사람 지원), 여기는 모든
요청을 날 · 사람 · 길 · 라우트마다 **수로** 더한다(사용 현황). 조회를 행으로 남기면 표가 요청
수만큼 자라지만, 수로 더하면 하루에 「사람 · 라우트」 줄이 전부다.

## 무엇을 세나

- **로그인한 요청만.** 누가 썼는지 모르는 요청(로그인 전 · 헬스체크)은 「사용」 이 아니다.
- **라우트 틀로 센다** — `/materials/{material_id}`. 맞는 라우트가 없는 주소(화면 새로고침의
  SPA 폴백 · 없는 API)는 안 센다.
- **폴링은 안 센다** — 알림 배지가 30초마다 묻는 것까지 세면 「얼마나 쓰나」 가 「얼마나 켜
  두나」 가 된다. MCP 서버의 호출 보고(`/usage/mcp-calls`)도 안 센다 — 도구 수는 그쪽 표가
  따로 센다.
- 상세 조회 다섯(재료 · 문헌 재료 · 시험 · 카드 · 가이드 문서)은 **무엇을 봤는지**도 센다.

기록은 요청 처리와 다른 세션에서 하고, 실패해도 삼킨다 — 계량이 요청을 막으면 안 된다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.database import SessionLocal
from app.modules.usage.models import McpToolDaily, UsageDaily, UsageViewDaily
from app.shared.request_context import get_client

logger = logging.getLogger(__name__)

#: 안 세는 라우트 — 폴링과 MCP 의 호출 보고.
SKIP_ROUTES = frozenset(
    {
        "/notifications/unread-count",
        "/notices/unread-count",
        "/usage/mcp-calls",
    }
)

#: SPA 폴백 — 맞는 API 가 없을 때 걸리는 틀. 세지 않는다.
FALLBACK_ROUTES = frozenset({"/{full_path:path}"})

#: 상세 조회로 세는 라우트 → (종류, 경로 변수).
VIEW_ROUTES: dict[str, tuple[str, str]] = {
    "/materials/{material_id}": ("material", "material_id"),
    "/catalog/materials/{material_id}": ("catalog_material", "material_id"),
    "/test-runs/{run_id}": ("test_run", "run_id"),
    "/fitting/cards/{card_id}": ("card", "card_id"),
    "/guide/documents/{key}": ("guide", "key"),
}

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def today() -> date:
    """이 서버의 **현지** 날짜. 사람은 「오늘 몇 명」 을 현지 날짜로 묻는다."""
    return datetime.now().astimezone().date()


def client_name(raw: str | None) -> str:
    """`X-Client` 표식 → 집계 열. 표식이 없으면 화면(`web`)이다."""
    return raw or "web"


def record_request(
    db: Session,
    *,
    user_id: uuid.UUID,
    client: str,
    method: str,
    route: str,
    failed: bool,
    day: date | None = None,
) -> None:
    statement = insert(UsageDaily).values(
        day=day or today(),
        user_id=user_id,
        client=client,
        method=method,
        route=route[:200],
        requests=1,
        errors=1 if failed else 0,
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["day", "user_id", "client", "method", "route"],
            set_={
                "requests": UsageDaily.requests + 1,
                "errors": UsageDaily.errors + (1 if failed else 0),
            },
        )
    )


def record_view(
    db: Session,
    *,
    kind: str,
    entity_id: str,
    user_id: uuid.UUID,
    client: str,
    day: date | None = None,
) -> None:
    statement = insert(UsageViewDaily).values(
        day=day or today(),
        kind=kind,
        entity_id=entity_id[:100],
        user_id=user_id,
        client=client,
        views=1,
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["day", "kind", "entity_id", "user_id", "client"],
            set_={"views": UsageViewDaily.views + 1},
        )
    )


def record_tool(
    db: Session,
    *,
    user_id: uuid.UUID,
    tool: str,
    ok: bool,
    elapsed_ms: int,
    day: date | None = None,
) -> None:
    statement = insert(McpToolDaily).values(
        day=day or today(),
        user_id=user_id,
        tool=tool[:80],
        calls=1,
        failures=0 if ok else 1,
        elapsed_ms=max(0, elapsed_ms),
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["day", "user_id", "tool"],
            set_={
                "calls": McpToolDaily.calls + 1,
                "failures": McpToolDaily.failures + (0 if ok else 1),
                "elapsed_ms": McpToolDaily.elapsed_ms + max(0, elapsed_ms),
            },
        )
    )


def route_of(scope: Scope) -> str | None:
    """맞은 라우트의 틀. 없으면(라우트가 안 맞음) `None`."""
    route: Any = scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else None


class UsageMeterMiddleware:
    """로그인한 API 요청을 센다. `RequestIdMiddleware` 안쪽에 둔다 — `X-Client` 를 거기서
    읽는다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
            await send(message)

        await self.app(scope, receive, send_wrapper)

        path = str(scope.get("path", ""))
        user_id = scope.get("mnx_user_id")
        route = route_of(scope)
        if not path.startswith("/api/") or user_id is None or route is None:
            return
        if route in SKIP_ROUTES or route in FALLBACK_ROUTES or route == "/api/health":
            return

        method = str(scope.get("method", ""))
        status = status_holder["status"]
        client = client_name(get_client())
        try:
            factory = getattr(scope["app"].state, "session_factory", SessionLocal)
            db = factory()
            try:
                record_request(
                    db,
                    user_id=user_id,
                    client=client,
                    method=method,
                    route=route,
                    failed=status >= 400,
                )
                viewed = VIEW_ROUTES.get(route)
                if viewed and method == "GET" and status == 200:
                    kind, param = viewed
                    entity = (scope.get("path_params") or {}).get(param)
                    if entity:
                        record_view(
                            db,
                            kind=kind,
                            entity_id=str(entity),
                            user_id=user_id,
                            client=client,
                        )
                db.commit()
            finally:
                db.close()
        except Exception:
            # 계량이 요청을 막으면 안 된다. 요청은 이미 끝났다 — 삼키되 남긴다.
            logger.exception("사용 집계 실패 (%s %s)", method, path)


__all__ = [
    "SKIP_ROUTES",
    "VIEW_ROUTES",
    "UsageMeterMiddleware",
    "client_name",
    "record_request",
    "record_tool",
    "record_view",
    "today",
]
