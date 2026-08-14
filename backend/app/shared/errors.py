"""오류 규약 — 구조화 코드 + 반드시 로그를 남긴다.

65의 교훈: `except Exception` 322회가 불투명한 409로 치환돼 원인이 로그에 남지
않았다(비교표 C-1). 그래서 여기서는 오류를 만드는 경로가 곧 로그를 남기는
경로다. 핸들러를 거치지 않고 오류 응답을 만들 방법을 두지 않는다.

코드 형식: MNX-<MODULE>-<NNNN>  예) MNX-TESTS-0001
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.request_context import get_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    """도메인 오류. status는 HTTP 상태, code는 사람이 검색할 수 있는 식별자."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class NotFound(AppError):
    def __init__(self, code: str, message: str, **kw: Any) -> None:
        super().__init__(code, message, status=404, **kw)


class Conflict(AppError):
    def __init__(self, code: str, message: str, **kw: Any) -> None:
        super().__init__(code, message, status=409, **kw)


class Forbidden(AppError):
    def __init__(self, code: str, message: str, **kw: Any) -> None:
        super().__init__(code, message, status=403, **kw)


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
            "details": details or {},
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        # 4xx는 정상 흐름의 일부라 warning, 5xx는 error. 어느 쪽이든 남긴다.
        log = logger.warning if exc.status < 500 else logger.error
        log(
            "%s %s -> %s %s: %s",
            request.method,
            request.url.path,
            exc.status,
            exc.code,
            exc.message,
            extra={"details": exc.details},
        )
        return JSONResponse(
            status_code=exc.status, content=_body(exc.code, exc.message, exc.details)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            "%s %s -> 422 validation: %s", request.method, request.url.path, exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content=_body(
                "MNX-COMMON-0422", "요청 형식이 올바르지 않습니다.", {"errors": exc.errors()}
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 스택 트레이스를 반드시 남긴다. 사용자에게는 request_id만 주고,
        # 그 id로 로그에서 원본을 찾는다.
        logger.exception("%s %s -> 500 unhandled", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_body(
                "MNX-COMMON-0500",
                "서버 오류가 발생했습니다. 요청 ID를 관리자에게 알려주세요.",
            ),
        )
