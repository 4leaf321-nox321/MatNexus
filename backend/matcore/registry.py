"""플러그인 레지스트리 — D7("정의는 데이터, 계산은 플러그인")의 계산 쪽.

65는 물성 6종을 4계층에 걸친 슬라이스로 복제해 131파일 44k줄이 됐다. 여기서는
계산 하나가 함수 하나이고, 등록하면 API·화면·익스포트가 따라온다.

이 패키지 전체가 DB도 HTTP도 모른다. tests/architecture가 이를 검사한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["parser", "processing", "statistics", "fitting", "export"]


@dataclass(frozen=True)
class ParamSpec:
    """사용자가 조절하는 값 하나. 화면의 폼 필드가 여기서 생성된다."""

    name: str
    label: str
    type: Literal["float", "int", "bool", "str", "choice"]
    default: Any = None
    choices: tuple[str, ...] = ()
    unit: str | None = None
    help: str | None = None


@dataclass(frozen=True)
class Plugin:
    id: str
    kind: Kind
    label: str
    fn: Callable[..., Any]
    inputs: tuple[str, ...] = ()
    produces: str | None = None
    params: tuple[ParamSpec, ...] = ()
    applies_to: tuple[str, ...] = ()
    """적용 가능한 재료군·시험종류. 비어 있으면 제한 없음."""
    version: str = "1"
    """계산이 바뀌면 올린다. 결과 아티팩트에 기록해 재현 가능성을 남긴다."""
    meta: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, Plugin] = {}


def register(
    *,
    id: str,
    kind: Kind,
    label: str,
    inputs: tuple[str, ...] = (),
    produces: str | None = None,
    params: tuple[ParamSpec, ...] = (),
    applies_to: tuple[str, ...] = (),
    version: str = "1",
    **meta: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """계산 함수를 레지스트리에 등록한다.

    >>> @register(id="metal.voce", kind="fitting", label="Voce 경화식")
    ... def fit_voce(curve, opts): ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if id in _REGISTRY:
            raise ValueError(f"플러그인 id 중복: {id}")
        _REGISTRY[id] = Plugin(
            id=id,
            kind=kind,
            label=label,
            fn=fn,
            inputs=inputs,
            produces=produces,
            params=params,
            applies_to=applies_to,
            version=version,
            meta=meta,
        )
        return fn

    return decorator


def get(plugin_id: str) -> Plugin:
    try:
        return _REGISTRY[plugin_id]
    except KeyError:
        raise KeyError(f"등록되지 않은 플러그인: {plugin_id}") from None


def list_plugins(kind: Kind | None = None, applies_to: str | None = None) -> list[Plugin]:
    items = [p for p in _REGISTRY.values() if kind is None or p.kind == kind]
    if applies_to is not None:
        items = [p for p in items if not p.applies_to or applies_to in p.applies_to]
    return sorted(items, key=lambda p: p.id)


def clear() -> None:
    """테스트 전용."""
    _REGISTRY.clear()
