"""MCP 의 쓰기 도구는 **전부 감사 흔적을 남긴다** — AI 가 한 일을 셀 수 있어야 한다.

## 왜 이 시험이 있나

AI 는 사람의 토큰으로 부른다. 그래서 등록자·작성자 칸만으로는 「이거 사람이 한 거 맞나」 에
답할 수 없고, 답할 자리는 감사의 `client`(들어온 길)뿐이다(`shared/audit.py`).

그 자리가 두 번 샜다. 09-10 에는 값 수정만 남겼고(AI 가 문헌값 9건을 담았는데 흔적이
`updated_at` 뿐이었다), 09-18 에 카드·처리·레시피·형식을 더했다. **09-25 에 도구마다 경로를
맞대 보니 셋이 더 샜다** — 재료·시료·시편 등록, 문헌 카탈로그 쓰기, 측정 의뢰 작성. AI 가
문헌 값을 지어 넣어도 사람이 넣은 값과 구별할 길이 없었다. 「AI 는 아무것도 안 했다」 로
읽히는 조용한 구멍은 없는 것보다 나쁘다. 그래서 여기서 막는다.

## 무엇을 보나

MCP 서버의 쓰기는 `_send` 하나를 지난다. 그 호출(메서드 · 경로)을 모아 백엔드 라우트를 찾고,
그 라우트 함수 — 또는 그것이 부르는 함수 한 겹 — 가 `audit.record` 나 `audit.record_by_client`
를 부르는지 본다. 미리보기처럼 **쓰지 않는** 호출은 `READS` 에 사유와 함께 적는다.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from app.main import app

SERVER = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"

#: 경로가 변수인 호출 — 도구 함수 → 그 변수가 될 수 있는 경로.
DYNAMIC: dict[str, list[str]] = {
    # dry_run 일 때의 이름 미리보기(`?workspace_slug=` 가 붙을 수 있다).
    "create_material": ["/materials/preview-name"],
    # 묶음 플러그인마다 카드 만드는 자리가 다르다(`_GROUP_CARD_PATHS`).
    "create_card_from_group": [
        "/fitting/cards/rate-dependent",
        "/fitting/cards/viscoelastic",
        "/fitting/cards/from-group",
    ],
}

#: **쓰지 않는** POST — (메서드, 경로) → 사유. 여기 적는 것은 「저장하지 않는다」 는 주장이다.
READS: dict[tuple[str, str], str] = {
    ("POST", "/materials/preview-name"): "지어질 이름을 미리 본다 — 저장하지 않는다",
    ("POST", "/catalog/deck/match"): "부품표 줄을 문헌 재료에 짝지어 보기만 한다",
    ("POST", "/fitting/decks/bom"): "덱을 만들어 돌려줄 뿐 저장하지 않는다",
    ("POST", "/fitting/preview"): "식을 견주기만 한다 — 카드는 안 만든다",
    ("POST", "/formulas/preview"): "식을 계산해 보기만 한다",
    ("POST", "/processing/preview"): "처리 결과를 미리 본다 — 저장하지 않는다",
    ("POST", "/formats/check"): "형식이 파일을 읽는지 검사만 한다",
    ("POST", "/fitting/export-profiles/scan"): "덱을 읽어 형식을 알아보기만 한다",
    ("POST", "/fitting/cards/{}/export/check"): "내보낼 덱을 검사만 한다",
}

_PARAM = re.compile(r"\{[^}]*\}")


def _normal(path: str) -> str:
    """`/materials/{material_id}/samples?x=1` → `/materials/{}/samples`."""
    return _PARAM.sub("{}", path.split("?", 1)[0])


def _path_of(node: ast.expr, tool: str) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [
            "".join(
                str(part.value) if isinstance(part, ast.Constant) else "{}"
                for part in node.values
            )
        ]
    if isinstance(node, ast.Name) and tool in DYNAMIC:
        return DYNAMIC[tool]
    raise AssertionError(
        f"`{tool}` 의 `_send` 경로를 읽지 못했습니다({ast.unparse(node)}). 변수라면 "
        "`DYNAMIC` 에 그 도구가 부를 수 있는 경로를 적으세요."
    )


def _mcp_writes() -> set[tuple[str, str, str]]:
    """(메서드, 경로, 도구) — MCP 서버가 `_send` 로 보내는 것 전부."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    found: set[tuple[str, str, str]] = set()
    for tool in tree.body:
        if not isinstance(tool, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(tool):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_send"
            ):
                continue
            assert len(node.args) >= 3, f"`{tool.name}` 의 `_send` 는 위치 인자로 부른다"
            method = node.args[1]
            assert isinstance(method, ast.Constant), f"`{tool.name}` 의 메서드가 상수가 아니다"
            for path in _path_of(node.args[2], tool.name):
                found.add((str(method.value), _normal(path), tool.name))
    return found


