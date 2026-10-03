"""MCP 스킬이 **두 연결 모두를** 덮는가 — 직접 연결과 HWAX 포털 게이트웨이(2026-10-03).

MatNexus MCP 는 두 길로 붙는다 — MatNexus 에 직접(`mcp__matnexus__…`) 또는 HWAX 포털
게이트웨이(`mcp__hwax__…`, ADR 0056). 게이트웨이는 도구를 원래 이름으로 내놓되 다른 앱과
이름이 겹치면 `matnexus_` 를 붙인다(겹침은 다른 앱의 가동 여부로 바뀐다 — HWAXMcpGateway
`_aggregate`). 그래서 스킬의 자동 허용 목록에 도구마다 두 형태를 다 적는다. 도구를 추가하고
목록을 안 고치면 게이트웨이로 붙은 사람만 그 도구에서 매번 허용 확인을 받는다 — 조용히 생기는
불편이라 여기서 잡는다(Report Archive `tests/test_mcp_connection.py` 와 같은 판단).

안내(`guide/GUIDE.md`)는 서버가 두 길 모두에 내준다 — 한쪽 이름을 박으면 다른 쪽 모델이 없는
이름을 부른다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "mcp_server" / "server.py"
SKILL = ROOT / "mcp_server" / "skill" / "matnexus" / "SKILL.md"
GUIDE = ROOT / "mcp_server" / "guide" / "GUIDE.md"

pytestmark = pytest.mark.skipif(not SERVER.exists(), reason="mcp_server 가 없는 배포본")


def _tool_names() -> set[str]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                found.add(node.name)
    return found


def _allowed_tools() -> set[str]:
    """머리말의 allowed-tools — 여러 줄로 접힌 쉼표 목록(YAML 평문 스칼라)."""
    front = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
    parts: list[str] = []
    grab = False
    for line in front.splitlines():
        if line.startswith("allowed-tools:"):
            grab = True
            parts.append(line.split(":", 1)[1])
        elif grab and line.startswith((" ", "\t")):
            parts.append(line)
        elif grab:
            break
    return {one.strip() for one in " ".join(parts).split(",") if one.strip()}


def test_스킬이_두_연결의_도구_이름을_다_허용한다() -> None:
    tools = _tool_names()
    assert len(tools) > 50, "도구 추출이 깨졌다 — 0개면 아래 검사가 헛돈다"
    allowed = _allowed_tools()
    assert "mcp__matnexus__*" in allowed
    missing = sorted(
        name
        for name in tools
        if f"mcp__hwax__{name}" not in allowed or f"mcp__hwax__matnexus_{name}" not in allowed
    )
    assert not missing, f"SKILL.md allowed-tools 에 게이트웨이 이름이 빠졌다: {missing}"


def test_스킬에_없는_도구가_남지_않았다() -> None:
    tools = _tool_names()
    stale = sorted(
        one
        for one in _allowed_tools() - {"mcp__matnexus__*"}
        if one.removeprefix("mcp__hwax__").removeprefix("matnexus_") not in tools
    )
    assert not stale, f"없는 도구가 allowed-tools 에 남았다: {stale}"


def test_안내는_한쪽_연결_이름을_박지_않는다() -> None:
    """안내는 두 길 모두에 나간다 — 직접 연결 이름을 박으면 게이트웨이 쪽 모델이 없는 이름을
    부른다."""
    assert not re.search(r"mcp__(matnexus|hwax)__[A-Za-z_]", GUIDE.read_text(encoding="utf-8"))
