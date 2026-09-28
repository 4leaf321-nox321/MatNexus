"""덱 정의의 **식** — 값·열을 계산하고, 조건을 묻고, 표를 센다.

정의가 값을 그대로 꽂는 것만 됐다(2026-09-05 산술을 넣었다). 기본 제공 형식을 정의로 옮겨
보니(2026-09-28, ADR 0038) 남은 자리가 산술이 아니라 **표와 조건**이었다 — 항복응력은 표의
첫 점이고, 장기 탄성률은 Prony 합이고, 초탄성 식은 글자 값으로 갈린다. 그래서 넓혔다:

    값        elastic.density(블록.값) · true_stress(표 줄의 열) · _index(자리 변수)
    산술      + - * / ^ ( ) · sqrt abs exp log log10 min max
    비교·논리  < <= > >= == != · and or not · A if 조건 else B
    글자      "ogden_1" — 비교하고 글자 줄에 적는 데만
    있나      has(elastic.density) — 빠진 값을 묻는 유일한 길
    표        count(표[, 조건]) · sum(표, 식[, 조건]) · first/last(표, 식[, 조건])
              min_of/max_of(표, 식[, 조건]) · distinct(표, 식) · joined(표, 글자, 사이[, 조건])
    글자로    fmt(x, ".3g") · 글자 + 글자 · round(x, 3)

표 함수의 첫 인자는 표 이름이고, 둘째부터는 **그 표의 줄마다** 계산한다 — 맨 이름은 그 줄의
열이다(표 줄의 식과 같은 규칙). `first(curve, true_stress)` 는 정리된 소성 곡선의 첫 응력,
곧 항복응력이다.

## 빠진 값

값이 없으면 `MissingName` 이 난다. `has(x)` 는 그것을 거짓으로 바꾸고, `x or "unknown"` 은
다음 것으로 넘어간다. 조건(`when`)에서 빠진 값은 거짓이다 — 칸에서는 `when` 으로 걸러야 하는
줄이라 멈춘다.

## `eval` 은 쓰지 않는다

정의는 데이터라 누구나 적고, 그 글자가 서버에서 코드로 돈다면 곧 원격 실행이다. 파이썬
문법 트리를 읽어 위의 것만 허용한다 — 그 밖의 것은 이름을 대며 거절한다. 정수끼리의
거듭제곱은 실수로 바꿔 계산한다: `10 ^ 10 ^ 10` 이 정수로 돌면 서버가 멈춘다.

`^` 는 거듭제곱으로 읽는다. 사람은 `x^2` 라고 쓰고, 파이썬은 그것을 XOR 로 읽는다.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable, Sequence
from functools import lru_cache
from typing import Any, Protocol, cast

#: 허용하는 이항 연산.
_BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_COMPARE: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
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
    "round": round,
}

#: 표 함수 → (인자 수 최소, 최대). 첫 인자는 표 이름이다.
TABLE_FUNCTIONS: dict[str, tuple[int, int]] = {
    "count": (1, 2),
    "sum": (2, 3),
    "first": (2, 3),
    "last": (2, 3),
    "min_of": (2, 3),
    "max_of": (2, 3),
    "distinct": (2, 2),
    # 줄마다의 글자를 잇는다 — 알림의 「잘린 속도: 0.001, 0.1」.
    "joined": (3, 4),
}

#: 파이썬 형식 문자열 모양 — `fmt(x, ".3g")`. 템플릿의 `["spec", …]` 과 같은 규칙.
_FMT = r"^(?:.?[<>=^])?[+\- ]?z?#?0?\d{0,3},?(?:\.\d{1,2})?[eEfFgGd%s]?$"


class BadExpression(ValueError):
    """식이 문법에 안 맞거나 허용 밖의 것을 쓴다. 저장 전에 잡는다."""


class MissingName(KeyError):
    """식이 부르는 값·열이 덱에 없다. 렌더링 때 난다 — `when` 으로 걸러야 하는 줄."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class Scope(Protocol):
    """식이 이름을 찾는 곳. 템플릿이 준다 — 블록 값·표 줄·자리 변수를 안다."""

    def lookup(self, name: str) -> Any:
        """`블록.값` · 열 이름 · `_변수`. 없으면 `MissingName`."""

    def rows(self, table: str) -> Sequence[Scope]:
        """표 하나의 줄마다의 이름 공간."""


class _Plain:
    """이름 → 값 함수 하나로 된 이름 공간 — 예전 부르는 법(`evaluate(text, resolve)`)."""

    def __init__(self, resolve: Callable[[str], Any]) -> None:
        self._resolve = resolve

    def lookup(self, name: str) -> Any:
        value = self._resolve(name)
        if value is None:
            raise MissingName(name)
        return value

    def rows(self, table: str) -> Sequence[Scope]:
        raise BadExpression(f"표 함수는 여기서 못 씁니다: {table}")


def _source(text: str) -> str:
    return text.replace("^", "**").strip()


