"""문헌 값의 이어진 한 벌 — 곡선 · 표 · 계수 묶음의 머리와 점의 묶음 칸

Revision ID: a5c2e8d4f9b1
Revises: f1d8b3c6a2e4
Create Date: 2026-10-22

문헌 값은 낱값뿐이라 온도별 영률 여섯 점이 한 곡선이라는 사실이 어디에도 없었고, 응력-변형률
곡선은 넣을 길이 없었다(ADR 0067). 점은 지금처럼 문헌 값 한 줄씩이고 묶음 칸으로 머리에 잇는다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a5c2e8d4f9b1"
down_revision: Union[str, Sequence[str], None] = "f1d8b3c6a2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_series",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("x_key", sa.String(length=100), nullable=True),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=True),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("quality_tier", sa.SmallInteger(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_detail", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["catalog_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_series_material_id"), "catalog_series", ["material_id"])
    op.add_column(
        "catalog_values",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "catalog_values_series_id_fkey",
        "catalog_values",
        "catalog_series",
        ["series_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_catalog_values_series_id"), "catalog_values", ["series_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_catalog_values_series_id"), table_name="catalog_values")
    op.drop_constraint("catalog_values_series_id_fkey", "catalog_values", type_="foreignkey")
    op.drop_column("catalog_values", "series_id")
    op.drop_index(op.f("ix_catalog_series_material_id"), table_name="catalog_series")
    op.drop_table("catalog_series")
