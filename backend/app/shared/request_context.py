"""요청 ID — 사용자 신고와 로그를 잇는 유일한 끈.

콘솔 실행(D9)이라 원격 디버깅이 없다. "그 화면에서 안 돼요" 를 재현하려면
사용자가 본 오류 응답과 서버 로그가 같은 id로 묶여 있어야 한다.

**순수 ASGI 미들웨어로 구현한다.** Starlette의 BaseHTTPMiddleware는 downstream을
별도 태스크로 실행해서, dispatch에서 설정한 ContextVar가 엔드포인트와 예외
핸들러에 전파되지 않는다(실측: 로그와 오류 본문의 request_id가 모두 '-' 로
찍혔다). 순수 ASGI는 같은 컨텍스트에서 downstream을 호출하므로 전파된다 —
sync 엔드포인트도 anyio가 contextvars를 복사해 스레드풀로 넘긴다.

접근 로그는 여기서 남기지 않는다. uvicorn의 접근 로그가 우리 핸들러를 타면서
이 id를 이미 달고 나오고 클라이언트 주소까지 함께 남기 때문이다
(app/logging_setup.py 참조).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

HEADER = "X-Request-ID"
_HEADER_BYTES = HEADER.lower().encode()


def get_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 역방향 프록시나 클라이언트가 id를 들고 오면 그대로 이어 쓴다.
        incoming = dict(scope.get("headers") or {}).get(_HEADER_BYTES)
        rid = incoming.decode() if incoming else uuid.uuid4().hex[:12]
        token = _request_id.set(rid)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((_HEADER_BYTES, rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(token)
