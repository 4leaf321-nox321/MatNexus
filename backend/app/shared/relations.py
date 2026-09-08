"""관계 레지스트리 — **표를 안 바꾸고 온톨로지를 얻는다.**

3단계다. 1단계가 이름을 풀고(`property_names`), 2단계가 값을 걸었고
(`property_search`), 여기는 **무엇이 무엇과 어떤 사이인가**를 데이터로 적는다.
4단계 트래버설(`graph`)이 이 표만 보고 길을 찾는다.

## 열쇠는 `source` 칸이다

관계가 **어디에 실려 있나**를 함께 적는다:

    fk:samples.material_id                     이미 있는 외래키를 설명만 한다
    table:instrument_capabilities(...)         관계 전용 표가 이미 있다
    edge                                       일반 관계 표에 산다(5단계)

이 칸 덕분에 **기존 FK 를 옮기지 않는다.** 재료↔시료는 이미 `samples.material_id`
가 들고 있고, 그것을 「`derived_from` 이라는 뜻의 관계」라고 가리키기만 하면 된다.
관계를 데이터로 만들자고 잘 도는 표를 다시 쓰는 것은 온톨로지가 아니라 이관이다.

## 왜 DB 표가 아니라 코드인가

계획서는 RA 처럼 `relation_types` **표**를 두자고 적었다. 코드로 바꿨다 —

`source` 가 가리키는 것이 **열 이름**이기 때문이다. 표에 적어 두면 나중
마이그레이션이 `samples.material_id` 를 갈았을 때 그 행은 조용히 썩고, **질의를
돌릴 때에야** 터진다. 코드에 적으면 `tests/architecture/test_relations.py` 가
SQLAlchemy 메타데이터와 맞대 보고 **CI 에서** 잡는다.

이 저장소에 이미 같은 판단이 있다 — 기준정보 `Binding(slug, field, column, …)` 도
「어느 표 어느 열이 이 축을 쓴다」를 코드로 적고, 어긋남 검사가 그것을 센다.

## 첫 세트는 뜻 있는 것만

사람·부서·감사 FK 는 **온톨로지가 아니다.** 넣으면 그래프가 「누가 만들었나」 로
뒤덮여 정작 「이 물성을 어느 장비로 쟀나」 가 묻힌다(RA 가 보고서 본문을 그래프에
안 넣은 것과 같은 판단). 조직은 하나만 들어온다 — **장비를 어느 조직이 갖고 있나**
는 사람이 실제로 묻는 질문이라서다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: `source` 가 될 수 있는 것.
SOURCE_KINDS = ("fk", "table", "edge")


@dataclass(frozen=True)
class Source:
    """관계가 실려 있는 자리.

    `fk` 는 **FK 를 든 쪽이 `src`** 다 — `samples.material_id` 면 시료가 src,
    재료가 dst. 이 규칙을 지키면 트래버설이 방향을 유추할 필요가 없다.
    """

    kind: str
    table: str = ""
    src_column: str = ""
    dst_column: str = ""

    def __str__(self) -> str:
        if self.kind == "edge":
            return "edge"
        if self.kind == "fk":
            return f"fk:{self.table}.{self.src_column}"
        return f"table:{self.table}({self.src_column},{self.dst_column})"


def fk(table: str, column: str) -> Source:
    """이미 있는 외래키를 가리킨다. **`table` 이 FK 를 든 쪽이다.**"""
    return Source(kind="fk", table=table, src_column=column)


def via(table: str, src_column: str, dst_column: str) -> Source:
    """관계 전용 표(연결 표)를 가리킨다."""
    return Source(kind="table", table=table, src_column=src_column, dst_column=dst_column)


#: 5단계의 일반 관계 표. **아직 표가 없다** — 여기 쓰는 관계는 그때 등록한다.
EDGE = Source(kind="edge")


@dataclass(frozen=True)
class EntityKind:
    """그래프의 마디. **표 하나에 하나씩.**"""

    slug: str
    label: str
    table: str
    module: str
    """어느 모듈의 것인가. AI 가 「이걸 어느 화면에서 보나」 를 알아야 한다."""

    id_column: str = "id"
    """식별자 열. **`property` 는 `key` 다** — FK 들이 `catalog_definitions.key`
    를 가리키므로 `id` 로 이으면 아무것도 안 걸린다."""

    name_columns: tuple[str, ...] = ("name",)
    """사람에게 보여 줄 이름. 여럿이면 이어 붙인다 — 장비 정의는 이름 열이 없고
    `vendor` + `model` 이 그 노릇을 한다."""

    soft_delete: bool = False
    """`deleted_at` 을 쓰나. 안 보면 **지운 재료가 그래프에 남는다.**"""


@dataclass(frozen=True)
class RelationType:
    """마디와 마디 사이. **`src → dst` 방향으로 `label` 을 읽는다.**"""

    slug: str
    label: str
    inverse_label: str
    src: str
    dst: str
    source: Source

    directed: bool = True
    transitive: bool = False
    """`a→b`, `b→c` 면 `a→c` 인가. 조직 상하가 그렇다 — 사업부 아래 전부를 묻는다."""
    acyclic: bool = False
    """고리가 없나. 자기를 가리키는 관계(조직 상하)에만 뜻이 있다."""
    note: str = ""


KINDS: dict[str, EntityKind] = {
    one.slug: one
    for one in (
        EntityKind(
            slug="material",
            label="재료",
            table="materials",
            module="materials",
            name_columns=("record_name",),
            soft_delete=True,
        ),
        EntityKind(
            slug="sample",
            label="시료",
            table="samples",
            module="materials",
            name_columns=("record_name",),
            soft_delete=True,
        ),
        EntityKind(
            slug="specimen",
            label="시편",
            table="specimens",
            module="materials",
            name_columns=("record_name",),
            soft_delete=True,
        ),
        EntityKind(
            slug="test_run",
            label="시험",
            table="test_runs",
            module="tests",
            name_columns=("record_name",),
            soft_delete=True,
        ),
        EntityKind(
            slug="test_type",
            label="시험법",
            table="test_types",
            module="tests",
            name_columns=("label",),
            soft_delete=True,
        ),
        EntityKind(
            slug="property_card",
            label="물성카드",
            table="property_cards",
            module="fitting",
            name_columns=("label",),
        ),
        EntityKind(
            slug="processing_result",
            label="처리결과",
            table="processing_results",
            module="processing",
            name_columns=("recipe_label",),
        ),
        EntityKind(
            slug="property",
            label="문헌 물성 정의",
            table="catalog_definitions",
            module="catalog",
            id_column="key",
            name_columns=("name",),
        ),
        EntityKind(
            slug="catalog_material",
            label="문헌 재료",
            table="catalog_materials",
            module="catalog",
            name_columns=("name",),
        ),
        EntityKind(
            slug="instrument",
            label="장비 정의",
            table="instruments",
            module="metrology",
            name_columns=("vendor", "model"),
        ),
        EntityKind(
            slug="equipment_unit",
            label="보유 장비",
            table="equipment_units",
            module="equipment",
            name_columns=("name",),
        ),
        EntityKind(
            slug="term",
            label="기준정보 값",
            table="vocabulary_terms",
            module="vocabulary",
            name_columns=("value",),
        ),
        EntityKind(
            slug="workspace",
            label="조직",
            table="workspaces",
            module="workspaces",
            name_columns=("name",),
        ),
    )
}


RELATIONS: dict[str, RelationType] = {
    one.slug: one
    for one in (
        # ── 재료에서 시험까지. 「이 값이 어느 재료에서 나왔나」 의 사슬이다.
        RelationType(
            slug="derived_from",
            label="이 시료가 나온 재료",
            inverse_label="이 재료에서 나온 시료",
            src="sample",
            dst="material",
            source=fk("samples", "material_id"),
        ),
        RelationType(
            slug="part_of",
            label="이 시편을 자른 시료",
            inverse_label="이 시료에서 자른 시편",
            src="specimen",
            dst="sample",
            source=fk("specimens", "sample_id"),
        ),
        RelationType(
            slug="tested",
            label="이 시험이 잰 시편",
            inverse_label="이 시편을 잰 시험",
            src="test_run",
            dst="specimen",
            source=fk("test_runs", "specimen_id"),
            note="계획서의 `tested_by` — FK 를 든 쪽을 src 로 두는 규칙에 맞춰 이름을 바꿨다.",
        ),
        RelationType(
            slug="follows",
            label="이 시험이 따른 시험법",
            inverse_label="이 시험법으로 돌린 시험",
            src="test_run",
            dst="test_type",
            source=fk("test_runs", "test_type_id"),
        ),
        RelationType(
            slug="processed_from",
            label="이 결과가 나온 시험",
            inverse_label="이 시험의 처리결과",
            src="processing_result",
            dst="test_run",
            source=fk("processing_results", "test_run_id"),
        ),
        RelationType(
            slug="card_of",
            label="이 카드의 재료",
            inverse_label="이 재료의 물성카드",
            src="property_card",
            dst="material",
            source=fk("property_cards", "material_id"),
        ),
        # ── 물성과 장비. 「이 물성을 재려면 어느 장비인가」 가 여기로 답해진다.
        RelationType(
            slug="measured_by",
            label="이 물성을 재는 장비",
            inverse_label="이 장비가 재는 물성",
            src="property",
            dst="instrument",
            source=via("instrument_capabilities", "property_key", "instrument_id"),
        ),
        RelationType(
            slug="unit_of",
            label="이 개체의 장비 정의",
            inverse_label="이 장비 정의의 보유 개체",
            src="equipment_unit",
            dst="instrument",
            source=fk("equipment_units", "instrument_id"),
        ),
        RelationType(
            slug="held_by",
            label="이 장비를 가진 조직",
            inverse_label="이 조직이 가진 장비",
            src="equipment_unit",
            dst="workspace",
            source=fk("equipment_units", "workspace_id"),
            note="온톨로지에 넣는 유일한 조직 관계 — "
            "「우리 사업부에 이 장비가 있나」 는 사람이 실제로 묻는다.",
        ),
        RelationType(
            slug="child_of",
            label="이 조직의 상위",
            inverse_label="이 조직의 하위",
            src="workspace",
            dst="workspace",
            source=fk("workspaces", "parent_id"),
            transitive=True,
            acyclic=True,
            note="사업부 아래 전부를 한 번에 묻기 위해 이행성을 켠다.",
        ),
        # ── 사내와 문헌. 1단계가 만든 표가 여기 들어온다.
        RelationType(
            slug="links_to",
            label="이 사내 재료와 이은 문헌 재료",
            inverse_label="이 문헌 재료와 이은 사내 재료",
            src="material",
            dst="catalog_material",
            source=via("catalog_links", "material_id", "catalog_material_id"),
        ),
        RelationType(
            slug="same_as",
            label="같은 뜻의 사내 물성 항목",
            inverse_label="이 항목에 해당하는 문헌 물성",
            src="property",
            dst="term",
            source=via("property_links", "property_key", "term_id"),
            directed=False,
            note="1단계가 만든 표. ADR 0027 이 미뤄 둔 매핑이다.",
        ),
    )
}


def kind_of_table(table: str) -> EntityKind | None:
    """표 이름으로 마디 종류를 찾는다. 시험이 `source` 를 검사할 때 쓴다."""
    for one in KINDS.values():
        if one.table == table:
            return one
    return None


def relations_of(kind: str) -> list[RelationType]:
    """이 종류가 걸린 관계 전부 — 어느 쪽이든."""
    return [one for one in RELATIONS.values() if kind in (one.src, one.dst)]


def describe() -> dict[str, Any]:
    """MCP `get_ontology` 가 그대로 실어 보낼 모양(6단계).

    **AI 가 스키마를 읽을 수 있어야 길을 찾는다** — 사람은 화면에서 링크를 눌러
    다니면 되지만 AI 에게는 이 표가 지도의 전부다.
    """
    return {
        "kinds": [
            {"slug": one.slug, "label": one.label, "module": one.module}
            for one in KINDS.values()
        ],
        "relations": [
            {
                "slug": one.slug,
                "label": one.label,
                "inverse_label": one.inverse_label,
                "src": one.src,
                "dst": one.dst,
                "directed": one.directed,
                "transitive": one.transitive,
                "source": str(one.source),
                "note": one.note,
            }
            for one in RELATIONS.values()
        ],
    }
