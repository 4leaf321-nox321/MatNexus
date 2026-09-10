"""MCP 도구가 **선언한 모양대로 답하는가** — 정적으로 대조한다.

## 왜 이 시험이 생겼나 (실측 2026-09-10)

진짜 MCP 클라이언트로 41개를 처음 왕복해 보고서야 셋이 죽어 있는 것이 드러났다 —
`get_parameter_sets` · `get_catalog_parameter_sets` · `list_recipes`. 셋 다 **목록
엔드포인트를 그대로 돌려주는데 반환 표기는 `dict`** 였다.

mcp 2.x 는 도구가 돌려준 값을 함수의 반환 표기로 검증한다(1.x 는 안 했다). 배열이
오면 pydantic 이 막고, 클라이언트에는 `Error executing tool …` 한 줄만 간다 —
무엇이 왜 틀렸는지가 사라진다. 그런데 **같은 엔드포인트를 curl 로 부르면 멀쩡하다.**
화면에서도 안 드러난다. 오직 MCP 로 불러야만 보인다.

그래서 여기서 막는다. `openapi.json` 이 「이 경로는 배열을 준다」 를 알고 있고,
CI 가 그 파일을 최신으로 강제하므로(스키마를 바꾸면 다시 뽑는다) 대조가 성립한다.

## 무엇을 검사하나

    반환 표기가 dict 인데 배열 경로를 그대로 돌려주는 도구가 없다
    도구에는 설명이 있다 (AI 가 고르는 근거가 설명뿐이다)
    지도에 적은 들머리·길잡이가 **실재하는 이름만** 쓴다

경로를 **그대로 돌려주는** 것만 본다. 안에서 받아 쓰고 자기 모양으로 감싸는 것은
문제가 아니다 — `_listed(...)` 로 감싼 것도 여기서 통과한다.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from app.shared import relations

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "mcp_server" / "server.py"
OPENAPI = ROOT / "backend" / "openapi.json"


def _placeholders(path: str) -> str:
    """`/materials/{material_id}/x` 와 `/materials/{x}/x` 를 같은 것으로 본다."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def _array_paths() -> set[tuple[str, str]]:
    """배열을 돌려주는 (메서드, 경로) — `/api` 접두는 뗀다(MCP 는 그 뒤부터 쓴다)."""
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    found: set[tuple[str, str]] = set()
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            for code in ("200", "201"):
                answer = (operation.get("responses") or {}).get(code)
                if not answer:
                    continue
                schema = ((answer.get("content") or {}).get("application/json") or {}).get(
                    "schema"
                ) or {}
                if schema.get("type") == "array":
                    trimmed = path[4:] if path.startswith("/api") else path
                    found.add((method.upper(), _placeholders(trimmed)))
    return found