@lru_cache(maxsize=4096)
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
    if isinstance(
        node,
        (ast.Expression, ast.Load, ast.operator, ast.unaryop, ast.cmpop, ast.boolop, ast.Name),
    ):
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, str)):
            raise BadExpression(
                f"식에는 숫자와 글자만 쓸 수 있습니다: {node.value!r} ({text})"
            )
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
        if not isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            raise BadExpression(f"쓸 수 없는 연산입니다: {type(node.op).__name__} ({text})")
        return
    if isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _COMPARE:
                raise BadExpression(f"쓸 수 없는 비교입니다: {type(op).__name__} ({text})")
        return
    if isinstance(node, (ast.BoolOp, ast.IfExp)):
        return
    if isinstance(node, ast.Call):
        _check_call(node, text)
        return
    raise BadExpression(f"식에 쓸 수 없는 것이 있습니다: {type(node).__name__} ({text})")


def _check_call(node: ast.Call, text: str) -> None:
    if not isinstance(node.func, ast.Name):
        raise BadExpression(f"쓸 수 없는 함수입니다 ({text})")
    name = node.func.id
    if node.keywords:
        raise BadExpression(f"함수에 이름 붙은 인자는 못 씁니다 ({text})")
    if name == "has":
        if len(node.args) != 1:
            raise BadExpression(f"has 는 인자가 하나입니다 ({text})")
        return
    if name == "fmt":
        spec = node.args[1] if len(node.args) == 2 else None
        if not isinstance(spec, ast.Constant) or not isinstance(spec.value, str):
            raise BadExpression(f'fmt 는 (값, "형식") 입니다 — fmt(x, ".3g") ({text})')
        if re.fullmatch(_FMT, spec.value) is None:
            raise BadExpression(f"fmt 의 형식을 읽을 수 없습니다: {spec.value!r} ({text})")
        return
    if name in TABLE_FUNCTIONS:
        low, high = TABLE_FUNCTIONS[name]
        if not low <= len(node.args) <= high or not isinstance(node.args[0], ast.Name):
            raise BadExpression(
                f"{name} 은 (표 이름{', 식' if low > 1 else ''}[, 조건]) 입니다 ({text})"
            )
        return
    if name not in FUNCTIONS:
        allowed = ", ".join(sorted({*FUNCTIONS, *TABLE_FUNCTIONS, "has", "fmt"}))
        raise BadExpression(f"쓸 수 없는 함수입니다 ({text}). 쓸 수 있는 것: {allowed}")


def names(text: str) -> list[str]:
    """식이 부르는 값·열 이름 — `true_stress`, `elastic.density`. 화면·검증이 쓴다.

    함수 이름과 표 함수의 표 이름은 뺀다 — 값이 아니다.
    """
    found: list[str] = []
    skip: set[int] = set()  # `elastic.density` 의 `elastic`, 함수 이름, 표 이름
    for node in ast.walk(parse(text)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            skip.add(id(node.func))
            if node.func.id in TABLE_FUNCTIONS and node.args:
                skip.add(id(node.args[0]))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            found.append(f"{node.value.id}.{node.attr}")
            skip.add(id(node.value))
    for node in ast.walk(parse(text)):
        if isinstance(node, ast.Name) and id(node) not in skip:
            found.append(node.id)
    return sorted(set(found))


def evaluate(text: str, resolve: Callable[[str], Any] | Scope) -> float:
    """식을 **숫자로** 계산한다. `resolve` 는 이름 → 값 함수이거나 `Scope` 다.

    없으면 `MissingName` 이 난다. 숫자가 아니면(글자·참거짓) 멈춘다 — 칸에는 숫자가 간다.
    """
    value = evaluate_any(text, resolve)
    if not _is_number(value):
        raise BadExpression(f"식의 값이 숫자가 아닙니다: {value!r} ({text})")
    return float(value)


def evaluate_any(text: str, resolve: Callable[[str], Any] | Scope) -> Any:
    """식을 계산한다 — 숫자·글자·참거짓 그대로. 글자 줄의 자리표가 쓴다."""
    scope: Scope = cast(Scope, resolve) if hasattr(resolve, "lookup") else _Plain(resolve)
    return _eval(parse(text).body, scope, text)


def truth(text: str, scope: Scope) -> bool:
    """조건 — **빠진 값은 거짓이다.** 「밀도가 있으면」 을 `elastic.density > 0` 으로 적어도
    밀도가 없는 카드에서 멈추지 않는다."""
    try:
        return _truthy(evaluate_any(text, scope))
    except MissingName:
        return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _truthy(value: Any) -> bool:
    return bool(value)


def _number(value: Any, text: str) -> int | float:
    if not _is_number(value):
        raise BadExpression(f"숫자가 아닌 것으로 계산하려 했습니다: {value!r} ({text})")
    return value  # type: ignore[no-any-return]


def _eval(node: ast.AST, scope: Scope, text: str) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return scope.lookup(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return scope.lookup(f"{node.value.id}.{node.attr}")
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, scope, text), _eval(node.right, scope, text)
        if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
            # **글자끼리는 잇는다** — 알림의 「0.001↔0.1 1/s」.
            return left + right
        left, right = _number(left, text), _number(right, text)
        if isinstance(node.op, ast.Pow):
            # **정수 거듭제곱은 실수로.** `10 ^ 10 ^ 10` 을 정수로 계산하면 서버가 멈춘다.
            left, right = float(left), float(right)
        try:
            return _BINARY[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise BadExpression("식에서 0 으로 나눴습니다.") from exc
        except OverflowError as exc:
            raise BadExpression(f"식의 값이 너무 큽니다 ({text})") from exc
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, scope, text)
        if isinstance(node.op, ast.Not):
            return not _truthy(value)
        value = _number(value, text)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BoolOp):
        return _bool_op(node, scope, text)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, scope, text)
        for op, right_node in zip(node.ops, node.comparators, strict=True):
            right = _eval(right_node, scope, text)
            try:
                if not _COMPARE[type(op)](left, right):
                    return False
            except TypeError as exc:
                raise BadExpression(
                    f"견줄 수 없는 둘입니다: {left!r}, {right!r} ({text})"
                ) from exc
            left = right
        return True
    if isinstance(node, ast.IfExp):
        chosen = node.body if _truthy(_eval(node.test, scope, text)) else node.orelse
        return _eval(chosen, scope, text)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _call(node, scope, text)
    raise BadExpression(f"식에 쓸 수 없는 것이 있습니다: {type(node).__name__}")


