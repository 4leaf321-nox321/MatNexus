"""계산식 — **식 한 줄을 안전하게 읽고, numpy 로 계산한다** (ADR 0030).

    parse("A + B * x**n")            → Formula (읽기만, 계산 안 함)
    formula.evaluate({"x": …, "A": …, "B": …, "n": …})  → ndarray | float

## `eval` 이 아니다

`ast` 로 읽어 **허용한 노드만** 받는다. 수·이름·사칙·거듭제곱·단항 부호·괄호·허용 함수
호출. 속성 접근(`x.__class__`)·첨자·람다·비교·이름 바인딩·문자열은 전부 거절한다 —
사람이 화면에서 적는 식이므로 임의 코드가 되면 안 된다.

## 이름은 선언한 것만

식에 나온 이름은 **부르는 쪽이 넘긴 변수·파라미터** 아니면 상수(`pi`·`e`)여야 한다.
오타(`stres`)를 `0` 으로 채우면 그럴듯하게 틀린 값이 나온다 — 모르는 이름은 읽는
단계에서 막는다.

## 한 평가기가 세 자리를 덮는다

적합식(곡선을 통째로 넣어 y 배열)·열 단계(점마다)·스칼라 단계(숫자 하나)가 같은 함수를
쓴다 — numpy 브로드캐스팅이 셋을 구별하지 않는다. 그래서 여기는 배열이든 숫자든 받고
같은 모양으로 돌려준다.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: 허용 함수. **여기 없는 이름은 함수로 못 부른다.** 전부 numpy 의 벡터 함수라 배열도
#: 숫자도 같은 모양으로 돌려준다.
FUNCTIONS: dict[str, Any] = {
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "tanh": np.tanh,
    "sinh": np.sinh,
    "cosh": np.cosh,
    "sin": np.sin,
    "cos": np.cos,
    "pow": np.power,
    "min": np.minimum,
    "max": np.maximum,
    "where": np.where,
    "clip": np.clip,
}

CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}

#: 식 길이와 노드 수의 상한. 루프가 없으니 실행 시간은 유계지만, 수만 노드짜리 식은
#: 읽는 것만으로도 느리고 사람이 읽을 수 없다.
MAX_LENGTH = 1000
MAX_NODES = 300

_BINARY = {
    ast.Add: np.add,
    ast.Sub: np.subtract,
    ast.Mult: np.multiply,
    ast.Div: np.divide,
    ast.Pow: np.power,
    ast.Mod: np.mod,
}
_UNARY = {ast.USub: np.negative, ast.UAdd: np.positive}


class FormulaError(ValueError):
    """식을 읽거나 계산하지 못했다. **메시지는 사용자가 읽는다.**"""


@dataclass(frozen=True)
class Formula:
    """읽힌 식. `names` 는 식이 쓰는 이름(상수 제외) — 부르는 쪽이 전부 넘겨야 한다."""

    source: str
    names: tuple[str, ...]
    _tree: ast.Expression = field(repr=False, compare=False)

    def evaluate(self, values: Mapping[str, Any]) -> Any:
        """이름 → 값(숫자·배열)을 넣어 계산한다. 배열을 넣으면 배열이 나온다."""
        missing = [name for name in self.names if name not in values]
        if missing:
            raise FormulaError(f"식에 값이 없는 이름이 있습니다: {', '.join(missing)}")
        env = {**CONSTANTS, **{key: _as_number(key, value) for key, value in values.items()}}
        with np.errstate(all="ignore"):
            return _eval(self._tree.body, env)


def _as_number(name: str, value: Any) -> Any:
    if isinstance(value, bool):
        raise FormulaError(f"'{name}' 은 참/거짓입니다 — 식은 수만 받습니다.")
    if isinstance(value, int | float):
        return float(value)
    array = np.asarray(value, dtype=np.float64)
    if array.ndim > 1:
        raise FormulaError(f"'{name}' 은 2차원 이상입니다 — 식은 열(1차원)까지 받습니다.")
    return array


def parse(source: str) -> Formula:
    """식을 읽는다. 허용 밖의 것이 있으면 **어느 것이 왜** 안 되는지 말한다."""
    text = (source or "").strip()
    if not text:
        raise FormulaError("식이 비었습니다.")
    if len(text) > MAX_LENGTH:
        raise FormulaError(f"식이 너무 깁니다({len(text)}자 > {MAX_LENGTH}자).")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"식을 읽지 못했습니다: {exc.msg} (위치 {exc.offset})") from exc
    found: list[tuple[int, int, str]] = []
    count = 0
    for node in ast.walk(tree):
        count += 1
        _check(node, found)
    if count > MAX_NODES:
        raise FormulaError(f"식이 너무 복잡합니다({count} 노드 > {MAX_NODES}).")
    # 이름은 **식에 나온 차례**로 — 화면이 변수 칸을 이 순서로 그린다.
    ordered = [name for _line, _col, name in sorted(found)]
    return Formula(source=text, names=tuple(dict.fromkeys(ordered)), _tree=tree)


def _check(node: ast.AST, found: list[tuple[int, int, str]]) -> None:
    if isinstance(node, ast.Expression):
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise FormulaError(f"수만 적을 수 있습니다: {node.value!r}")
        return
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, ast.Load):
            if node.id not in CONSTANTS and node.id not in FUNCTIONS:
                found.append((node.lineno, node.col_offset, node.id))
            return
        raise FormulaError(f"이름에 값을 넣을 수 없습니다: {node.id}")
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise FormulaError(f"쓸 수 없는 연산입니다: {type(node.op).__name__}")
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise FormulaError(f"쓸 수 없는 단항 연산입니다: {type(node.op).__name__}")
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            shown = ast.unparse(node.func) if hasattr(ast, "unparse") else "?"
            raise FormulaError(
                f"쓸 수 없는 함수입니다: {shown}. 되는 것: {', '.join(sorted(FUNCTIONS))}"
            )
        if node.keywords:
            raise FormulaError("함수에 이름 붙인 인자는 못 씁니다.")
        return
    if isinstance(node, ast.operator | ast.unaryop | ast.expr_context):
        return
    raise FormulaError(f"식에 쓸 수 없는 것이 있습니다: {type(node).__name__}")


def _eval(node: ast.AST, env: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        assert isinstance(node.value, int | float)  # parse 가 수만 통과시켰다
        return float(node.value)
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.BinOp):
        return _BINARY[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)
        return FUNCTIONS[node.func.id](*(_eval(arg, env) for arg in node.args))
    raise FormulaError(f"계산할 수 없는 것: {type(node).__name__}")  # parse 가 막았어야 한다


__all__ = ["CONSTANTS", "FUNCTIONS", "Formula", "FormulaError", "parse"]