def _literal_path(node: ast.AST) -> str | None:
    """`"/a/b"` 와 `f"/a/{x}/b"` 에서 경로를 뽑는다. 그 밖의 표현식은 안 본다."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                out.append(piece.value)
            else:
                out.append("{}")
        return "".join(out)
    return None


def _tools() -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                out.append(node)
    return out


def _returns_dict(node: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    got = node.returns
    if isinstance(got, ast.Subscript) and isinstance(got.value, ast.Name):
        return got.value.id == "dict"
    return isinstance(got, ast.Name) and got.id == "dict"


def _passthrough_calls(node: ast.AST) -> list[tuple[str, str]]:
    """`return await _get(...)` 처럼 **그대로 돌려주는** 호출의 (메서드, 경로)."""
    found: list[tuple[str, str]] = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Return) or inner.value is None:
            continue
        value = inner.value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            continue
        if value.func.id not in ("_get", "_get_text", "_send"):
            continue
        args = value.args[1:]  # 첫 인자는 ctx
        if value.func.id == "_send":
            method = _literal_path(args[0]) if args else None
            path = _literal_path(args[1]) if len(args) > 1 else None
        else:
            method, path = "GET", _literal_path(args[0]) if args else None
        if method and path:
            found.append((method, _placeholders(path)))
    return found


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server 가 없는 배포본")
class TestMcp도구:
    def test_배열을_주는_경로를_그대로_돌려주지_않는다(self) -> None:
        """**이것이 이 파일이 있는 이유다.**

        `-> dict[str, Any]` 로 적고 배열을 그대로 흘리면 그 도구는 통째로 죽는데,
        HTTP 로는 멀쩡해서 MCP 로 불러 보기 전까지 안 보인다.
        """
        arrays = _array_paths()
        assert arrays, "openapi.json 에서 배열 응답을 하나도 못 찾았다 — 대조가 무의미하다"

        broken: list[str] = []
        for tool in _tools():
            if not _returns_dict(tool):
                continue
            for method, path in _passthrough_calls(tool):
                if (method, path) in arrays:
                    broken.append(f"{tool.name} → {method} {path}")

        assert not broken, (
            "이 도구들은 배열을 그대로 돌려주는데 반환 표기가 dict 다 — "
            "MCP 로 부르면 'Error executing tool' 로 죽는다. `_listed(...)` 로 감싸라:\n  "
            + "\n  ".join(broken)
        )

    def test_모든_도구에_설명이_있다(self) -> None:
        """AI 가 도구를 고르는 근거는 설명뿐이다 — 없으면 안 불리거나 잘못 불린다."""
        empty = [tool.name for tool in _tools() if not ast.get_docstring(tool)]
        assert not empty, f"설명 없는 도구: {empty}"


def _map_hints() -> str:
    """`get_ontology` 에 실어 보내는 들머리·길잡이의 원문."""
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    out = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            names = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            for name in names:
                if isinstance(name, ast.Name) and name.id in (
                    "_ENTRY",
                    "_RECIPES",
                    "_ANY_ENTRY",
                ):
                    got = ast.get_source_segment(source, node)
                    if got:
                        out.append(got)
    return "\n".join(out)


@pytest.mark.skipif(not SERVER.exists(), reason="mcp_server 가 없는 배포본")
class Test지도의_길잡이:
    """**지도에 적어 둔 길이 실재하는가.**

    `get_ontology` 는 종류마다 「이 손잡이를 어느 도구가 주나」(`entry`)와 물음별
    도구 차례(`recipes`)를 얹어 보낸다. 그 글은 사람이 손으로 적은 것이라 **이름이
    바뀌면 조용히 썩는다** — AI 는 그 말을 믿고 부르고, 422 나 빈손을 받고, 그때
    지도가 틀렸다는 것은 모른 채 자기가 잘못 골랐다고 여기고 헤맨다.

    실측(2026-09-10): 「점탄성이 있나」 한 물음에 도구를 37번 부른 세션이 있었다
    (길잡이를 넣고 다시 물으니 16번). 길잡이를 넣는 이유가 그것이고, **그 길잡이가
    틀리면 헤맴이 그때보다 길어진다.**
    """

    def test_적어_둔_종류가_온톨로지에_있다(self) -> None:
        source = _map_hints()
        assert source, "_ENTRY·_RECIPES 를 못 찾았다 — 이름이 바뀌었나"
        named = set(re.findall(r'kind="([a-z_]+)"', source))
        keys = set(re.findall(r'^\s{4}"([a-z_]+)":', source, re.MULTILINE))
        unknown = sorted((named | keys) - set(relations.KINDS) - {"…"})
        assert not unknown, f"지도에 없는 종류를 길잡이가 가리킨다: {unknown}"

    def test_적어_둔_관계가_온톨로지에_있다(self) -> None:
        source = _map_hints()
        named = set(re.findall(r'relation="([a-z_]+)"', source))
        assert named, "길잡이에 관계 이름이 하나도 없다 — 정규식이 늙었나"
        unknown = sorted(named - set(relations.RELATIONS))
        assert not unknown, f"지도에 없는 관계를 길잡이가 가리킨다: {unknown}"

    def test_적어_둔_도구가_실재한다(self) -> None:
        """**없는 도구를 부르라고 적어 두면 헤맴이 늘어난다.**"""
        source = _map_hints()
        known = {tool.name for tool in _tools()}
        called = set(re.findall(r"\b([a-z][a-z_]{3,})\(", source))
        unknown = sorted(called - known)
        assert not unknown, f"없는 도구를 길잡이가 가리킨다: {unknown}"
