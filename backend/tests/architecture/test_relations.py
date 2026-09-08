"""관계 레지스트리가 **진짜 스키마와 맞는지** 검사한다.

이것이 관계를 DB 표가 아니라 코드에 둔 이유다. `fk:samples.material_id` 를 표에
적어 두면 나중 마이그레이션이 그 열을 갈았을 때 조용히 썩고 질의를 돌릴 때에야
터진다. 여기 적으면 **그 마이그레이션을 만든 커밋에서** CI 가 잡는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Table

import app.all_models  # noqa: F401  — 표를 전부 메타데이터에 올린다
from app.database import Base
from app.shared import relations

#: 온톨로지에 들어오면 안 되는 표. 사람·감사·인증은 관계가 아니라 이력이다 —
#: 넣으면 그래프가 「누가 만들었나」 로 뒤덮인다.
FORBIDDEN = {
    "users",
    "audit_entries",
    "access_logs",
    "refresh_tokens",
    "personal_access_tokens",
}


def _table(name: str) -> Table:
    assert name in Base.metadata.tables, f"'{name}' 표가 없다"
    return Base.metadata.tables[name]


@pytest.mark.parametrize("kind", list(relations.KINDS.values()), ids=lambda one: one.slug)
def test_마디는_진짜_표를_가리킨다(kind: relations.EntityKind) -> None:
    table = _table(kind.table)
    assert kind.id_column in table.c, f"{kind.slug}: '{kind.id_column}' 열이 없다"
    for column in kind.name_columns:
        assert column in table.c, f"{kind.slug}: 이름 열 '{column}' 이 없다"


@pytest.mark.parametrize("kind", list(relations.KINDS.values()), ids=lambda one: one.slug)
def test_소프트삭제_표시가_실제와_맞는다(kind: relations.EntityKind) -> None:
    """어긋나면 **지운 재료가 그래프에 남는다** — 트래버설이 이 칸만 보고 거른다."""
    real = "deleted_at" in _table(kind.table).c
    assert kind.soft_delete == real, (
        f"{kind.slug}: soft_delete={kind.soft_delete} 인데 실제 deleted_at 은 {real}"
    )


def test_마디는_표마다_하나다() -> None:
    tables = [one.table for one in relations.KINDS.values()]
    assert len(tables) == len(set(tables)), "같은 표에 마디가 둘이면 트래버설이 갈린다"


@pytest.mark.parametrize("rel", list(relations.RELATIONS.values()), ids=lambda one: one.slug)
def test_관계의_양끝이_등록된_마디다(rel: relations.RelationType) -> None:
    assert rel.src in relations.KINDS, f"{rel.slug}: src '{rel.src}' 가 없다"
    assert rel.dst in relations.KINDS, f"{rel.slug}: dst '{rel.dst}' 가 없다"
    assert rel.label and rel.inverse_label, f"{rel.slug}: 양방향 말이 다 있어야 한다"
    assert rel.source.kind in relations.SOURCE_KINDS


@pytest.mark.parametrize("rel", list(relations.RELATIONS.values()), ids=lambda one: one.slug)
def test_외래키_관계는_진짜_외래키다(rel: relations.RelationType) -> None:
    """**`fk:` 는 FK 를 든 쪽이 src 다.** 이 규칙이 깨지면 방향이 뒤집힌다."""
    if rel.source.kind != "fk":
        pytest.skip("외래키 관계가 아니다")

    src_kind = relations.KINDS[rel.src]
    dst_kind = relations.KINDS[rel.dst]
    assert rel.source.table == src_kind.table, (
        f"{rel.slug}: FK 를 든 표는 src('{src_kind.table}') 여야 하는데 "
        f"'{rel.source.table}' 이라고 적혀 있다"
    )

    column = _table(rel.source.table).c[rel.source.src_column]
    targets = {(one.column.table.name, one.column.name) for one in column.foreign_keys}
    assert targets, f"{rel.slug}: '{rel.source}' 에 외래키가 없다"
    assert (dst_kind.table, dst_kind.id_column) in targets, (
        f"{rel.slug}: '{rel.source}' 가 {targets} 를 가리키는데 "
        f"dst 는 {dst_kind.table}.{dst_kind.id_column} 이다"
    )


@pytest.mark.parametrize("rel", list(relations.RELATIONS.values()), ids=lambda one: one.slug)
def test_연결표_관계는_두_열을_다_가진다(rel: relations.RelationType) -> None:
    if rel.source.kind != "table":
        pytest.skip("연결 표 관계가 아니다")

    table = _table(rel.source.table)
    for side, column_name, kind_slug in (
        ("src", rel.source.src_column, rel.src),
        ("dst", rel.source.dst_column, rel.dst),
    ):
        assert column_name in table.c, f"{rel.slug}: {side} 열 '{column_name}' 이 없다"
        kind = relations.KINDS[kind_slug]
        targets = {
            (one.column.table.name, one.column.name)
            for one in table.c[column_name].foreign_keys
        }
        # **FK 가 없을 수 있다.** `property_links.property_key` 는 일부러 안 걸었다
        # (이관이 정의를 지웠다 넣으면 매핑이 함께 지워진다). 걸려 있으면 맞아야 한다.
        if targets:
            assert (kind.table, kind.id_column) in targets, (
                f"{rel.slug}: {side} 열이 {targets} 를 가리키는데 "
                f"{kind.table}.{kind.id_column} 이어야 한다"
            )


def test_사람과_감사는_온톨로지가_아니다() -> None:
    """넣으면 그래프가 「누가 만들었나」 로 뒤덮여 정작 물어본 길이 묻힌다."""
    used = {one.table for one in relations.KINDS.values()}
    used |= {one.source.table for one in relations.RELATIONS.values() if one.source.table}
    assert not (used & FORBIDDEN), f"온톨로지에 들어오면 안 되는 표: {used & FORBIDDEN}"


def test_이행성은_자기를_가리키는_관계에만_붙는다() -> None:
    """`a→b`, `b→c` 면 `a→c` 라는 말은 양끝 종류가 같을 때만 뜻이 있다."""
    for one in relations.RELATIONS.values():
        if one.transitive:
            assert one.src == one.dst, f"{one.slug}: 이행성인데 양끝 종류가 다르다"


def test_설명은_MCP_가_실을_수_있는_모양이다() -> None:
    shape = relations.describe()
    assert len(shape["kinds"]) == len(relations.KINDS)
    assert len(shape["relations"]) == len(relations.RELATIONS)
    for row in shape["relations"]:
        assert row["source"], "관계가 어디 실려 있는지 말하지 않으면 AI 가 못 따라간다"
