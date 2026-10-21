"""적용 부품 줄 — 파트명 · 제품 · 부품코드 · 사업부 · 출처 (material_uses → material_parts)

Revision ID: d4b9e1f6a3c2
Revises: c8e2a7d4f1b6
Create Date: 2026-10-21

한 재료가 부품 50개에 들어가자(사용자 보고) 칩 스무 개 상한에 걸렸고, 「어느 제품의 어느 파트인지」
· 부품코드 · 사업부를 담을 자리가 없었다(ADR 0064). 예전 용도 줄(`material_uses`, 축마다 한 줄)은
출처 `legacy` 의 줄로 옮기고 지운다 — 기준정보 병합이 옛 표의 외래키에 걸리지 않게.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4b9e1f6a3c2"
down_revision: Union[str, Sequence[str], None] = "c8e2a7d4f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_parts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_term_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("part_name", sa.String(length=200), nullable=True),
        sa.Column("product_term_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column("part_code", sa.String(length=100), nullable=True),
        sa.Column("division_term_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("division_name", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["part_term_id"], ["vocabulary_terms.id"]),
        sa.ForeignKeyConstraint(["product_term_id"], ["vocabulary_terms.id"]),
        sa.ForeignKeyConstraint(["division_term_id"], ["vocabulary_terms.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "material_id",
        "part_term_id",
        "product_term_id",
        "division_term_id",
        "part_code",
    ):
        op.create_index(op.f(f"ix_material_parts_{column}"), "material_parts", [column])

    # 예전 용도 줄 → 출처 `legacy` 의 줄. 축마다 한 줄이라 제품 · 파트의 짝은 모른다 — 그대로 옮긴다.
    op.execute(
        """
        INSERT INTO material_parts (
            id, material_id, part_term_id, part_name, product_term_id, product_name,
            source, position
        )
        SELECT gen_random_uuid(), u.material_id,
               CASE WHEN u.axis = 'part' THEN u.term_id END,
               CASE WHEN u.axis = 'part' THEN u.value END,
               CASE WHEN u.axis = 'product' THEN u.term_id END,
               CASE WHEN u.axis = 'product' THEN u.value END,
               'legacy', u.position
          FROM material_uses AS u
        """
    )
    op.drop_index("ix_material_uses_term_id", table_name="material_uses")
    op.drop_index("ix_material_uses_axis", table_name="material_uses")
    op.drop_index("ix_material_uses_material_id", table_name="material_uses")
    op.drop_table("material_uses")


def downgrade() -> None:
    op.create_table(
        "material_uses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("axis", sa.String(length=20), nullable=False),
        sa.Column("term_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["vocabulary_terms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id", "axis", "term_id", name="uq_material_uses_axis_term"
        ),
    )
    op.create_index("ix_material_uses_material_id", "material_uses", ["material_id"])
    op.create_index("ix_material_uses_axis", "material_uses", ["axis"])
    op.create_index("ix_material_uses_term_id", "material_uses", ["term_id"])
    # 이름 목록만 되돌린다 — 부품코드 · 사업부 · 출처는 예전 표에 자리가 없다.
    op.execute(
        """
        INSERT INTO material_uses (id, material_id, axis, term_id, value, position)
        SELECT gen_random_uuid(), material_id, axis, term_id, left(value, 100), min(position)
          FROM (
            SELECT material_id, 'product' AS axis, product_term_id AS term_id,
                   product_name AS value, position
              FROM material_parts WHERE product_term_id IS NOT NULL
            UNION ALL
            SELECT material_id, 'part', part_term_id, part_name, position
              FROM material_parts WHERE part_term_id IS NOT NULL
          ) AS n
         GROUP BY material_id, axis, term_id, value
        """
    )
    for column in (
        "part_code",
        "division_term_id",
        "product_term_id",
        "part_term_id",
        "material_id",
    ):
        op.drop_index(op.f(f"ix_material_parts_{column}"), table_name="material_parts")
    op.drop_table("material_parts")
