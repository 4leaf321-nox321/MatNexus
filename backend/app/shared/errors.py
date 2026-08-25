"""오류 규약 — 구조화 코드 + 반드시 로그를 남긴다.

65의 교훈: `except Exception` 322회가 불투명한 409로 치환돼 원인이 로그에 남지
않았다(비교표 C-1). 그래서 여기서는 오류를 만드는 경로가 곧 로그를 남기는
경로다. 핸들러를 거치지 않고 오류 응답을 만들 방법을 두지 않는다.

코드 형식: MNX-<MODULE>-<NNNN>  예) MNX-TESTS-0001
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.request_context import get_request_id

logger = logging.getLogger(__name__)


#: 스키마 검증 실패 종류 → 사람이 읽는 말.
#: pydantic 의 영어 메시지를 그대로 내보내면 화면에서 아무도 안 읽는다.
_VALIDATION_MESSAGES = {
    "missing": "값이 빠졌습니다",
    "string_too_short": "값이 필요합니다",
    "string_too_long": "너무 깁니다",
    "string_pattern_mismatch": "쓸 수 없는 문자가 있습니다",
    "int_parsing": "정수여야 합니다",
    "float_parsing": "숫자여야 합니다",
    "bool_parsing": "예/아니오 값이어야 합니다",
    "value_error": "값이 올바르지 않습니다",
    "greater_than_equal": "너무 작습니다",
    "too_long": "너무 많습니다",
    "too_short": "개수가 모자랍니다",
    "less_than_equal": "너무 큽니다",
}

#: 한 번에 보여 줄 항목 수. 다 늘어놓으면 첫 줄부터 안 읽는다.
_MAX_VALIDATION_ITEMS = 3


def describe_validation(errors: Sequence[Any]) -> str:
    """**어느 칸이 왜 틀렸는지 말한다.**

    "요청 형식이 올바르지 않습니다" 만 내보내던 때 실제로 막혔다: 시험 종류
    키에 `DMA` 를 넣어 대소문자 규칙에 걸렸는데, 화면은 그 사실을 말해 주지
    않아 사용자가 무엇을 고쳐야 할지 알 수 없었다. 자세한 내용은 `details` 에도
    있지만 **화면이 보여 주는 것은 `message` 하나**다.
    """
    if not errors:
        return "요청 형식이 올바르지 않습니다."

    parts: list[str] = []
    for error in errors[:_MAX_VALIDATION_ITEMS]:
        location = [
            str(item) for item in error.get("loc", ()) if item not in ("body", "query")
        ]
        where = ""
        for index, item in enumerate(location):
            where += f"[{item}]" if item.isdigit() else (f".{item}" if index else item)

        kind = str(error.get("type"))
        message = str(error.get("msg", ""))
        # 직접 쓴 검증기가 붙인 말이 있으면 **그것이 낫다.** pydantic 은 그 말
        # 앞에 `Value error, ` 를 붙여 준다 — 우리가 적은 한국어가 그 뒤에 있다.
        reason = (
            message.removeprefix("Value error, ")
            if kind == "value_error" and message.startswith("Value error, ")
            else _VALIDATION_MESSAGES.get(kind, message)
        )
        context = error.get("ctx") or {}
        pattern = context.get("pattern")
        if pattern:
            reason = f"{reason} (허용: {pattern})"
        # **한도를 말해 주지 않으면 고칠 수 없다.** 「너무 많습니다」만 보고
        # 몇 개까지인지 알아내려면 코드를 읽어야 한다.
        limit = context.get("max_length") or context.get("actual_length")
        if limit is not None and kind in ("too_long", "too_short"):
            reason = f"{reason} (최대 {limit}개)"
        parts.append(f"{where or '요청'} — {reason}")

    more = len(errors) - len(parts)
    summary = " / ".join(parts)
    return f"{summary} 외 {more}건" if more > 0 else summary


def _plain(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """검증 오류를 JSON 으로 낼 수 있는 형태로 바꾼다.

    **직접 쓴 검증기가 500 을 냈다.** pydantic 은 `ValueError` 를 그대로
    `ctx["error"]` 에 담아 주는데, 그것을 응답 본문에 실으려다 직렬화에서
    터진다 — 422 를 내려던 자리에서 "서버 오류" 가 나가고, 사람은 자기가 뭘
    잘못 적었는지 알 수 없다. 관측하고 고쳤다(v1.87.0).
    """
    out: list[dict[str, Any]] = []
    for error in errors:
        item = dict(error)
        context = item.get("ctx")
        if isinstance(context, dict):
            item["ctx"] = {key: str(value) for key, value in context.items()}
        # `input` 에는 무엇이든 올 수 있다 — 파일 객체까지.
        if "input" in item:
            try:
                json.dumps(item["input"])
            except (TypeError, ValueError):
                item["input"] = str(item["input"])
        out.append(item)
    return out


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
        errors = _plain(exc.errors())
        logger.warning("%s %s -> 422 validation: %s", request.method, request.url.path, errors)
        return JSONResponse(
            status_code=422,
            content=_body("MNX-COMMON-0422", describe_validation(errors), {"errors": errors}),
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
