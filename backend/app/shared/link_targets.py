"""바깥 객체를 **무엇에 이을 수 있나** — 기준정보 값 · 물성 · 물성군 · 물성 분야(ADR 0063).

SP 코어 객체를 잇는 자리(`modules/sp_core`)가 맞은편 목록을 여기서 받는다. 기준정보(값 ·
별칭)와 문헌 물성(정의 · 별칭 · 분류)을 한자리에서 맞대 보는 일이라 어느 한 모듈의 것이
아니다 — `declared_slots` 와 같은 판단이다. 모듈끼리는 `models` 말고 직접 안 부른다
(`tests/architecture`).

**쓰는 중인 것만** 낸다 — 폐기한 물성 · 분류, 사용 중지한 기준정보 값은 잇는 대상이 아니다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import PropertyAlias
from app.modules.catalog.taxonomy_models import PropertyField, PropertyGroup
from app.modules.vocabulary.models import Vocabulary, VocabularyAlias, VocabularyTerm
from app.shared.errors import AppError, NotFound
from app.shared.text import compare_key

#: 대상 종류 → 사람이 읽는 이름.
TARGETS: dict[str, str] = {
    "term": "기준정보 값",
    "property": "물성",
    "property_group": "물성군",
    "property_field": "물성 분야",
}


@dataclass(frozen=True)
class Target:
    """맞은편 하나."""

    kind: str
    ref: str
    """연결이 드는 값 — 기준정보 값은 uuid, 물성 · 물성군 · 분야는 키."""
    label: str
    key: str | None = None
    """키로도 맞추는 대상(물성 · 물성군 · 분야)."""
    names: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    """(비교키, 어디서 — `name` · `alias`)."""


def bad_kind(kind: str) -> AppError:
    return AppError(
        "MNX-SPCORE-0005",
        f"대상 종류는 {', '.join(TARGETS)} 중 하나입니다: {kind!r}",
        status=422,
    )


def pool(db: Session, kind: str, vocabulary: str | None = None) -> list[Target]:
    """맞은편 전부. `term` 이면 어느 기준정보 축인지(`vocabulary`)가 있어야 한다."""
    if kind == "term":
        if not vocabulary:
            raise AppError(
                "MNX-SPCORE-0005",
                "기준정보 값과 견주려면 어느 축인지(vocabulary — 예: manufacturer)를 주세요.",
                status=422,
            )
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == vocabulary))
        if axis is None:
            raise NotFound("MNX-SPCORE-0006", f"그런 기준정보 축이 없습니다: {vocabulary}")
        terms = list(
            db.scalars(
                select(VocabularyTerm).where(
                    VocabularyTerm.vocabulary_id == axis.id, VocabularyTerm.status == "active"
                )
            )
        )
        aliases: dict[uuid.UUID, list[str]] = defaultdict(list)
        for alias in db.scalars(
            select(VocabularyAlias).where(VocabularyAlias.vocabulary_id == axis.id)
        ):
            aliases[alias.term_id].append(alias.normalized)
        return [
            Target(
                kind="term",
                ref=str(term.id),
                label=term.value,
                names=(
                    (term.normalized, "name"),
                    *((one, "alias") for one in aliases.get(term.id, [])),
                ),
            )
            for term in terms
        ]
    if kind == "property":
        rows = list(
            db.scalars(
                select(CatalogDefinition).where(CatalogDefinition.deprecated_at.is_(None))
            )
        )
        by_key: dict[str, list[str]] = defaultdict(list)
        for entry in db.scalars(select(PropertyAlias)):
            by_key[entry.property_key].append(entry.normalized)
        return [
            Target(
                kind="property",
                ref=row.key,
                label=row.name,
                key=row.key,
                names=(
                    (compare_key(row.name), "name"),
                    *((one, "alias") for one in by_key.get(row.key, [])),
                ),
            )
            for row in rows
        ]
    if kind in ("property_group", "property_field"):
        model: Any = PropertyGroup if kind == "property_group" else PropertyField
        return [
            Target(
                kind=kind,
                ref=row.key,
                label=row.name,
                key=row.key,
                names=((compare_key(row.name), "name"),),
            )
            for row in db.scalars(select(model).where(model.retired_at.is_(None)))
        ]
    raise bad_kind(kind)


def label_of(db: Session, kind: str, ref: str) -> str | None:
    """대상이 있으면 그 이름 — 없으면 None(잇기 전에 본다)."""
    if kind == "term":
        try:
            term_id = uuid.UUID(ref)
        except ValueError:
            return None
        term = db.get(VocabularyTerm, term_id)
        return term.value if term is not None else None
    if kind == "property":
        row = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == ref))
        return row.name if row is not None else None
    if kind in ("property_group", "property_field"):
        model: Any = PropertyGroup if kind == "property_group" else PropertyField
        found = db.scalar(select(model).where(model.key == ref))
        return str(found.name) if found is not None else None
    raise bad_kind(kind)
