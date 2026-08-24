"""분류 계층

Revision ID: 71f73806a42f
Revises: c15961e7444a
Create Date: 2026-08-21 03:12:41.932220

"""

from typing import Sequence, Union

import logging

from alembic import op
import sqlalchemy as sa

from app.shared.text import clean, compare_key

logger = logging.getLogger("alembic.runtime.migration")


# revision identifiers, used by Alembic.
revision: str = "71f73806a42f"
down_revision: Union[str, Sequence[str], None] = "c15961e7444a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- 분류 계층 --------------------------------------------------------------
#
# **분류는 사슬이다.** Metal → Steel → SECC. 평평하게 두면 Polymer + PP + SECC
# 같은 조합을 아무도 안 막고, 강종이 수만 개일 때 피커가 전체를 보여 준다.
#
# 실측(개발 DB): 강종 86종 중 두 분류에 걸친 것은 하나뿐이고 그것도 쓰레기 분류
# (`Family/Category`)에 붙은 것이다. 실사용에서는 강종 → 분류가 함수다.


def _seed_and_backfill_classification() -> None:
    bind = op.get_bind()
    for slug, label, order, parent in (
        ("family", "Family", 1, None),
        ("category", "Category", 2, "family"),
    ):
        bind.execute(
            sa.text(
                "INSERT INTO vocabularies (id, slug, label, entry_policy, sort_order,"
                " parent_slug) VALUES (gen_random_uuid(), :slug, :label, 'open', :order,"
                " :parent)"
            ),
            {"slug": slug, "label": label, "order": order, "parent": parent},
        )
    bind.execute(
        sa.text("UPDATE vocabularies SET parent_slug = 'category' WHERE slug = 'grade'")
    )

    ids = {
        slug: bind.execute(
            sa.text("SELECT id FROM vocabularies WHERE slug = :slug"), {"slug": slug}
        ).scalar_one()
        for slug in ("family", "category", "grade")
    }

    for slug, column in (("family", "family"), ("category", "category")):
        rows = (
            bind.execute(
                sa.text(
                    f"SELECT DISTINCT {column} FROM materials"
                    f" WHERE {column} IS NOT NULL AND {column} <> ''"
                )
            )
            .scalars()
            .all()
        )
        for raw in rows:
            key, value = compare_key(raw), clean(raw)
            if not key or value is None:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO vocabulary_terms"
                    " (id, vocabulary_id, value, normalized, status, usage_count)"
                    " VALUES (gen_random_uuid(), :vid, :value, :key, 'active', 0)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"vid": ids[slug], "value": value, "key": key},
            )
        filled = bind.execute(
            sa.text(
                f"""
                UPDATE materials AS m
                   SET {column}_term_id = t.id
                  FROM vocabulary_terms AS t
                 WHERE t.vocabulary_id = :vid
                   AND t.normalized = lower(btrim(m.{column}))
                """
            ),
            {"vid": ids[slug]},
        ).rowcount
        logger.info("%s 어휘: 재료 %s건 연결", slug, filled)

    # **부모를 데이터에서 추론한다.** 값마다 그 값을 쓰는 재료의 상위 분류를 본다.
    # 갈리는 것은 **잇지 않는다** — 어느 쪽이 맞는지 마이그레이션이 정할 일이 아니다.
    for child, parent, child_col, parent_col in (
        ("category", "family", "category_term_id", "family_term_id"),
        ("grade", "category", "grade_term_id", "category_term_id"),
    ):
        linked = bind.execute(
            sa.text(
                f"""
                UPDATE vocabulary_terms AS t
                   SET parent_term_id = agreed.parent_id
                  FROM (
                        SELECT m.{child_col} AS child_id,
                               MIN(m.{parent_col}::text)::uuid AS parent_id
                          FROM materials AS m
                         WHERE m.{child_col} IS NOT NULL
                           AND m.{parent_col} IS NOT NULL
                           AND m.deleted_at IS NULL
                         GROUP BY m.{child_col}
                        HAVING COUNT(DISTINCT m.{parent_col}) = 1
                       ) AS agreed
                 WHERE t.id = agreed.child_id
                """
            )
        ).rowcount
        logger.info("%s → %s 부모 연결: %s건", child, parent, linked)

        conflicts = bind.execute(
            sa.text(
                f"""
                SELECT t.value, COUNT(DISTINCT m.{parent_col})
                  FROM materials AS m
                  JOIN vocabulary_terms AS t ON t.id = m.{child_col}
                 WHERE m.{parent_col} IS NOT NULL AND m.deleted_at IS NULL
                 GROUP BY t.id, t.value
                HAVING COUNT(DISTINCT m.{parent_col}) > 1
                """
            )
        ).all()
        for value, n in conflicts:
            logger.warning(
                "%s %r 가 %s가지 %s 아래 있습니다 — 부모를 안 이었습니다. "
                "어휘 관리에서 정하세요.",
                child,
                value,
                n,
                parent,
            )

    for slug in ("family", "category"):
        column = f"{slug}_term_id"
        bind.execute(
            sa.text(
                f"""
                UPDATE vocabulary_terms AS t
                   SET usage_count = (SELECT count(*) FROM materials
                                       WHERE {column} = t.id AND deleted_at IS NULL)
                 WHERE t.vocabulary_id = :vid
                """
            ),
            {"vid": ids[slug]},
        )


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("materials", sa.Column("family_term_id", sa.UUID(), nullable=True))
    op.add_column("materials", sa.Column("category_term_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_materials_category_term_id"), "materials", ["category_term_id"], unique=False
    )
    op.create_index(
        op.f("ix_materials_family_term_id"), "materials", ["family_term_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_materials_family_term_id_vocabulary_terms"),
        "materials",
        "vocabulary_terms",
        ["family_term_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_materials_category_term_id_vocabulary_terms"),
        "materials",
        "vocabulary_terms",
        ["category_term_id"],
        ["id"],
    )
    op.add_column(
        "vocabularies", sa.Column("parent_slug", sa.String(length=50), nullable=True)
    )
    op.add_column("vocabulary_terms", sa.Column("parent_term_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_vocabulary_terms_parent_term_id"),
        "vocabulary_terms",
        ["parent_term_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_vocabulary_terms_parent_term_id_vocabulary_terms"),
        "vocabulary_terms",
        "vocabulary_terms",
        ["parent_term_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # ### end Alembic commands ###
    _seed_and_backfill_classification()


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("fk_vocabulary_terms_parent_term_id_vocabulary_terms"),
        "vocabulary_terms",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_vocabulary_terms_parent_term_id"), table_name="vocabulary_terms")
    op.drop_column("vocabulary_terms", "parent_term_id")
    op.drop_column("vocabularies", "parent_slug")
    op.drop_constraint(
        op.f("fk_materials_category_term_id_vocabulary_terms"), "materials", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_materials_family_term_id_vocabulary_terms"), "materials", type_="foreignkey"
    )
    op.drop_index(op.f("ix_materials_family_term_id"), table_name="materials")
    op.drop_index(op.f("ix_materials_category_term_id"), table_name="materials")
    op.drop_column("materials", "category_term_id")
    op.drop_column("materials", "family_term_id")
    # ### end Alembic commands ###
