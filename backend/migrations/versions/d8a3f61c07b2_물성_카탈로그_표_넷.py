"""물성 카탈로그 표 넷 — 문헌 채굴 데이터를 별도 표로 받는다 (ADR 0027)

Revision ID: d8a3f61c07b2
Revises: b3f7a9c2d4e1
Create Date: 2026-09-05

MaterialTwin 카탈로그(재료·출처·물성 정의·물성값)를 담는 새 표 4개. 기존 표는
건드리지 않는다 — 카탈로그 재료는 문헌상의 등급이고 사내 재료는 실물 lot 이라
수명주기가 다르다. 각 표의 `mt_id` 가 원본 id 를 보존해 이관이 멱등이 된다.
데이터는 어느 환경이든 이관 스크립트 + 원본 파일로만 들어온다(개발→운영 복사
경로 없음).

손으로 쓴 마이그레이션이다 — autogenerate 는 같은 작업 트리의 다른 세션 모델
변경까지 쓸어 담는다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8a3f61c07b2"
down_revision: Union[str, Sequence[str], None] = "b3f7a9c2d4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("material_code", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("subsystem", sa.String(length=50), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=True),
        sa.Column("manufacturer", sa.Text(), nullable=True),
        sa.Column("material_class", sa.Text(), nullable=True),
        sa.Column("grade", sa.Text(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_materials_mt_id", "catalog_materials", ["mt_id"], unique=True)
    op.create_index("ix_catalog_materials_name", "catalog_materials", ["name"])
    op.create_index("ix_catalog_materials_category", "catalog_materials", ["category"])
    op.create_index("ix_catalog_materials_subsystem", "catalog_materials", ["subsystem"])

    op.create_table(
        "catalog_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("doi", sa.String(length=200), nullable=True),
        sa.Column("isbn", sa.String(length=50), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("publisher", sa.String(length=300), nullable=True),
        sa.Column("license", sa.String(length=100), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=100), nullable=True),
        sa.Column("source_retrieved_at", sa.DateTime(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_sources_mt_id", "catalog_sources", ["mt_id"], unique=True)
    op.create_index("ix_catalog_sources_doi", "catalog_sources", ["doi"])

    op.create_table(
        "catalog_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=True),
        sa.Column("si_unit", sa.String(length=50), nullable=True),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("test_standard", sa.String(length=200), nullable=True),
        sa.Column("condition_axes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mt_id", name="uq_catalog_definitions_mt_id"),
    )
    op.create_index("ix_catalog_definitions_key", "catalog_definitions", ["key"], unique=True)
    op.create_index("ix_catalog_definitions_domain", "catalog_definitions", ["domain"])

    op.create_table(
        "catalog_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt_id", sa.Integer(), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_key", sa.String(length=100), nullable=False),
        sa.Column("value_num", sa.Float(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("uncertainty", sa.Float(), nullable=True),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=True),
        sa.Column("quality_tier", sa.SmallInteger(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_detail", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["catalog_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_key"], ["catalog_definitions.key"]),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_values_mt_id", "catalog_values", ["mt_id"], unique=True)
    op.create_index("ix_catalog_values_material_id", "catalog_values", ["material_id"])
    op.create_index("ix_catalog_values_property_key", "catalog_values", ["property_key"])
    op.create_index("ix_catalog_values_quality_tier", "catalog_values", ["quality_tier"])
    op.create_index(
        "ix_catalog_values_material_key", "catalog_values", ["material_id", "property_key"]
    )


def downgrade() -> None:
    op.drop_table("catalog_values")
    op.drop_table("catalog_definitions")
    op.drop_table("catalog_sources")
    op.drop_table("catalog_materials")