def _bool_op(node: ast.BoolOp, scope: Scope, text: str) -> Any:
    """`or` 는 **빠진 값을 건너뛴다** — `thermal.source or "unknown"`. `and` 는 빠진 값을
    그대로 올린다(조건이면 거짓이 된다)."""
    if isinstance(node.op, ast.And):
        value: Any = True
        for one in node.values:
            value = _eval(one, scope, text)
            if not _truthy(value):
                return value
        return value
    missing: MissingName | None = None
    value = False
    for one in node.values:
        try:
            value = _eval(one, scope, text)
        except MissingName as exc:
            missing = exc
            continue
        if _truthy(value):
            return value
    if missing is not None and not _truthy(value):
        raise missing
    return value


def _call(node: ast.Call, scope: Scope, text: str) -> Any:
    assert isinstance(node.func, ast.Name)
    name = node.func.id
    if name == "has":
        try:
            _eval(node.args[0], scope, text)
        except MissingName:
            return False
        return True
    if name in TABLE_FUNCTIONS:
        return _table_call(name, node, scope, text)
    if name == "fmt":
        value = _eval(node.args[0], scope, text)
        spec = node.args[1]
        assert isinstance(spec, ast.Constant)
        try:
            return format(value, str(spec.value))
        except (ValueError, TypeError) as exc:
            raise BadExpression(f"fmt 로 {value!r} 를 적을 수 없습니다: {exc}") from exc
    args = [_number(_eval(arg, scope, text), text) for arg in node.args]
    try:
        return FUNCTIONS[name](*args)
    except (ValueError, TypeError) as exc:
        raise BadExpression(f"{name} 를 계산할 수 없습니다: {exc}") from exc


def _table_call(name: str, node: ast.Call, scope: Scope, text: str) -> Any:
    """표 함수 — 첫 인자는 표 이름, 나머지는 **그 표의 줄마다** 계산한다."""
    table = node.args[0]
    assert isinstance(table, ast.Name)
    rows = list(scope.rows(table.id))
    if name == "count":
        if len(node.args) == 1:
            return len(rows)
        return sum(1 for row in rows if _row_truth(node.args[1], row, text))
    expression = node.args[1]
    if name == "joined":
        # joined(표, 글자 식, 사이 글자[, 조건])
        if len(node.args) == 4:
            rows = [row for row in rows if _row_truth(node.args[3], row, text)]
        between = _eval(node.args[2], scope, text)
        pieces = [_eval(expression, row, text) for row in rows]
        if not isinstance(between, str) or not all(isinstance(one, str) for one in pieces):
            raise BadExpression(
                f"joined 는 글자를 잇습니다 — fmt(…) 로 글자로 바꾸세요 ({text})"
            )
        return between.join(pieces)
    if len(node.args) == 3:
        rows = [row for row in rows if _row_truth(node.args[2], row, text)]
    if name == "distinct":
        return len({_eval(expression, row, text) for row in rows})
    values = [_eval(expression, row, text) for row in rows]
    if name == "sum":
        # 코드 렌더러와 **같은 차례로 더한다** — 0 에서 시작해 앞에서부터. 차례가 다르면
        # 마지막 자리가 달라져 덱이 바이트로 어긋난다.
        total: int | float = 0
        for value in values:
            total = total + _number(value, text)
        return total
    if not values:
        raise MissingName(f"{table.id} 의 {'첫' if name == 'first' else '마지막'} 줄")
    if name == "first":
        return values[0]
    if name == "last":
        return values[-1]
    numbers = [_number(value, text) for value in values]
    return min(numbers) if name == "min_of" else max(numbers)


def _row_truth(condition: ast.AST, row: Scope, text: str) -> bool:
    try:
        return _truthy(_eval(condition, row, text))
    except MissingName:
        return False
