"""덱 준비도 — **이 재료로 이 솔버 형식이 나오나 · 안 나오면 무엇이 없나 · 어디서 채우나.**

연결된 플랫폼은 재료와 솔버만 안다. 전에는 카드를 열어 `available_formats` 를 봐야
「나오나」 를 알았고, 「왜 안 나오나 · 어디서 채우나」 는 렌더 실패 메시지와 사람의
머릿속에만 있었다(2026-09-16, [계획] 온톨로지 고도화 §2-A).

## 관계 셋을 코드에서 읽는다

    형식 → 필요한 블록      `Renderer.needs`            (덱 정의 · 코드 렌더러)
    시험 종류 → 내는 블록   `BlockSpec.from_tests`      (블록 레지스트리)
    문헌 물성 → 채우는 자리  `Produced.property_key`     (블록의 값 선언)

셋 다 이미 코드에 있던 사실이다 — 표를 새로 만들지 않고 **질의할 수 있게 한 번 더
읽는다**(ADR 0028 의 방식). 온톨로지 지도(`GET /api/ontology`)의 `deck_requirements`
가 이 정적 관계를 그대로 싣고(`shared/deckmap`), 여기는 재료 하나에 그것을 대어 본다.

## 판정은 `export.missing_for` 와 같은 규칙이다

「낼 수 있다」 고 해 놓고 렌더러가 거절하면 이 도구는 거짓말이다. 그래서 `Need` 를
같은 순서로 같은 조건으로 본다 — 다만 사람이 읽는 문장이 아니라 **블록·값 단위**로
남겨, 「어디서 채우나」 를 블록마다 붙일 수 있게 한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogLink, CatalogValue
from app.modules.fitting.models import PropertyCard
from app.modules.tests.models import TestType
from matcore import cards, export


@dataclass(frozen=True)
class TestWay:
    key: str
    label: str
    test_type_ids: tuple[str, ...]
    """이 키로 등록된 시험 종류(부서마다 있을 수 있다). 비어 있으면 아직 만든 부서가 없다."""


@dataclass(frozen=True)
class CatalogWay:
    property_keys: tuple[str, ...]
    values_available: int
    """이 재료에 이어진 문헌 재료(`catalog_links`)가 가진, 그 자리에 들어갈 값의 수
    (등급 4 — 계산·추정 — 는 뺀다). 0 이면 「채택할 문헌값이 없다」."""


@dataclass(frozen=True)
class MissingBlock:
    block: str
    label: str
    what: tuple[str, ...]
    """빠진 것 — 블록 전체 · 값 이름 · 「표 N줄 이상」. `export.missing_for` 와 같은 말."""
    tests: tuple[TestWay, ...]
    catalog: CatalogWay | None
    declarable_values: tuple[str, ...]
    """사람이 **적어 넣을 수 있는 값**(문헌 물성 키를 가진 스칼라). 비어 있으면 표로만
    채우는 블록이다 — 소성 표는 적는 것이 아니라 시험에서 나온다."""


@dataclass(frozen=True)
class FormatReadiness:
    key: str
    label: str
    extension: str
    ready: bool
    card_id: str | None
    """나오면 그 카드(확정된 것 먼저). 안 나오면 가장 가까운 카드 — 빠진 것이 가장 적은."""
    card_label: str | None
    missing: tuple[MissingBlock, ...]


@dataclass(frozen=True)
class Readiness:
    material_id: str
    card_count: int
    formats: tuple[FormatReadiness, ...]
    note: str = ""
    """카드가 하나도 없을 때 사람에게 할 말."""


@dataclass
class _Gap:
    block: str
    what: list[str] = field(default_factory=list)


def _gaps(deck: export.Deck, target: export.Renderer) -> list[_Gap]:
    """`export.missing_for` 와 **같은 판정**, 블록 단위로 묶어서."""
    out: dict[str, _Gap] = {}

    def gap(block: str) -> _Gap:
        return out.setdefault(block, _Gap(block=block))

    for need in target.needs:
        if need.optional:
            continue
        if not deck.has(need.block):
            gap(need.block).what.append(_label(need.block))
            continue
        values = deck.values(need.block)
        for key in need.values:
            if values.get(key) is None:
                gap(need.block).what.append(_label(need.block, key))
        if need.rows_min and len(deck.rows(need.block)) < need.rows_min:
            gap(need.block).what.append(f"{_label(need.block)}(표 {need.rows_min}줄 이상)")
        for key, floor in need.at_least:
            found = values.get(key)
            if found is None or float(found) < floor:
                gap(need.block).what.append(f"{_label(need.block, key)} {floor:g} 이상")
    return list(out.values())


def _label(block: str, key: str | None = None) -> str:
    try:
        spec = cards.block(block)
    except KeyError:
        return f"{block}.{key}" if key else block
    if key is None:
        return spec.label
    for item in (*spec.produces, *spec.rows):
        if item.key == key:
            return f"{spec.label} · {item.label}"
    return f"{spec.label} · {key}"


def _ways(
    db: Session, material_id: uuid.UUID, block_key: str
) -> tuple[tuple[TestWay, ...], CatalogWay | None, tuple[str, ...]]:
    try:
        spec = cards.block(block_key)
    except KeyError:
        return (), None, ()

    tests: list[TestWay] = []
    for test_key in spec.from_tests:
        rows = list(
            db.execute(
                select(TestType.id, TestType.label)
                .where(TestType.key == test_key, TestType.is_active.is_(True))
                .order_by(TestType.label)
            )
        )
        tests.append(
            TestWay(
                key=test_key,
                label=rows[0][1] if rows else test_key,
                test_type_ids=tuple(str(row[0]) for row in rows),
            )
        )

    keys = tuple(item.property_key for item in spec.produces if item.property_key is not None)
    catalog: CatalogWay | None = None
    if keys:
        linked = select(CatalogLink.catalog_material_id).where(
            CatalogLink.material_id == material_id
        )
        available = db.scalar(
            select(func.count(CatalogValue.id))
            .where(CatalogValue.material_id.in_(linked))
            .where(CatalogValue.property_key.in_(keys))
            .where(CatalogValue.quality_tier < 4)
            .where(CatalogValue.value_num.is_not(None))
        )
        catalog = CatalogWay(property_keys=keys, values_available=int(available or 0))

    return tuple(tests), catalog, keys


def assess(
    db: Session,
    *,
    material_id: uuid.UUID,
    decks: list[tuple[PropertyCard, export.Deck]],
    renderers: list[export.Renderer],
) -> Readiness:
    """재료의 카드들(확정된 것 먼저)을 형식마다 대어 본다.

    `decks` 는 부르는 쪽이 만든다 — 가시성과 덱 구성(`_deck_for_card`)은 라우터의 것이고,
    여기는 판정만 한다. 카드가 없어도 형식 목록은 낸다: 「전부 안 나온다, 이것들이
    없어서」 가 「카드가 없다」 보다 사람에게 유용하다.
    """
    cards.load_builtin()
    formats: list[FormatReadiness] = []
    for target in renderers:
        if target.key == "json":
            continue
        best: tuple[PropertyCard, list[_Gap]] | None = None
        for card, deck in decks:
            gaps = _gaps(deck, target)
            if not gaps:
                best = (card, [])
                break
            if best is None or len(gaps) < len(best[1]):
                best = (card, gaps)
        if best is None:
            # 카드가 없다 — 빈 덱에 대어 무엇이 필요한지만 말한다.
            empty = export.Deck(name="NONE", solver_id=1, blocks={}, provenance=())
            gaps = _gaps(empty, target)
            card_id = card_label = None
        else:
            card_id, card_label = str(best[0].id), best[0].label
            gaps = best[1]
        missing = []
        for one in gaps:
            tests, catalog, declarable = _ways(db, material_id, one.block)
            missing.append(
                MissingBlock(
                    block=one.block,
                    label=_label(one.block),
                    what=tuple(one.what),
                    tests=tests,
                    catalog=catalog,
                    declarable_values=declarable,
                )
            )
        formats.append(
            FormatReadiness(
                key=target.key,
                label=target.label,
                extension=target.extension,
                ready=not gaps,
                card_id=card_id,
                card_label=card_label,
                missing=tuple(missing),
            )
        )
    note = (
        "" if decks else "이 재료에는 카드가 없습니다 — 형식마다 무엇이 필요한지만 적었습니다."
    )
    return Readiness(
        material_id=str(material_id), card_count=len(decks), formats=tuple(formats), note=note
    )
