"""쓰이지 않는 장비 기준정보 축 둘을 걷어낸다 — 장비 제조사 · 시험실 (정본은 TestScope)

보유 장비(ADR 0069)를 지운 뒤 「장비 제조사」(`instrument_maker`) · 「시험실」(`lab`) 축은 아무도 안
가리킨다 — 둘 다 보유 장비가 쓰던 칸이고, 장비의 제조사 · 위치의 정본은 TestScope 다. 「장비」 · 「장비
유형」 은 시험이 파일에서 읽은 장비 이름을 가리키므로 남긴다.

**바깥에서 가리키는 값이 하나라도 있으면 그 축은 지우지 않는다** — 외래키로 기준정보 값을 가리키는 칸
전부와 SP 코어 연결(`sp_core_links`, 외래키 없이 `target_ref` 로 든다)을 본다. 기준정보 안의 기록(별칭 ·
병합 · 짝 제외)은 값을 지우면 따라 지워지거나 비워진다(CASCADE · SET NULL).

Revision ID: c4e8a1d7f203
Revises: 2b126b605270
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1d7f203"
down_revision: str | Sequence[str] | None = "2b126b605270"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (slug, 이름, 차례) — 되돌릴 때 빈 축으로 다시 세운다.
AXES = (("instrument_maker", "장비 제조사", 49), ("lab", "시험실", 52))

#: 기준정보 안의 표 — 값을 지우면 따라간다. 바깥 쓰임으로 세지 않는다.
INTERNAL = {
    "vocabulary_aliases",
    "vocabulary_dismissals",
    "vocabulary_merges",
    "vocabulary_terms",
}


def _referenced(bind: sa.engine.Connection, ids: list[str]) -> list[str]:
    """이 값들을 가리키는 바깥 자리 — `표.칸(수)`."""
    found: list[str] = []
    columns = bind.execute(
        sa.text(
            """
            SELECT kcu.table_name, kcu.column_name
              FROM information_schema.referential_constraints rc
              JOIN information_schema.key_column_usage kcu
                ON kcu.constraint_name = rc.constraint_name
              JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = rc.unique_constraint_name
             WHERE ccu.table_name = 'vocabulary_terms'
            """
        )
    ).all()
    for table, column in sorted(set(columns)):
        if table in INTERNAL:
            continue
        count = bind.execute(
            sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}"::text = ANY(:ids)'),
            {"ids": ids},
        ).scalar()
        if count:
            found.append(f"{table}.{column}({count})")
    linked = bind.execute(
        sa.text(
            "SELECT count(*) FROM sp_core_links WHERE target_kind = 'term' AND target_ref = ANY(:ids)"
        ),
        {"ids": ids},
    ).scalar()
    if linked:
        found.append(f"sp_core_links({linked})")
    return found


def upgrade() -> None:
    bind = op.get_bind()
    for slug, _label, _order in AXES:
        vocabulary_id = bind.execute(
            sa.text("SELECT id FROM vocabularies WHERE slug = :slug"), {"slug": slug}
        ).scalar()
        if vocabulary_id is None:
            continue
        ids = [
            str(one)
            for one in bind.execute(
                sa.text("SELECT id FROM vocabulary_terms WHERE vocabulary_id = :id"),
                {"id": vocabulary_id},
            ).scalars()
        ]
        if ids:
            users = _referenced(bind, ids)
            if users:
                print(f"[{slug}] 값을 가리키는 곳이 있어 남긴다: {', '.join(users)}")
                continue
            bind.execute(
                sa.text("DELETE FROM vocabulary_terms WHERE id::text = ANY(:ids)"),
                {"ids": ids},
            )
        bind.execute(sa.text("DELETE FROM vocabularies WHERE id = :id"), {"id": vocabulary_id})


def downgrade() -> None:
    # 빈 축으로 다시 세운다 — 지운 값은 돌아오지 않는다(쓰이지 않던 값이었다).
    bind = op.get_bind()
    for slug, label, order in AXES:
        bind.execute(
            sa.text(
                """
                INSERT INTO vocabularies (id, slug, label, entry_policy, sort_order,
                                          base_fields, created_at)
                VALUES (gen_random_uuid(), :slug, :label, 'open', :order, '[]', now())
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {"slug": slug, "label": label, "order": order},
        )
