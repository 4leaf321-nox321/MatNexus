"""지식 그래프의 **정의** — 무엇이 노드이고 무엇이 선인가.

TestScope 는 노드 종류와 선 종류를 이 자리에 코드로 적었다. MatNexus 는 그 정의가 이미
있다 — `shared/relations.py` 의 마디 21 · 관계 26(ADR 0028, 관계는 표를 안 바꾸고 FK·연결
표를 가리킨다). 그래서 여기는 **정의를 다시 적지 않고** 화면에 필요한 것만 얹는다: 층
(색 묶음) · 아이콘 · 상세 화면 주소 · 차례, 그리고 노드의 부제·키·상태·부서를 어느 열에서
읽나. 새 마디·관계는 `relations.py` 에 적으면 여기 자동으로 든다.

노드 id 는 `"<종류>:<식별자>"` — 물성 정의만 키 문자열(`property:mechanical.yield_strength`),
나머지는 uuid. 표가 다르면 식별자만으로는 종류를 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.shared import relations

#: 층 — 관계도 HTML(2026-09-17)의 세 기둥. 색 묶음과 설명에 쓴다.
LAYER_VOCAB = "vocabulary"  # 사전 · 기준정보
LAYER_CATALOG = "catalog"  # 문헌 · 장비 정의 (반입)
LAYER_OPERATIONS = "operations"  # 사내 측정 사슬 · 조직
LAYER_DEFINITION = "definition"  # 시험법 · 레시피 · 계산식 · 핸드북


@dataclass(frozen=True)
class NodeMeta:
    """마디 종류 하나에 얹는 화면 정보. `relations.EntityKind` 가 정본이고 이것은 덧옷이다."""

    slug: str
    layer: str
    icon: str
    detail_path: str | None = None
    """상세 화면 주소 서식 — `{id}` 가 식별자. `{id}` 없이 적으면 목록 화면."""
    sort_order: int = 100
    key_column: str | None = None
    """사람이 부르는 손잡이(재료 번호·자산번호·DOI). 없으면 None."""
    sublabel_columns: tuple[str, ...] = ()
    """아래 붙는 작은 글씨 — 여럿이면 ` · ` 로 잇는다."""
    status_column: str | None = None
    """상태 열. 없으면 `active`. `is_active`(bool)면 active/inactive 로 옮긴다."""
    workspace_column: str | None = None
    """소유 부서 FK 열 — 「부서별」 색에 쓴다."""

    @property
    def kind(self) -> relations.EntityKind:
        return relations.KINDS[self.slug]

    @property
    def label(self) -> str:
        return self.kind.label


NODE_META: tuple[NodeMeta, ...] = (
    # ── 사전 ──────────────────────────────────────────────────────────────
    NodeMeta(
        "property",
        LAYER_VOCAB,
        "atom",
        "/catalog",
        10,
        key_column="key",
        sublabel_columns=("si_unit",),
    ),
    NodeMeta("term", LAYER_VOCAB, "tags", "/vocabulary", 20, status_column="status"),
    # ── 문헌 · 장비 정의 ──────────────────────────────────────────────────
    NodeMeta(
        "catalog_material",
        LAYER_CATALOG,
        "book-marked",
        "/catalog/{id}",
        30,
        key_column="material_code",
        sublabel_columns=("manufacturer",),
    ),
    NodeMeta(
        "source",
        LAYER_CATALOG,
        "scroll-text",
        None,
        40,
        key_column="doi",
        sublabel_columns=("year",),
    ),
    NodeMeta(
        "instrument",
        LAYER_CATALOG,
        "microscope",
        "/metrology",
        50,
        sublabel_columns=("category",),
    ),
    # ── 사내 측정 사슬 ────────────────────────────────────────────────────
    NodeMeta(
        "material",
        LAYER_OPERATIONS,
        "layers",
        "/materials/{id}",
        60,
        key_column="code",
        sublabel_columns=("family", "grade"),
        workspace_column="owner_workspace_id",
    ),
    NodeMeta(
        "sample",
        LAYER_OPERATIONS,
        "package",
        None,
        70,
        key_column="lot_no",
        sublabel_columns=("manufacturer",),
        workspace_column="workspace_id",
    ),
    NodeMeta(
        "specimen",
        LAYER_OPERATIONS,
        "ruler",
        "/specimens/{id}",
        80,
        sublabel_columns=("orientation",),
        workspace_column="workspace_id",
    ),
    NodeMeta(
        "test_run",
        LAYER_OPERATIONS,
        "flask-conical",
        "/test-runs/{id}",
        90,
        sublabel_columns=("operator",),
        status_column="status",
        workspace_column="workspace_id",
    ),
    NodeMeta("processing_result", LAYER_OPERATIONS, "sigma", None, 100),
    NodeMeta(
        "property_card",
        LAYER_OPERATIONS,
        "id-card",
        "/cards",
        110,
        sublabel_columns=("orientation",),
        status_column="status",
    ),
    NodeMeta(
        "parameter_set",
        LAYER_OPERATIONS,
        "braces",
        None,
        120,
        sublabel_columns=("model",),
    ),
    NodeMeta(
        "commission",
        LAYER_OPERATIONS,
        "clipboard-list",
        "/commissions/{id}",
        130,
        key_column="seq",
        status_column="status",
        workspace_column="requester_workspace_id",
    ),
    NodeMeta("commission_item", LAYER_OPERATIONS, "list-checks", None, 140),
    NodeMeta(
        "equipment_unit",
        LAYER_OPERATIONS,
        "wrench",
        "/settings/equipment/{id}",
        150,
        key_column="asset_no",
        status_column="status",
        workspace_column="workspace_id",
    ),
    NodeMeta(
        "workspace",
        LAYER_OPERATIONS,
        "building-2",
        "/admin/workspaces",
        160,
        key_column="slug",
        status_column="is_active",
    ),
    # ── 정의 · 계산 · 핸드북 ──────────────────────────────────────────────
    NodeMeta(
        "test_type",
        LAYER_DEFINITION,
        "list-checks",
        "/settings/test-types",
        170,
        key_column="key",
        sublabel_columns=("abbr",),
        status_column="is_active",
    ),
    NodeMeta(
        "recipe",
        LAYER_DEFINITION,
        "workflow",
        "/settings/recipes",
        180,
        key_column="key",
        status_column="is_active",
        workspace_column="owner_workspace_id",
    ),
    NodeMeta(
        "formula",
        LAYER_DEFINITION,
        "function-square",
        "/admin/formulas",
        190,
        key_column="key",
        sublabel_columns=("kind",),
        status_column="enabled",
    ),
    NodeMeta(
        "guide_document",
        LAYER_DEFINITION,
        "book-open",
        "/guide",
        200,
        key_column="key",
        sublabel_columns=("topic",),
    ),
    NodeMeta("guide_section", LAYER_DEFINITION, "text", None, 210, key_column="key"),
)
NODE_META_BY_SLUG: dict[str, NodeMeta] = {one.slug: one for one in NODE_META}

# **레지스트리의 마디는 빠짐없이 덧옷을 입는다** — 여기 없는 마디는 그래프에 안 뜬다.
_missing = set(relations.KINDS) - set(NODE_META_BY_SLUG)
assert not _missing, (
    f"relations.KINDS 에 있는데 graph/model.py 에 없는 마디: {sorted(_missing)}"
)

#: 선 종류 — 레지스트리의 관계 중 실린 자리가 있는 것(`edge` 는 5단계 전까지 빈손).
EDGE_KINDS: tuple[relations.RelationType, ...] = tuple(
    one for one in relations.RELATIONS.values() if one.source.kind != "edge"
)
EDGE_KIND_BY_SLUG: dict[str, relations.RelationType] = {one.slug: one for one in EDGE_KINDS}


def node_id(type_slug: str, ident: object) -> str:
    return f"{type_slug}:{ident}"


def split_node_id(raw: str) -> tuple[str, str] | None:
    """`"<종류>:<식별자>"` → (종류, 식별자). 모르는 종류면 None."""
    if ":" not in raw:
        return None
    type_slug, ident = raw.split(":", 1)
    if type_slug not in NODE_META_BY_SLUG or not ident:
        return None
    return type_slug, ident
