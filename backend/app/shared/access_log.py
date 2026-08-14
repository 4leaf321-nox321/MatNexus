"""접근 로그 미들웨어.

**모든 API 요청을 남기지 않는다.** 알림 배지 폴링(30초마다)까지 적으면 테이블이
의미 없는 행으로 차서 정작 찾을 것을 못 찾는다. 상태를 바꾸는 요청과 로그인만
남긴다 — 사용자 지원에 필요한 것은 "무엇을 했는가"이지 "무엇을 봤는가"가 아니다.

기록은 요청 처리와 별개 세션에서 한다. 로그를 남기다 실패해도 사용자의 요청은
성공해야 한다.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.database import SessionLocal
from app.modules.audit.models import AccessLog
from app.shared.request_context import get_request_id

logger = logging.getLogger(__name__)

#: 남길 메서드. GET 은 기본적으로 남기지 않는다(조회는 양이 많고 가치가 낮다).
_RECORDED_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

#: 예외적으로 남길 GET 경로 — 로그인 직후 확인 같은 것.
_ALWAYS: tuple[str, ...] = ()

#: 남기지 않을 경로. 폴링과 헬스체크가 대부분이다.
_SKIP = ("/api/health", "/api/notifications/unread-count")


def _action(path: str) -> str:
    if path.endswith("/auth/login"):
        return "LOGIN"
    if path.endswith("/auth/logout"):
        return "LOGOUT"
    return "API"


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", ""))
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if not path.startswith("/api/") or path in _SKIP:
            return
        if method not in _RECORDED_METHODS and path not in _ALWAYS:
            return

        try:
            headers = dict(scope.get("headers") or {})
            client = scope.get("client")
            # 세션 공장을 app.state 에서 가져온다. SessionLocal 을 직접 부르면
            # 설정과 무관하게 늘 같은 DB 를 보게 되어, 테스트가 자기 DB 를
            # 쓰지 못한다(실측: 접근 로그만 개발 DB 에 쌓였다).
            factory = getattr(scope["app"].state, "session_factory", SessionLocal)
            db = factory()
            try:
                db.add(
                    AccessLog(
                        user_id=scope.get("mnx_user_id"),
                        action=_action(path),
                        path=path[:300],
                        method=method,
                        status_code=status_holder["status"],
                        request_id=get_request_id(),
                        client_ip=client[0] if client else None,
                        user_agent=(headers.get(b"user-agent") or b"").decode()[:300] or None,
                    )
                )
                db.commit()
            finally:
                db.close()
        except Exception:
            # 로그를 남기다 실패해도 사용자의 요청은 이미 끝났다. 삼키되 남긴다.
            logger.exception("접근 로그 기록 실패 (%s %s)", method, path)
