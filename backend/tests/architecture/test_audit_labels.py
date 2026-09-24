"""감사에 남기는 행위는 **화면이 이름으로 부른다** — 백엔드가 남기는 코드 전부.

변경 이력 화면은 이름표(`frontend/src/modules/audit/api.ts` 의 `ACTION_LABELS`)에 없는
코드를 **그대로** 보인다 — 모르는 일이 일어났다는 것 자체가 알아야 할 일이라서다. 그런데
이름표에 없으면 「행위로 필터」 에서 고를 수도 없다. 실측(2026-09-24): 백엔드가 남기는
행위 36가지 중 18가지가 이름표에 없었다. 배포(ADR 0035)가 남긴 「열람 제한이 켜져 있던
부서」 를 찾으려는데 필터에 그 행위가 없었다 — 수백 줄을 눈으로 훑어야 했다.

행위를 남기는 길은 둘이다. 앱은 `audit.record(action=...)`, 마이그레이션은 SQL 로
`audit_entries` 에 직접 넣는다. 둘 다 본다.

**이름표에만 있고 아무도 안 남기는 코드는 막지 않는다** — 행위를 걷어도 옛 기록은 표에
남고, 그 줄은 여전히 이름으로 읽혀야 한다.
"""

from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
LABELS = BACKEND.parent / "frontend" / "src" / "modules" / "audit" / "api.ts"

#: 마이그레이션의 `INSERT INTO audit_entries (...) VALUES (:id, '<행위>', ...)`.
_SQL_ACTION = re.compile(r":id,\s*'([a-z_]+(?:\.[a-z_]+)+)'")


def _module_constants(tree: ast.Module) -> dict[str, str]:
    found: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value.value
    return found


def _parse(path: Path) -> ast.Module:
    # 문서 문자열의 역슬래시(`C:\MatNexus`)가 SyntaxWarning 을 낸다 — 읽기만 하므로 끈다.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8"))


def _emitted() -> tuple[dict[str, set[str]], list[str]]:
    """(행위 → 남기는 자리, 읽지 못한 자리)."""
    audit_py = BACKEND / "app" / "shared" / "audit.py"
    shared = _module_constants(_parse(audit_py))
    found: dict[str, set[str]] = {}
    unread: list[str] = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        tree = _parse(path)
        local = _module_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if path == audit_py:
                # **감사 모듈 안은 `record(...)` 를 바로 부른다**(남의 자료 고침 — 2026-09-25).
                # 전에는 이 파일을 통째로 건너뛰었는데, 그러면 여기서 남기는 행위가 이름표
                # 검사를 빠져나간다. 받은 것을 넘기는 자리(`action=action`)만 건너뛴다.
                if not (isinstance(node.func, ast.Name) and node.func.id == "record"):
                    continue
                if any(
                    k.arg == "action" and ast.unparse(k.value) == "action"
                    for k in node.keywords
                ):
                    continue
            elif not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in ("record", "record_by_client")
                and ast.unparse(node.func.value) == "audit"
            ):
                continue
            where = f"{path.relative_to(BACKEND).as_posix()}:{node.lineno}"
            for keyword in node.keywords:
                if keyword.arg != "action":
                    continue
                value = keyword.value
                code: str | None = None
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    code = value.value
                elif isinstance(value, ast.Attribute) and ast.unparse(value.value) == "audit":
                    code = shared.get(value.attr)
                elif isinstance(value, ast.Name):
                    code = local.get(value.id) or shared.get(value.id)
                if code:
                    found.setdefault(code, set()).add(where)
                else:
                    unread.append(f"{where} action={ast.unparse(value)}")
    for path in sorted((BACKEND / "migrations" / "versions").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "audit_entries" not in text:
            continue
        for match in _SQL_ACTION.finditer(text):
            found.setdefault(match.group(1), set()).add(f"migrations/{path.name}")
    return found, unread


def _labeled() -> set[str]:
    text = LABELS.read_text(encoding="utf-8")
    start = text.index("export const ACTION_LABELS")
    body = text[start : text.index("\n}", start)]
    return set(re.findall(r"^\s*'([a-z_]+(?:\.[a-z_]+)+)':", body, re.M))


def test_남기는_행위는_전부_이름표가_있다() -> None:
    emitted, _ = _emitted()
    missing = {
        code: sorted(where) for code, where in emitted.items() if code not in _labeled()
    }
    assert not missing, (
        "감사에 남기는데 화면 이름표가 없는 행위입니다 — "
        f"`frontend/src/modules/audit/api.ts` 의 ACTION_LABELS 에 적으세요: {missing}"
    )


def test_행위_코드는_읽을_수_있게_적는다() -> None:
    """변수로 넘기면 이 시험이 무엇이 남는지 모른다 — 글자나 `audit.` 상수로 적는다."""
    _, unread = _emitted()
    assert not unread, f"행위 코드를 읽을 수 없는 자리: {unread}"


def test_이_시험이_실제로_읽는다() -> None:
    """못 읽어서 통과하는 것을 막는다 — 알려진 행위들이 잡혀야 한다."""
    emitted, _ = _emitted()
    assert {"card.published", "trash.purged", "workspace.restriction_removed"} <= set(emitted)
    assert len(emitted) >= 30
