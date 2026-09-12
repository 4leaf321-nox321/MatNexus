"""계산식을 **레지스트리의 시민으로** 만든다 (ADR 0030 D1·D3·D4).

`matcore.formula` 는 식을 읽고 계산할 뿐이다. 여기서 식 하나(`FormulaSpec`)를 세 자리
가운데 하나로 바꿔 등록한다:

    kind="family"        → fitting.Family          (곡선에 맞춰 파라미터를 구한다)
    kind="scalar_step"   → registry(processing)    (앞 단계 값들로 스칼라 하나)
    kind="column_step"   → registry(processing)    (프레임 열들로 새 열 하나, 점마다)

DB 를 모른다 — spec 은 부르는 쪽(app)이 표에서 읽어 넘긴다.

## 이름공간 `formula.`

등록 키는 전부 `formula.<key>` 다. 내장·파이썬 확장과 같은 레지스트리에 서되 겹치지
않고, **이 접두어만 다시 등록(교체)할 수 있다** — 식을 고치면 판이 오르고 레지스트리의
항목이 새 판으로 바뀌어야 하는데, 내장·확장은 그런 일이 없어야 하기 때문이다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from matcore import fitting, formula, registry
from matcore.processing import Frame, Scalar, StepResult
from matcore.registry import ParamSpec, Produced

PREFIX = "formula."

KINDS = ("family", "scalar_step", "column_step")


class FormulaSpecError(ValueError):
    """식은 읽히는데 **자리에 맞지 않는다** — 축이 없거나, 파라미터 선언이 식과 안 맞거나."""


@dataclass(frozen=True)
class Parameter:
    """적합식의 파라미터 하나 — 이름·단위·초기값·범위."""

    name: str
    unit: str = "1"
    initial: float = 1.0
    lower: float = -np.inf
    upper: float = np.inf


@dataclass(frozen=True)
class Variable:
    """식의 입력 하나. 자리마다 뜻이 다르다.

    - family: `x` 하나 — 곡선의 x 축(`x_column`)
    - scalar_step: 앞 단계가 낸 스칼라 (`@name` 으로 받는다)
    - column_step: 프레임의 열
    """

    name: str
    unit: str = "1"
    label: str | None = None


@dataclass(frozen=True)
class FormulaSpec:
    key: str
    kind: str
    label: str
    expression: str
    variables: tuple[Variable, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    """적합식만."""
    result: Produced | None = None
    """스칼라·열 단계가 내는 것의 이름·단위. 적합식은 파라미터가 결과라 비운다."""
    x_column: str = "strain_true_plastic"
    y_column: str = "stress_true"
    x_label: str = "진소성변형률"
    y_label: str = "진응력"
    block: str = "hardening"
    applies_to: tuple[str, ...] = ()
    requires_channels: tuple[tuple[str, ...], ...] = ()
    describe: str = ""
    version: str = "1"
    order: int = 88
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def registry_key(self) -> str:
        return PREFIX + self.key


def validate(spec: FormulaSpec) -> formula.Formula:
    """식이 읽히고 **자리에 맞는지** 본다. 맞으면 읽힌 식을 돌려준다."""
    if spec.kind not in KINDS:
        raise FormulaSpecError(f"자리는 {', '.join(KINDS)} 중 하나입니다: {spec.kind}")
    if not spec.key or not spec.key.replace("_", "").isalnum() or not spec.key[0].isalpha():
        raise FormulaSpecError("key 는 영문 소문자로 시작하는 snake_case 여야 합니다.")
    try:
        parsed = formula.parse(spec.expression)
    except formula.FormulaError as exc:
        raise FormulaSpecError(str(exc)) from exc

    declared = {one.name for one in spec.variables} | {one.name for one in spec.parameters}
    unknown = [name for name in parsed.names if name not in declared]
    if unknown:
        raise FormulaSpecError(
            f"식이 쓰는 이름이 선언에 없습니다: {', '.join(unknown)}. "
            "변수(입력)나 파라미터로 적으세요."
        )
    unused = sorted(declared - set(parsed.names))
    if unused:
        raise FormulaSpecError(f"선언했는데 식에 없는 이름이 있습니다: {', '.join(unused)}")

    if spec.kind == "family":
        if not spec.parameters:
            raise FormulaSpecError("적합식에는 구할 파라미터가 하나 이상 있어야 합니다.")
        if [one.name for one in spec.variables] != ["x"]:
            raise FormulaSpecError(
                "적합식의 변수는 `x` 하나입니다 — 축은 x_column 이 정합니다."
            )
        for one in spec.parameters:
            if not (one.lower <= one.initial <= one.upper):
                raise FormulaSpecError(
                    f"파라미터 {one.name} 의 초기값 {one.initial} 이 범위 "
                    f"[{one.lower}, {one.upper}] 밖입니다."
                )
    else:
        if spec.parameters:
            raise FormulaSpecError("단계에는 파라미터가 없습니다 — 상수는 식에 적으세요.")
        if not spec.variables:
            raise FormulaSpecError("단계에는 입력(변수)이 하나 이상 있어야 합니다.")
        if spec.result is None or not spec.result.key:
            raise FormulaSpecError("단계는 내는 값의 이름과 단위(result)를 적어야 합니다.")
        if spec.result.key in declared:
            raise FormulaSpecError("내는 값의 이름이 입력 이름과 겹칩니다.")
    return parsed


# ── 적합식 ───────────────────────────────────────────────────────────────────


def build_family(spec: FormulaSpec) -> fitting.Family:
    parsed = validate(spec)
    names = tuple(one.name for one in spec.parameters)
    units = tuple(one.unit for one in spec.parameters)
    initial = np.asarray([one.initial for one in spec.parameters], dtype=np.float64)
    lower = np.asarray([one.lower for one in spec.parameters], dtype=np.float64)
    upper = np.asarray([one.upper for one in spec.parameters], dtype=np.float64)

    def evaluate(parameters: np.ndarray, x: np.ndarray) -> np.ndarray:
        values: dict[str, Any] = {"x": np.asarray(x, dtype=np.float64)}
        for name, value in zip(names, parameters, strict=True):
            values[name] = float(value)
        got = parsed.evaluate(values)
        return np.broadcast_to(np.asarray(got, dtype=np.float64), np.shape(x)).copy()

    def guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return initial.copy()

    def bounds(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return lower.copy(), upper.copy()

    return fitting.Family(
        key=spec.registry_key,
        label=spec.label,
        parameter_names=names,
        parameter_units=units,
        evaluate=evaluate,
        guess=guess,
        bounds=bounds,
        describe=spec.describe or f"y = {spec.expression}",
        x_label=spec.x_label,
        y_label=spec.y_label,
        x_column=spec.x_column,
        y_column=spec.y_column,
        # 소성 구간 다듬기는 축이 소성 변형률일 때만 뜻이 있다 — 내장 금속 식과 같은 판단.
        prepare=fitting.plastic_branch if spec.x_column == "strain_true_plastic" else None,
        block=spec.block,
        applies_to=spec.applies_to,
    )


# ── 처리 단계 ────────────────────────────────────────────────────────────────


def build_step(spec: FormulaSpec) -> tuple[Callable[..., StepResult], dict[str, Any]]:
    """`(함수, register 에 넘길 인자)` — 부르는 쪽이 `registry.register(**kwargs)(fn)` 한다."""
    parsed = validate(spec)
    assert spec.result is not None
    result = spec.result

    if spec.kind == "scalar_step":
        params = tuple(
            ParamSpec(
                name=one.name,
                label=one.label or one.name,
                type="float",
                unit=one.unit,
                default=f"@{one.name}",
                required=True,
                help="앞 단계가 낸 값. `@이름` 이면 그 값을 그대로 받는다.",
            )
            for one in spec.variables
        )

        def scalar_step(frame: Frame, options: dict[str, Any]) -> StepResult:
            values: dict[str, float] = {}
            for one in spec.variables:
                raw = options.get(one.name)
                if not isinstance(raw, int | float) or isinstance(raw, bool):
                    return StepResult(
                        frame=frame,
                        notes=(
                            f"'{one.label or one.name}' 값이 없어 {result.label} 을 "
                            "내지 않았습니다.",
                        ),
                    )
                values[one.name] = float(raw)
            try:
                got = float(parsed.evaluate(values))
            except (formula.FormulaError, TypeError, ValueError) as exc:
                return StepResult(frame=frame, notes=(f"{result.label}: {exc}",))
            if not np.isfinite(got):
                return StepResult(
                    frame=frame,
                    notes=(f"{result.label} 이 수가 아닙니다({got}) — 식이나 입력을 보세요.",),
                )
            unit = result.si_unit or ""
            note = f"{result.label} = {spec.expression} → {got:.6g} {unit}".rstrip()
            return StepResult(
                frame=frame,
                scalars=(Scalar(result.key, result.label, got, result.si_unit or "1"),),
                notes=(note,),
            )

        kwargs: dict[str, Any] = {
            "id": spec.registry_key,
            "kind": "processing",
            "label": spec.label,
            "params": params,
            "applies_to": spec.applies_to,
            "requires_channels": spec.requires_channels,
            "makes_values": (result,),
            "order": spec.order,
            "version": spec.version,
            "formula": spec.expression,
        }
        return scalar_step, kwargs

    # column_step
    def column_step(frame: Frame, options: dict[str, Any]) -> StepResult:
        values: dict[str, Any] = {}
        for one in spec.variables:
            if one.name not in frame.columns:
                available = ", ".join(sorted(frame.columns)) or "(없음)"
                return StepResult(
                    frame=frame,
                    notes=(
                        f"'{one.name}' 열이 없어 {result.label} 을 만들지 않았습니다. "
                        f"있는 열: {available}",
                    ),
                )
            values[one.name] = frame.columns[one.name]
        try:
            got = np.asarray(parsed.evaluate(values), dtype=np.float64)
        except (formula.FormulaError, TypeError, ValueError) as exc:
            return StepResult(frame=frame, notes=(f"{result.label}: {exc}",))
        got = np.broadcast_to(got, (frame.length(),)).copy()
        return StepResult(
            frame=frame.with_columns({result.key: got}, {result.key: result.si_unit or "1"}),
            notes=(f"{result.key} = {spec.expression}",),
        )

    kwargs = {
        "id": spec.registry_key,
        "kind": "processing",
        "label": spec.label,
        "params": (),
        "applies_to": spec.applies_to,
        "requires_channels": spec.requires_channels
        or tuple((one.name,) for one in spec.variables),
        "makes_columns": (result,),
        "order": spec.order,
        "version": spec.version,
        "formula": spec.expression,
    }
    return column_step, kwargs


# ── 등록·교체 ────────────────────────────────────────────────────────────────


def _forget(key: str) -> None:
    """`formula.` 접두어만 빼낸다 — 내장·확장은 이 길로 못 지운다."""
    assert key.startswith(PREFIX), key
    registry._REGISTRY.pop(key, None)
    fitting.FAMILIES.pop(key, None)


def install(spec: FormulaSpec) -> str:
    """등록한다. 같은 키가 있으면 **새 판으로 바꾼다.** 등록 키를 돌려준다."""
    key = spec.registry_key
    if spec.kind == "family":
        family = build_family(spec)
        _forget(key)
        fitting.register_family(family)
        return key
    fn, kwargs = build_step(spec)
    _forget(key)
    registry.register(**kwargs)(fn)
    return key


def uninstall(key: str) -> None:
    if not key.startswith(PREFIX):
        raise FormulaSpecError(f"계산식이 아닌 것은 뺄 수 없습니다: {key}")
    _forget(key)


def installed() -> list[str]:
    """지금 레지스트리에 있는 계산식 키들."""
    found = [key for key in registry._REGISTRY if key.startswith(PREFIX)]
    found += [key for key in fitting.FAMILIES if key.startswith(PREFIX)]
    return sorted(set(found))


__all__ = [
    "KINDS",
    "PREFIX",
    "FormulaSpec",
    "FormulaSpecError",
    "Parameter",
    "Variable",
    "build_family",
    "build_step",
    "install",
    "installed",
    "uninstall",
    "validate",
]
