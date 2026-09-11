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


# ── 판정표 — **온톨로지에 안 들어간 것에도 사유가 있다** ────────────────────
#
# 이 저장소는 예외를 사유와 함께 아키텍처 시험에 적는다(`test_boundaries.py` 의
# `FRONTEND_ONLY`). 같은 자리에 온톨로지의 **빈칸**을 적어 둔다.
#
# 왜 필요한가 (실측 2026-09-10): 출처와 파라미터 벌을 마디로 올린 것은 문헌
# 자료를 훑다가 「어? 이건 못 묻네」 하고 눈에 걸려서였다. 그렇게 찾으면 **눈에
# 안 걸린 것은 영영 안 찾는다.** 반대로 스키마를 대조하면 표 63개 · FK 133개가
# 초 단위로 후보를 내놓는다 — 그날 그렇게 대조해서 관계 셋(`adopted` ·
# `fitted_from` · `listed_in`)이 빠져 있던 것을 바로 찾았다.
#
# 그래서 규칙은 하나다: **모든 표는 셋 중 하나여야 한다** — 마디이거나, 관계를
# 나르거나, 여기에 사유가 적혀 있거나. 새 표가 생기면 시험이 울고, 그 커밋에서
# 「이건 온톨로지에 넣을 것인가」 를 묻게 된다. 지금은 아무도 안 묻는다.

#: 사람·권한·감사. 레지스트리 머리말의 판단 그대로다.
사람 = "사람·권한·감사 — 넣으면 그래프가 「누가 만들었나」 로 뒤덮여 물어본 길이 묻힌다"
#: 알림.
알림 = "알림은 사람에게 보내는 것이다 — 물성과 물성 사이가 아니다"
#: 기준정보를 **운영하는** 표들. 용어 자체는 `term` 마디로 이미 서 있다.
기준정보 = "기준정보를 운영하는 표 — 용어 자체는 `term` 마디이고 이름 풀기는 1단계가 한다"
#: 무엇을 어떻게 다루나. 자료가 아니라 설정이다.
설정 = "다루는 방법(형식·필드·단위계) — 자료가 아니라 설정이라 마디로 둘 것이 없다"
#: 언제 무엇이 돌았나.
이력 = "일감·이력 — 「언제 무엇이 돌았나」 이지 「무엇이 무엇인가」 가 아니다"
#: VOC — 사람이 사람에게 낸 제보와 그 절차.
제보 = "제보와 그 절차(등록·접수·해결) — 사람 사이에 오가는 말이지 물성 사이가 아니다"

#: 마디도 나르개도 아닌 표와 **왜 아닌가**.
EXCLUDED_TABLES: dict[str, str] = {
    "access_logs": 사람,
    "audit_entries": 사람,
    "personal_access_tokens": 사람,
    "refresh_tokens": 사람,
    "users": 사람,
    "workspace_members": 사람,
    "notice_reads": 알림,
    "notices": 알림,
    "notification_rule_states": 알림,
    "notification_rules": 알림,
    "notifications": 알림,
    "bom_aliases": 기준정보,
    "property_aliases": 기준정보,
    "voc_events": 제보,
    "voc_items": 제보,
    "vocabularies": 기준정보,
    "vocabulary_aliases": 기준정보,
    "vocabulary_dismissals": 기준정보,
    "vocabulary_drift_checks": 기준정보,
    "vocabulary_merges": 기준정보,
    "export_profiles": 설정,
    "format_profiles": 설정,
    "specimen_fields": 설정,
    "test_channels": 설정,
    "test_condition_fields": 설정,
    "unit_systems": 설정,
    "pipeline_connectors": 설정,
    "guide_revisions": 이력,
    "jobs": 이력,
    "pipeline_inbox_items": 이력,
    # ── 자료를 들고 있지만 **마디가 아닌 것.** 마디로 두면 그래프가 이것으로
    #    뒤덮인다 — 어느 것이든 「무엇에 딸렸나」 가 이미 답이라서, 그 마디를
    #    집으면 도구가 함께 준다.
    "curves": (
        "시험에 딸린 원곡선(366) — 마디로 두면 그래프가 곡선으로 뒤덮인다."
        " `get_test_run` 이 준다"
    ),
    "test_summaries": "시험의 요약값(2,564) — 시험 마디에 딸린 칸이다. `get_test_run` 이 준다",
    "master_curves": "처리 결과의 중간 산출물(17) — 카드의 `viscoelastic` 블록으로 닿는다",
    "prony_fits": "마스터커브 적합 결과(17) — 같은 블록으로 닿는다(`list_card_blocks`)",
    "group_results": "여러 시험을 묶은 처리 결과(14) — 처리결과 마디에 딸린다",
    "ensemble_results": "묶음 처리의 앙상블(1) — 같다",
    "guide_assets": "핸드북에 붙은 그림·파일(75) — 절 마디를 집으면 본문과 함께 온다",
    "equipment_parts": "보유 장비의 부품(4) — 장비 마디에 딸린 목록이다",
    "material_uses": (
        "재료의 용도 줄(34) — 재료의 칸이다. 용도로 찾는 것은 `search_materials` 의 일"
    ),
}

