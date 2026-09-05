"""측정법 표 둘 — 계측 장비와 측정 능력 (MaterialTwin 이식 4단계)

Revision ID: f2b8c5d94a17
Revises: e5c9d24a71f0
Create Date: 2026-09-06

「그 물성은 무엇으로 재는가」 — 장비(제조사·모델·보유 여부)와 능력(장비 하나가
물성 하나를 어떤 기법·규격으로, 인쇄된 사양과 함께). mt_id 로 이관이 멱등이고,
데이터는 이관 스크립트 + 원본 파일로만 들어온다(ADR 0027 과 같은 무늬).
손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f2b8c5d94a17"
down_revision: Union[str, Sequence[str], None] = "e5c9d24a71f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt_id", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(length=200), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("technique", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("doc_path", sa.Text(), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("owned", sa.Boolean(), nullable=False),
        sa.Column("owned_note", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.String(length=200), nullable=True),
        sa.Column("owner_contact", sa.String(length=200), nullable=True),
        sa.Column("owned_checked_at", sa.DateTime(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor", "model", name="uq_instruments_vendor_model"),
    )
    op.create_index("ix_instruments_mt_id", "instruments", ["mt_id"], unique=True)
    op.create_index("ix_instruments_category", "instruments", ["category"])

    op.create_table(
        "instrument_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_key", sa.String(length=100), nullable=False),
        sa.Column("technique", sa.Text(), nullable=True),
        sa.Column("standard", sa.String(length=200), nullable=True),
        sa.Column("range_min", sa.Float(), nullable=True),
        sa.Column("range_max", sa.Float(), nullable=True),
        sa.Column("range_unit", sa.String(length=50), nullable=True),
        sa.Column("resolution", sa.String(length=200), nullable=True),
        sa.Column("accuracy", sa.String(length=200), nullable=True),
        sa.Column("temperature_min_k", sa.Float(), nullable=True),
        sa.Column("temperature_max_k", sa.Float(), nullable=True),
        sa.Column("specimen", sa.Text(), nullable=True),
        sa.Column("mapping_confidence", sa.String(length=10), nullable=True),
        sa.Column("source_detail", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_key"], ["catalog_definitions.key"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id", "property_key", "technique", name="uq_capabilities_triple"
        ),
    )
    op.create_index(
        "ix_instrument_capabilities_mt_id", "instrument_capabilities", ["mt_id"], unique=True
    )
    op.create_index(
        "ix_instrument_capabilities_instrument_id",
        "instrument_capabilities",
        ["instrument_id"],
    )
    op.create_index(
        "ix_instrument_capabilities_property_key",
        "instrument_capabilities",
        ["property_key"],
    )


def downgrade() -> None:
    op.drop_table("instrument_capabilities")
    op.drop_table("instruments")
