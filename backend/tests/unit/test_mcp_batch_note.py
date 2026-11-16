"""MCP `run_batch_processing` — **부분 결과는 「바로 채택」 이어도 미뤘다고 말한다**
(2026-11-17, VOC 58).

서버가 처음 처리하는 시험의 부분 결과도 일괄 채택하지 않게 바뀌었다(ADR 0089). AI 가
「채택했다」 고 옮기지 않게 `note` 가 부분 결과 건수와 「채택은 미뤘습니다」 를 싣는다.
`server.py` 는 mcp SDK 를 불러 이 스위트가 못 연다 — 그 함수만 소스에서 꺼내 흉내 낸
`_send` 로 돌린다(`test_mcp_create_group.py`).
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

SERVER = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"

PARTIAL = {
    "test_run_id": "R1",
    "record_name": "시편-1",
    "status": "ok",
    "adopted": False,
    "failures": [{"plugin": "tensile.proof_stress", "label": "항복강도", "message": "E 없음"}],
    "warnings": [],
}
CLEAN = {**PARTIAL, "test_run_id": "R2", "record_name": "시편-2", "failures": []}


def _tool(items: list[dict[str, Any]]) -> Any:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    picked = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_batch_processing"
    ]
    assert len(picked) == 1, "server.py 에 run_batch_processing 이 없다"
    future = ast.parse("from __future__ import annotations").body
    module = ast.Module(body=[*future, *picked], type_ignores=[])

    class _Mcp:
        @staticmethod
        def tool() -> Any:
            return lambda fn: fn

    async def send(ctx: Any, method: str, path: str, body: Any = None) -> Any:
        assert (method, path) == ("POST", "/processing/batch")
        return {"items": items, "failed": 0, "succeeded": len(items)}

    space: dict[str, Any] = {"Any": Any, "mcp": _Mcp, "_send": send}
    exec(compile(module, str(SERVER), "exec", dont_inherit=True), space)
    return space["run_batch_processing"]


def _call(items: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    out: dict[str, Any] = asyncio.run(
        _tool(items)(None, test_run_ids=["R1", "R2"], recipe_key="rcp", **kwargs)
    )
    return out


def test_바로_채택이면_부분_결과를_미뤘다고_말한다() -> None:
    note = _call([PARTIAL, CLEAN], adopt=True, dry_run=False)["note"]
    assert "실패한 단계가 있는 부분 결과 1건 — 채택은 미뤘습니다" in note


def test_채택을_안_걸었으면_미뤘다고는_안_한다() -> None:
    note = _call([PARTIAL], adopt=False, dry_run=False)["note"]
    assert "부분 결과 1건" in note and "미뤘습니다" not in note


def test_부분_결과가_없으면_그_말이_없다() -> None:
    assert "부분 결과" not in _call([CLEAN], adopt=True, dry_run=False).get("note", "")