#: **막힌 물음이 있는데 아직 안 정한 것.** 「모른다」 를 적는 자리가 아니라
#: 「이 물음이 지금 막혀 있다」 를 적는 자리다 — 늘어나면 그 자체가 신호다.
PENDING_TABLES: dict[str, str] = {
    "equipment_calibrations": (
        "「이 장비의 교정이 언제까지 유효한가」 — AI 가 실제로 물었고 못 찾았다"
        "(실측 2026-09-10). 지금은 보유 장비가 6대·교정 4건이라 물어도 거의 빈손이다"
    ),
    "processing_recipes": (
        "「이 레시피로 돌린 결과들」 — 부서가 합의해 둔 단계 묶음이라 물음이 선다."
        " 목록은 `list_recipes` 로 닿지만 결과에서 거슬러 오를 길이 없다"
    ),
    "workbench_items": "워크벤치는 사람의 작업 공간이다 — 물성 그래프에 넣을 것인지 안 정했다",
    "workbench_runs": (
        "같다 — 넣는다면 「이 재료를 누가 어디서 만졌나」 에 가깝고, 그것은 사람 쪽이다"
    ),
}

#: **마디끼리 잇는 FK 인데 관계가 아닌 것.** 여기 없으면 시험이 운다 —
#: 「이을 수 있는데 안 이었다」 가 조용히 남지 않게 한다.
축 = (
    "기준정보 축은 재료의 **칸**이다 — 관계로 두면 재료마다 갈래가 넷씩 뻗어"
    " 그래프가 분류로 뒤덮인다"
)
소유 = (
    "소유 조직은 권한이지 물성이 아니다 —"
    " 가시 범위(`graph.visible_ids`)가 이미 그것으로 거른다"
)

EXCLUDED_FKS: dict[tuple[str, str], str] = {
    ("equipment_units", "instrument_term_id"): 축,
    ("equipment_units", "lab_term_id"): 축,
    ("equipment_units", "manufacturer_term_id"): 축,
    ("equipment_units", "type_term_id"): 축,
    ("materials", "category_term_id"): 축,
    ("materials", "family_term_id"): 축,
    ("materials", "grade_term_id"): 축,
    ("samples", "distributor_term_id"): 축,
    ("samples", "manufacturer_term_id"): 축,
    ("samples", "primary_vendor_term_id"): 축,
    ("samples", "sales_type_term_id"): 축,
    ("specimens", "standard_term_id"): 축,
    ("test_runs", "division_term_id"): 축,
    ("test_runs", "instrument_term_id"): 축,
    ("materials", "owner_workspace_id"): 소유,
    ("samples", "workspace_id"): 소유,
    ("specimens", "workspace_id"): 소유,
    ("test_runs", "workspace_id"): 소유,
    ("test_types", "owner_workspace_id"): 소유,
    # 용어끼리의 상하(등급 172개가 분류 아래에 선다). **들머리가 없어서 지금은
    # 뜻이 없다** — 재료에서 용어로 가는 길을 위의 `축` 판단으로 일부러 안 냈으니,
    # 용어 상하만 이어 두면 아무 데서도 그 사슬에 못 들어간다. 축을 열면 이것도
    # 함께 열 것.
    (
        "vocabulary_terms",
        "parent_term_id",
    ): "용어끼리의 상하 — `축` 을 안 이어서 들머리가 없다. 함께 결정할 것",
}


