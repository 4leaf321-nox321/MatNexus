"""문헌 반입 묶음 · 외부 키 · 출처의 귀속 문구 · 산점 벌의 점

Revision ID: b8d3f1a6c2e7
Revises: a5c2e8d4f9b1
Create Date: 2026-10-23

외부 공개 데이터(MaterialCollector)를 묶음 파일 하나로 들인다(ADR 0068). 같은 묶음을 다시 들여도
중복이 생기지 않게 줄마다 외부 키와 내용 지문을 남기고, 출처는 라이선스와 귀속 문구를 든다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8d3f1a6c2e7"
down_revision: Union[str, Sequence[str], None] = "a5c2e8d4f9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("catalog_materials", "catalog_sources", "catalog_values", "catalog_series")


def upgrade() -> None:
    op.create_table(
        "catalog_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_batches_key"), "catalog_batches", ["key"], unique=True)
    for table in TABLES:
        op.add_column(
            table, sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        op.add_column(table, sa.Column("external_key", sa.String(length=200), nullable=True))
        op.add_column(table, sa.Column("external_hash", sa.String(length=64), nullable=True))
        op.create_foreign_key(
            f"{table}_batch_id_fkey",
            table,
            "catalog_batches",
            ["batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(op.f(f"ix_{table}_batch_id"), table, ["batch_id"])
        op.create_index(
            f"uq_{table}_external_key",
            table,
            ["external_key"],
            unique=True,
            postgresql_where=sa.text("external_key IS NOT NULL"),
        )
    op.add_column("catalog_sources", sa.Column("attribution", sa.Text(), nullable=True))
    op.add_column(
        "catalog_values",
        sa.Column(
            "scatter_point", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("catalog_values", "scatter_point")
    op.drop_column("catalog_sources", "attribution")
    for table in TABLES:
        op.drop_index(f"uq_{table}_external_key", table_name=table)
        op.drop_index(op.f(f"ix_{table}_batch_id"), table_name=table)
        op.drop_constraint(f"{table}_batch_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "external_hash")
        op.drop_column(table, "external_key")
        op.drop_column(table, "batch_id")
    op.drop_index(op.f("ix_catalog_batches_key"), table_name="catalog_batches")
    op.drop_table("catalog_batches")
