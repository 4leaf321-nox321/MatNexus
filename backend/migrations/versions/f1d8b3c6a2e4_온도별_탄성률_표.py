"""온도별 탄성률 표 — 주파수 하나에서 본 DMA E′ · E″ · tan δ

Revision ID: f1d8b3c6a2e4
Revises: e7c3a9f2b5d1
Create Date: 2026-10-22

DMA 온도별 E′ 를 잰 물성으로 넘길 길이 없어 재료에 적어 둔 값(출처 추정)으로만 넣고 있었다
(v1.285.0 보고). 마스터커브처럼 시험의 곡선 여럿을 읽어 한 벌을 내는 불변 기록이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1d8b3c6a2e4"
down_revision: Union[str, Sequence[str], None] = "e7c3a9f2b5d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "modulus_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frequency_hz", sa.Float(), nullable=False),
        sa.Column("modulus_basis", sa.String(length=1), server_default="E", nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_curve_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_modulus_tables_test_run_id"), "modulus_tables", ["test_run_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_modulus_tables_test_run_id"), table_name="modulus_tables")
    op.drop_table("modulus_tables")