def _uncovered_tables() -> set[str]:
    """마디도 아니고 관계를 나르지도 않는 표."""
    covered = {one.table for one in relations.KINDS.values()}
    covered |= {one.source.table for one in relations.RELATIONS.values() if one.source.table}
    return set(Base.metadata.tables) - covered


def _undescribed_fks() -> set[tuple[str, str]]:
    """**마디끼리 잇는데** 어느 관계도 설명하지 않는 FK."""
    kinds = {one.table for one in relations.KINDS.values()}
    described: set[tuple[str, str]] = set()
    for one in relations.RELATIONS.values():
        source = one.source
        if source.kind == "fk":
            described.add((source.table, source.src_column))
        elif source.kind == "table":
            described.add((source.table, source.src_column))
            described.add((source.table, source.dst_column))

    found: set[tuple[str, str]] = set()
    for name, table in Base.metadata.tables.items():
        if name not in kinds:
            continue
        for column in table.c:
            for key in column.foreign_keys:
                if key.column.table.name in kinds and (name, column.name) not in described:
                    found.add((name, column.name))
    return found


class Test판정표:
    """**빈칸에도 사유가 있어야 한다.**

    온톨로지를 넓히는 일이 「눈에 걸린 것을 줍는 연구」 에서 「목록을 처리하는
    일」 로 바뀌는 자리다. 여기가 비어 있으면 다음 사람은 표 63개를 처음부터
    다시 검토하게 된다 — 이미 한 판단을 아무도 안 적어 뒀기 때문이다.
    """

    def test_모든_표에_판정이_있다(self) -> None:
        left = _uncovered_tables() - set(EXCLUDED_TABLES) - set(PENDING_TABLES)
        assert not left, (
            f"온톨로지 판정이 없는 표: {sorted(left)}\n"
            "마디로 올리든지, `EXCLUDED_TABLES` 에 왜 아닌지 적든지, "
            "`PENDING_TABLES` 에 어떤 물음이 막히는지 적어라."
        )

    def test_판정이_늙지_않았다(self) -> None:
        """마디로 올렸는데 제외 목록에 그대로 남아 있으면, 그 사유는 거짓말이다."""
        uncovered = _uncovered_tables()
        tables = set(Base.metadata.tables)
        for name, where in ((one, "EXCLUDED_TABLES") for one in EXCLUDED_TABLES):
            assert name in tables, f"{where} 에 없는 표가 적혀 있다: {name}"
            assert name in uncovered, f"{name} 은 이제 온톨로지에 있다 — {where} 에서 지워라"
        for name in PENDING_TABLES:
            assert name in tables, f"PENDING_TABLES 에 없는 표가 적혀 있다: {name}"
            assert name in uncovered, (
                f"{name} 은 이제 온톨로지에 있다 — PENDING_TABLES 에서 지워라"
            )

    def test_마디끼리_잇는_FK_에_판정이_있다(self) -> None:
        """**이을 수 있는데 안 이은 것**을 세어 둔다.

        실측 2026-09-10: 이 대조로 셋을 찾았다 — 시험의 채택 결과, 카드의
        시험법, 장비 정의의 출처. 셋 다 「물어보고 싶은데 길이 없던」 것이었다.
        """
        left = _undescribed_fks() - set(EXCLUDED_FKS)
        assert not left, (
            f"마디끼리 잇는데 관계도 사유도 없는 FK: {sorted(left)}\n"
            "관계로 등록하든지 `EXCLUDED_FKS` 에 왜 아닌지 적어라."
        )

    def test_FK_판정도_늙지_않았다(self) -> None:
        stale = set(EXCLUDED_FKS) - _undescribed_fks()
        assert not stale, f"이미 관계가 됐거나 사라진 FK 가 목록에 남아 있다: {sorted(stale)}"

    def test_사유가_비어_있지_않다(self) -> None:
        """사유 없는 제외는 「그냥 안 넣었다」 와 구별이 안 된다."""
        for where, rows in (
            ("EXCLUDED_TABLES", EXCLUDED_TABLES),
            ("PENDING_TABLES", PENDING_TABLES),
        ):
            empty = [name for name, why in rows.items() if len(why.strip()) < 10]
            assert not empty, f"{where}: 사유가 비었다 — {empty}"
        empty_fk = [key for key, why in EXCLUDED_FKS.items() if len(why.strip()) < 10]
        assert not empty_fk, f"EXCLUDED_FKS: 사유가 비었다 — {empty_fk}"
