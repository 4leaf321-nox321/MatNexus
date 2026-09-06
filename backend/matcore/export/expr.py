"""덱 정의의 **식** — 값·열을 계산해서 적는다(2026-09-05).

정의가 값을 그대로 꽂는 것만 됐다. 솔버 덱에는 그것으로 안 되는 자리가 있다:

    열을 1000 으로 나눠 적는다        `true_stress / 1000`
    전단탄성률 G = E / (2(1+ν))      `E / (2 * (1 + nu))  ← E·nu 는 elastic.youngs_modulus 등`
    체적탄성률 K = E / (3(1-2ν))     `E / (3 * (1 - 2 * nu))`

**`eval` 은 쓰지 않는다.** 정의는 데이터라 부서 관리자가 적고, 그 글자가 서버에서
코드로 돈다면 그것은 곧 원격 실행이다. 파이썬 문법 트리를 읽어 **사칙연산·거듭제곱·
괄호·몇 개의 함수**만 허용한다 — 그 밖의 것은 이름을 대며 거절한다.

`^` 는 거듭제곱으로 읽는다. 사람은 `x^2` 라고 쓰고, 파이썬은 그것을 XOR 로 읽는다.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from typing import Any

#: 허용하는 이항 연산.
_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

#: 허용하는 함수. **여기 없는 이름은 거절한다.**
FUNCTIONS: dict[str, Callable[..., float]] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "min": min,
    "max": max,
}


class BadExpression(ValueError):
    """식이 문법에 안 맞거나 허용 밖의 것을 쓴다. 저장 전에 잡는다."""


class MissingName(KeyError):
    """식이 부르는 값·열이 덱에 없다. 렌더링 때 난다 — `when` 으로 걸러야 하는 줄."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _source(text: str) -> str:
    return text.replace("^", "**").strip()


def parse(text: str) -> ast.Expression:
    """문법과 허용 범위를 본다. 값은 안 본다 — 저장할 때 부른다."""
    source = _source(text)
    if not source:
        raise BadExpression("식이 비었습니다.")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise BadExpression(f"식을 읽을 수 없습니다: {text!r}") from exc
    for node in ast.walk(tree):
        _check(node, text)
    return tree


def _check(node: ast.AST, text: str) -> None:
    if isinstance(node, (ast.Expression, ast.Load)):
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise BadExpression(f"식에는 숫자만 쓸 수 있습니다: {node.value!r} ({text})")
        return
    if isinstance(node, ast.Name):
        return
    if isinstance(node, ast.Attribute):
        # `elastic.youngs_modulus` — 블록.값. 두 단계까지만.
        if not isinstance(node.value, ast.Name):
            raise BadExpression(f"값 자리는 '블록.값' 이어야 합니다 ({text})")
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise BadExpression(f"쓸 수 없는 연산입니다: {type(node.op).__name__} ({text})")
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise BadExpression(f"쓸 수 없는 연산입니다: {type(node.op).__name__} ({text})")
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            allowed = ", ".join(sorted(FUNCTIONS))
            raise BadExpression(f"쓸 수 없는 함수입니다 ({text}). 쓸 수 있는 것: {allowed}")
        if node.keywords:
            raise BadExpression(f"함수에 이름 붙은 인자는 못 씁니다 ({text})")
        return
    if isinstance(node, (ast.operator, ast.unaryop)):
        return
    raise BadExpression(f"식에 쓸 수 없는 것이 있습니다: {type(node).__name__} ({text})")


def names(text: str) -> list[str]:
    """식이 부르는 이름들 — `true_stress`, `elastic.density`. 화면·검증이 쓴다."""
    found: list[str] = []
    bases: set[int] = set()  # `elastic.density` 의 `elastic` 은 이름이 아니라 블록이다
    for node in ast.walk(parse(text)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            found.append(f"{node.value.id}.{node.attr}")
            bases.add(id(node.value))
        elif isinstance(node, ast.Name) and node.id not in FUNCTIONS and id(node) not in bases:
            found.append(node.id)
    return sorted(set(found))


def evaluate(text: str, resolve: Callable[[str], float | None]) -> float:
    """식을 계산한다. `resolve` 가 이름을 값으로 바꾼다 — 없으면 `None` 을 주고,
    그러면 `MissingName` 이 난다."""
    return float(_eval(parse(text).body, resolve))


def _eval(node: ast.AST, resolve: Callable[[str], float | None]) -> Any:
    if isinstance(node, ast.Constant):
        return float(node.value)  # type: ignore[arg-type]  # `_check` 가 숫자만 들였다
    if isinstance(node, ast.Name):
        return _resolve(node.id, resolve)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return _resolve(f"{node.value.id}.{node.attr}", resolve)
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, resolve)
        right = _eval(node.right, resolve)
        try:
            return _BINARY[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise BadExpression("식에서 0 으로 나눴습니다.") from exc
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, resolve)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_eval(arg, resolve) for arg in node.args]
        try:
            return FUNCTIONS[node.func.id](*args)
        except (ValueError, TypeError) as exc:
            raise BadExpression(f"{node.func.id} 를 계산할 수 없습니다: {exc}") from exc
    raise BadExpression(f"식에 쓸 수 없는 것이 있습니다: {type(node).__name__}")


def _resolve(name: str, resolve: Callable[[str], float | None]) -> float:
    value = resolve(name)
    if value is None:
        raise MissingName(name)
    return float(value)