def _routes() -> dict[tuple[str, str], Callable[..., Any]]:
    """(메서드, 경로) → 라우트 함수. **먼저 선 것이 이긴다** — 요청이 고르는 차례와 같다
    (`/notices/unread-count` 가 `/notices/{id}` 보다 앞에 서야 하는 것처럼).

    FastAPI 0.141 은 포함한 라우터를 감싸 둔다(`original_router` · `include_context`) — 앱의
    `routes` 에는 감싼 것만 보여서 펼쳐 읽는다.
    """
    table: dict[tuple[str, str], Callable[..., Any]] = {}

    def walk(routes: list[Any], prefix: str) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                path = _normal(prefix + route.path).removeprefix("/api")
                for method in route.methods or ():
                    table.setdefault((method, path), route.endpoint)
            elif hasattr(route, "original_router"):
                walk(route.original_router.routes, prefix + route.include_context.prefix)

    walk(list(app.routes), "")
    assert table, (
        "라우트를 하나도 못 읽었습니다 — FastAPI 가 라우터를 싸는 모양이 바뀌었나 보세요"
    )
    return table


def _records(func: Callable[..., Any]) -> bool:
    """몸통이 `audit.record(...)` 나 `audit.record_by_client(...)` 를 부르는가."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("record", "record_by_client")
        and ast.unparse(node.func.value) == "audit"
        for node in ast.walk(tree)
    )


def _callees(func: Callable[..., Any]) -> list[Callable[..., Any]]:
    """몸통이 부르는 **앱 안의** 함수 — `helper(...)` · `services.helper(...)`."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    scope = getattr(func, "__globals__", {})
    found: list[Callable[..., Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target: Any = None
        if isinstance(node.func, ast.Name):
            target = scope.get(node.func.id)
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = scope.get(node.func.value.id)
            if isinstance(owner, types.ModuleType):
                target = getattr(owner, node.func.attr, None)
        if isinstance(target, types.FunctionType) and target.__module__.startswith("app."):
            found.append(target)
    return found


def _audited(func: Callable[..., Any]) -> bool:
    """라우트 자신이나 **한 겹 아래**가 감사를 남기는가. 더 깊이 따라가지 않는다 — 깊이
    들어갈수록 「어딘가에서 남긴다」 가 참이 되기 쉬워, 새는 자리를 가린다."""
    return _records(func) or any(_records(one) for one in _callees(func))


def test_MCP_쓰기는_전부_감사를_남긴다() -> None:
    routes = _routes()
    missing_route: list[str] = []
    silent: list[str] = []
    for method, path, tool in sorted(_mcp_writes()):
        if (method, path) in READS:
            continue
        endpoint = routes.get((method, path))
        if endpoint is None:
            missing_route.append(f"{tool}: {method} {path}")
            continue
        if not _audited(endpoint):
            silent.append(
                f"{tool}: {method} {path} ({endpoint.__module__}.{endpoint.__name__})"
            )
    assert not missing_route, f"MCP 가 부르는데 백엔드에 없는 경로입니다: {missing_route}"
    assert not silent, (
        "MCP 가 쓰는데 감사에 흔적을 안 남기는 길입니다 — AI 가 한 일을 사람이 한 일과 "
        "구별할 수 없습니다. `audit.record_by_client` 를 부르세요(되돌릴 수 없는 일이면 "
        "`audit.record`). 쓰지 않는 호출이면 `READS` 에 사유와 함께 적으세요: "
        f"{silent}"
    )


def test_읽기_목록은_실제로_부르는_것만() -> None:
    """도구가 없어졌는데 `READS`·`DYNAMIC` 에 남으면, 같은 경로가 쓰기로 돌아왔을 때 이 목록이
    그것을 조용히 통과시킨다."""
    called = {(method, path) for method, path, _ in _mcp_writes()}
    stale = sorted(key for key in READS if key not in called)
    assert not stale, f"MCP 가 더는 안 부르는 경로입니다 — `READS` 에서 지우세요: {stale}"
    tools = {tool for _, _, tool in _mcp_writes()}
    gone = sorted(tool for tool in DYNAMIC if tool not in tools)
    assert not gone, f"없어진 도구입니다 — `DYNAMIC` 에서 지우세요: {gone}"


def test_깊이_한_겹만_따라간다() -> None:
    """두 겹 아래에서 남기는 쓰기는 **새는 것으로** 본다 — 가려내는 힘이 거기서 나온다."""

    def deep() -> None:
        _middle()

    assert not _audited(deep)


def _middle() -> None:
    _bottom()


def _bottom() -> None:  # pragma: no cover - 부르지 않는다. 소스만 읽는다.
    from app.shared import audit

    audit.record(
        None,  # type: ignore[arg-type]
        action="x",
        actor=None,
        target_table="x",
        target_id=None,
        target_label="x",
    )
