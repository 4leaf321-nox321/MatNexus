"""SP 코어 온톨로지 받기 — 받은 원본 · 받은 기록 · 연결

Revision ID: c8e2a7d4f1b6
Revises: f3c8a1d6e2b9
Create Date: 2026-10-21

Standard Platform 의 코어 온톨로지(부서 · 기관 · 장비 · PLM 개발모델 · 물성 …)를 코어 API 로 받아
**받은 그대로** 쌓고, 기준정보 값 · 물성 · 분류와 잇는 연결을 따로 든다(ADR 0063). 기존 표는
건드리지 않는다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8e2a7d4f1b6"
down_revision: Union[str, Sequence[str], None] = "f3c8a1d6e2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "sp_core_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("properties", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("relation_kinds", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("sp_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("rows_as_of", sa.String(length=40), nullable=True),
        sa.Column("relations_as_of", sa.String(length=40), nullable=True),
        sa.Column("full_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sp_core_types_slug"), "sp_core_types", ["slug"], unique=True)

    op.create_table(
        "sp_core_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type_slug", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=300), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("merged_into", sa.String(length=120), nullable=True),
        sa.Column("previous_keys", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("properties", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("sp_updated_at", sa.String(length=40), nullable=True),
        sa.Column("seen_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type_slug", "key", name="uq_sp_core_objects_type_key"),
    )
    op.create_index(op.f("ix_sp_core_objects_type_slug"), "sp_core_objects", ["type_slug"])

    op.create_table(
        "sp_core_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("src_type", sa.String(length=100), nullable=False),
        sa.Column("src", sa.String(length=120), nullable=False),
        sa.Column("relation", sa.String(length=100), nullable=False),
        sa.Column("dst", sa.String(length=120), nullable=False),
        sa.Column("dst_type", sa.String(length=100), nullable=False),
        sa.Column("evidence_note", sa.Text(), nullable=True),
        sa.Column("properties", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sp_updated_at", sa.String(length=40), nullable=True),
        sa.Column("seen_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "src_type", "src", "relation", "dst", "dst_type", name="uq_sp_core_relations_edge"
        ),
    )
    op.create_index(op.f("ix_sp_core_relations_src_type"), "sp_core_relations", ["src_type"])
    op.create_index(op.f("ix_sp_core_relations_dst_type"), "sp_core_relations", ["dst_type"])

    op.create_table(
        "sp_core_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("full", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("system", sa.String(length=100), nullable=True),
        sa.Column("revision", sa.String(length=100), nullable=True),
        sa.Column("counts", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sp_core_runs_started_at"), "sp_core_runs", ["started_at"])

    op.create_table(
        "sp_core_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sp_type", sa.String(length=100), nullable=False),
        sa.Column("sp_key", sa.String(length=120), nullable=False),
        sa.Column("target_kind", sa.String(length=30), nullable=False),
        sa.Column("target_ref", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sp_type", "sp_key", "target_kind", "target_ref", name="uq_sp_core_links_pair"
        ),
    )
    op.create_index(op.f("ix_sp_core_links_sp_type"), "sp_core_links", ["sp_type"])
    op.create_index(op.f("ix_sp_core_links_sp_key"), "sp_core_links", ["sp_key"])
    op.create_index(op.f("ix_sp_core_links_target_ref"), "sp_core_links", ["target_ref"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sp_core_links_target_ref"), table_name="sp_core_links")
    op.drop_index(op.f("ix_sp_core_links_sp_key"), table_name="sp_core_links")
    op.drop_index(op.f("ix_sp_core_links_sp_type"), table_name="sp_core_links")
    op.drop_table("sp_core_links")
    op.drop_index(op.f("ix_sp_core_runs_started_at"), table_name="sp_core_runs")
    op.drop_table("sp_core_runs")
    op.drop_index(op.f("ix_sp_core_relations_dst_type"), table_name="sp_core_relations")
    op.drop_index(op.f("ix_sp_core_relations_src_type"), table_name="sp_core_relations")
    op.drop_table("sp_core_relations")
    op.drop_index(op.f("ix_sp_core_objects_type_slug"), table_name="sp_core_objects")
    op.drop_table("sp_core_objects")
    op.drop_index(op.f("ix_sp_core_types_slug"), table_name="sp_core_types")
    op.drop_table("sp_core_types")
