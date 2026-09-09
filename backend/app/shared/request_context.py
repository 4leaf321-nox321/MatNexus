"""요청 ID 와 **누가 부르는 프로그램인가** — 로그를 잇는 두 끈.

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

#: 어느 프로그램이 부르나 — `mcp` · `web`(기본). **사람이 한 것과 AI 가 한 것을
#: 가르는 유일한 표시다.**
#:
#: MCP 서버는 진작부터 `X-Client: mcp` 를 보내고 있었는데 백엔드가 안 읽었다.
#: 쓰기 도구가 둘뿐일 때는 티가 안 났지만, 처리 실행까지 열면 감사 로그에서
#: 「이 결과 누가 돌렸지」 를 못 답하게 된다.
#:
#: **인증이 아니다.** 클라이언트가 아무 값이나 보낼 수 있다 — 권한은 토큰이
#: 정하고, 이 값은 「어느 길로 들어왔나」 를 적어 두는 표식일 뿐이다.
_client: ContextVar[str] = ContextVar("client", default="")

HEADER = "X-Request-ID"
_HEADER_BYTES = HEADER.lower().encode()

CLIENT_HEADER = "X-Client"
_CLIENT_BYTES = CLIENT_HEADER.lower().encode()

#: 아는 이름만 받는다. 모르는 값은 버린다 — 감사 열이 아무 글자나 담는 자리가
#: 되면 그 열로는 아무것도 셀 수 없다.
KNOWN_CLIENTS = ("mcp", "pylon", "script")


def get_request_id() -> str:
    return _request_id.get()


def get_client() -> str:
    """`mcp` · `pylon` · `script`, 또는 빈 문자열(화면·모름)."""
    return _client.get()


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

        raw = dict(scope.get("headers") or {}).get(_CLIENT_BYTES)
        said = raw.decode(errors="replace").strip().lower()[:20] if raw else ""
        client_token = _client.set(said if said in KNOWN_CLIENTS else "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((_HEADER_BYTES, rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(token)
            _client.reset(client_token)
