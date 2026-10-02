"""MCP 도구 호출 계량 — **끝날 때마다 알리고, 보고가 도구를 막지 않는다**(2026-10-02).

「관리 → 사용 현황」 의 MCP 숫자는 이 보고에서 온다. 판단은 `mcp_server/usage_report.py` 에
있다 — `server.py` 는 mcp SDK 를 불러 이 스위트가 못 연다(`declared_points` 와 같은 자리).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server"))

import usage_report  # noqa: E402


class Ctx:
    """SDK 의 Context 대신 — 계량기는 「이것이 ctx 인가」 만 묻는다."""


def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    return asyncio.run(fn(*args, **kwargs))


def _counted(fn: Any) -> tuple[Any, list[tuple[str, bool]]]:
    seen: list[tuple[str, bool]] = []

    async def report(_ctx: Any, tool: str, ok: bool, _ms: int) -> None:
        seen.append((tool, ok))

    return usage_report.counted(fn, report, lambda one: isinstance(one, Ctx)), seen


def test_성공과_오류를_가려_도구_이름으로_알린다() -> None:
    async def get_material(ctx: Ctx, material_id: str) -> dict[str, Any]:
        return {"error": "없는 재료"} if material_id == "x" else {"id": material_id}

    wrapped, seen = _counted(get_material)

    assert _run(wrapped, Ctx(), material_id="m1") == {"id": "m1"}
    _run(wrapped, ctx=Ctx(), material_id="x")

    assert seen == [("get_material", True), ("get_material", False)]


def test_미리보기_안쪽의_오류는_도구_실패가_아니다() -> None:
    assert usage_report.failed({"error": "x"})
    assert not usage_report.failed({"dry_run": True, "item": {"error": "없는 항목"}})
    assert not usage_report.failed("안내 문서 본문")


def test_예외로_끝나도_실패로_알리고_예외는_그대로_올라간다() -> None:
    async def broken(ctx: Ctx) -> None:
        raise RuntimeError("터짐")

    wrapped, seen = _counted(broken)

    with pytest.raises(RuntimeError):
        _run(wrapped, Ctx())
    assert seen == [("broken", False)]


def test_보고가_실패해도_도구의_답은_나간다() -> None:
    async def tool(ctx: Ctx) -> str:
        return "답"

    async def down(*_args: Any) -> None:
        raise ConnectionError("백엔드가 꺼졌다")

    wrapped = usage_report.counted(tool, down, lambda one: isinstance(one, Ctx))

    assert _run(wrapped, Ctx()) == "답"


def test_서명은_그대로다_SDK_가_인자와_ctx_자리를_원래_함수에서_읽는다() -> None:
    async def resolve_property(ctx: Ctx, name: str) -> dict[str, Any]:
        """이름 → 키."""
        return {}

    wrapped, _ = _counted(resolve_property)

    assert wrapped.__name__ == "resolve_property"
    assert wrapped.__doc__ == "이름 → 키."
    assert wrapped.__wrapped__ is resolve_property
