"""물성 블록 — **카드는 블록의 모음이다.**

## 레지스트리가 한 층 깊은 곳에 있었다

경화식은 이미 데이터였다. `matcore.fitting.FAMILIES` 에 하나 더하면 화면의 목록이
따라오고, Ghosh 를 붙이는 데 마이그레이션도 스키마도 화면도 필요 없다.

그런데 **물성의 종류**는 코드였다. 카드가 `elastic`·`hardening`·`table` 이라는
컬럼 셋을 갖고, 그 이름을 모델·스키마·라우트·화면이 각각 알고 있었다. 점탄성을
더하려면 네 번째 컬럼이, 초탄성이면 다섯 번째가 필요했다 — 매번 마이그레이션과
스키마와 화면이 딸려 온다.

폴리머 점탄성 슬라이스에서 **D7 이 못 미친 45%(저장·API·화면)의 정체가 그것**이다.
계산은 플러그인이 됐는데 물성의 갈래는 안 됐다.

셋 다 **이미 JSONB 였다**는 점이 이 구조의 아이러니였다 — 안은 형식이 없는데
바깥의 컬럼 이름만 굳어 있었다. JSONB 를 쓰는 이유를 절반 버린 모양이다.

## payload 의 모양은 하나다

블록이 무엇이든 담기는 모양은 같다. 그래야 화면이 **선언만으로** 그린다.

    {"values": {키: 값}, "rows": [{열: 값}], "notes": [문장]}

셋 다 선택이다. `values` 의 뜻은 `BlockSpec.produces` 가, `rows` 의 열은
`BlockSpec.rows` 가 준다 — `Produced` 를 그대로 쓴다(v1.19.0). 이름을 정하는
자리에서 뜻도 같이 적게 하는 장치이고, 처리 단계가 이미 그렇게 하고 있다.

**값의 출처는 `<키>_source` 에 둔다.** 7850 이 실측인지 관례값인지 덱만 봐서는
모르고, 화면에서도 모른다. 규칙으로 정해 두면 새 블록이 저절로 따라온다.

**행이 `si_unit` 을 들고 있으면 그것이 이긴다.** 경화식 파라미터는 식마다 단위가
다르다 — Voce 의 `b` 는 무차원이고 `q` 는 Pa 다. 열 선언 하나로는 못 적는다.

## 새 물성 1종에 드는 것

`BlockSpec` 하나다. 마이그레이션 0, 스키마 0, 화면 0 — 이 파일 옆에 파일 하나를
두고 `register_block` 을 부르면 저장·API·화면이 따라온다. 그것이 D7 의 수용
기준이고, 여기가 그 기준이 성립하는지 재는 자리다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from matcore.registry import Produced


class CardError(Exception):
    """블록을 솔버 카드로 옮기지 못했다.

    메시지는 **사용자가 읽는다.** 무엇이 없고 어디서 채우면 되는지 적는다.
    """


@dataclass(frozen=True)
class BlockSpec:
    """카드에 실리는 물성 한 갈래."""

    key: str
    label: str
    help: str
    """이 블록이 무엇인지 한 줄. **화면에 그대로 뜬다.**"""

    produces: tuple[Produced, ...] = ()
    """`values` 에 담기는 스칼라의 이름과 뜻.

    화면이 이 선언만으로 블록을 그린다. 선언하지 않은 키도 payload 에 남지만
    화면에는 안 뜬다 — `_source` 처럼 값에 딸린 것들이 그렇다."""

    rows: tuple[Produced, ...] = ()
    """`rows` 의 열 선언. 비어 있으면 이 블록에는 표가 없다.

    **행이 `si_unit` 을 들고 있으면 그것이 이긴다** — 경화식 파라미터는 식마다
    단위가 다르다."""

    order: int = 100
    """화면에 보이는 순서. **작을수록 앞.**"""

    meta: dict[str, Any] = field(default_factory=dict)


_BLOCKS: dict[str, BlockSpec] = {}


def register_block(spec: BlockSpec) -> BlockSpec:
    """블록을 레지스트리에 등록한다. 등록된 순간부터 저장·API·화면이 안다."""
    if spec.key in _BLOCKS:
        raise ValueError(f"물성 블록 key 중복: {spec.key}")
    # **이름 없는 선언을 막는다**(v1.19.0 과 같은 검사). label 이 비면 화면에
    # 키가 그대로 뜨고, 그것이 무엇인지는 코드를 읽어야 알게 된다.
    for item in (*spec.produces, *spec.rows):
        if not item.label.strip():
            raise ValueError(f"{spec.key}.{item.key} 에 이름이 없습니다.")
    _BLOCKS[spec.key] = spec
    return spec


def block(key: str) -> BlockSpec:
    try:
        return _BLOCKS[key]
    except KeyError:
        known = ", ".join(sorted(_BLOCKS))
        raise KeyError(f"등록되지 않은 물성 블록: {key}. 있는 것: {known}") from None


def list_blocks() -> list[BlockSpec]:
    """등록된 블록을 화면 순서로."""
    return sorted(_BLOCKS.values(), key=lambda spec: (spec.order, spec.key))


def clear() -> None:
    """테스트 전용."""
    _BLOCKS.clear()


def values_of(payload: Any) -> dict[str, Any]:
    """블록 payload 에서 `values` 를 꺼낸다. 없으면 빈 것."""
    return dict(payload.get("values", {})) if isinstance(payload, Mapping) else {}


def rows_of(payload: Any) -> list[dict[str, Any]]:
    """블록 payload 에서 `rows` 를 꺼낸다. 없으면 빈 것."""
    return list(payload.get("rows", [])) if isinstance(payload, Mapping) else []


def is_empty(payload: Any) -> bool:
    """담긴 것이 없는 블록인가. 빈 블록은 카드에 안 싣는다."""
    if not payload:
        return True
    return not values_of(payload) and not rows_of(payload)


def unknown(blocks: Mapping[str, Any]) -> tuple[str, ...]:
    """이 카드에 실렸는데 **레지스트리가 모르는** 블록.

    그 물성을 만든 코드가 사라졌거나 이름이 바뀌었다는 뜻이다. 조용히 넘기면
    덱에 그 물성만 빠진 채로 나가고, **덱은 멀쩡히 돈다.**

    전에는 카드를 솔버 양식으로 옮기다가(`card_kwargs`) 알아챘는데, 이제 옮기는
    단계가 없어졌다 — 렌더러가 블록을 직접 읽는다. 그래서 검사를 따로 둔다.
    """
    load_builtin()
    return tuple(key for key in blocks if key not in _BLOCKS)


def load_builtin() -> None:
    """내장 물성 블록을 등록한다.

    import 부작용에 기대지 않고 명시적으로 부른다 — `processing.load_builtin` 과
    같은 이유다. 워커와 테스트가 같은 함수를 부르면 "테스트에서는 되는데 워커에서는
    블록이 없다" 는 어긋남이 생기지 않는다.
    """
    from matcore.cards import hyperelastic, mechanical, viscoelastic  # noqa: F401


__all__ = [
    "BlockSpec",
    "CardError",
    "block",
    "clear",
    "is_empty",
    "list_blocks",
    "load_builtin",
    "register_block",
    "rows_of",
    "unknown",
    "values_of",
]
