"""BOM 매칭 기억 — bom_aliases (MaterialTwin 이식 2.5단계, 혼합 덱)

Revision ID: b9e2f5a8c1d4
Revises: d47e91b0c3a8
Create Date: 2026-09-06

부품표의 재료 이름(회사 관행)과 우리 재료의 매칭은 사람의 판단이다 — 판단을
저장해 다음 붙여넣기에서 자동으로 맞게 한다. 전사 하나(normalized 유일).
손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b9e2f5a8c1d4"
down_revision: Union[str, Sequence[str], None] = "d47e91b0c3a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bom_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized", sa.String(length=200), nullable=False),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("catalog_material_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["catalog_material_id"], ["catalog_materials.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bom_aliases_normalized", "bom_aliases", ["normalized"], unique=True)
    op.create_index("ix_bom_aliases_material_id", "bom_aliases", ["material_id"])
    op.create_index(
        "ix_bom_aliases_catalog_material_id", "bom_aliases", ["catalog_material_id"]
    )


def downgrade() -> None:
    op.drop_table("bom_aliases")
