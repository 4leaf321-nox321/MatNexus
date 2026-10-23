"""보유 장비를 지운다 — 정본은 TestScope

장비 자산(위치 · 상태 · 교정 · 부속)은 TestScope 가 기종 · 사양까지 온전히 다루고, MatNexus 의
보유 장비는 시험 · 측정법 · 의뢰 어디에도 이어지지 않은 채 남아 있었다(2026-10-23). 운영에는
등록된 장비가 없다(사용자 확인). 되돌리기는 표 모양만 되살린다 — 값은 배포 전날 백업에 있다.

Revision ID: b0fb5b052995
Revises: b8d3f1a6c2e7
Create Date: 2026-10-23 21:23:54.073952

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b0fb5b052995"
down_revision: Union[str, Sequence[str], None] = "b8d3f1a6c2e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 딸린 것부터 — 교정이 부속과 장비를, 부속이 장비를 가리킨다. 색인은 표와 함께 지워진다.
    op.drop_table("equipment_calibrations")
    op.drop_table("equipment_parts")
    op.drop_table("equipment_units")


def downgrade() -> None:
    op.create_table(
        "equipment_units",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("asset_no", sa.VARCHAR(length=80), autoincrement=False, nullable=True),
        sa.Column("asset_key", sa.VARCHAR(length=80), autoincrement=False, nullable=True),
        sa.Column("name", sa.VARCHAR(length=120), autoincrement=False, nullable=False),
        sa.Column("instrument_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("instrument_term_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("type_term_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("manufacturer", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column("model", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column("serial_no", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("manufacturer_term_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("lab_term_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column(
            "location_detail", sa.VARCHAR(length=200), autoincrement=False, nullable=True
        ),
        sa.Column("ownership", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("workspace_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("owner_name", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("owner_contact", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("commissioned_on", sa.DATE(), autoincrement=False, nullable=True),
        sa.Column("retired_on", sa.DATE(), autoincrement=False, nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("notes", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "instrument_type", sa.VARCHAR(length=120), autoincrement=False, nullable=True
        ),
        sa.Column("instrument", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("lab", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("registered_by_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("edit_workspace_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["edit_workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_equipment_units_edit_workspace_id_workspaces"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_equipment_units_instrument_id_instruments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_term_id"],
            ["vocabulary_terms.id"],
            name=op.f("fk_equipment_units_instrument_term_id_vocabulary_terms"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lab_term_id"],
            ["vocabulary_terms.id"],
            name=op.f("fk_equipment_units_lab_term_id_vocabulary_terms"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["manufacturer_term_id"],
            ["vocabulary_terms.id"],
            name=op.f("fk_equipment_units_manufacturer_term_id_vocabulary_terms"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["registered_by_id"],
            ["users.id"],
            name=op.f("fk_equipment_units_registered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["type_term_id"],
            ["vocabulary_terms.id"],
            name=op.f("fk_equipment_units_type_term_id_vocabulary_terms"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_equipment_units_workspace_id_workspaces"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_units")),
        sa.UniqueConstraint(
            "asset_key",
            name=op.f("uq_equipment_units_asset_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_index(
        op.f("ix_equipment_units_workspace_id"),
        "equipment_units",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_type_term_id"),
        "equipment_units",
        ["type_term_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_status"), "equipment_units", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_equipment_units_registered_by_id"),
        "equipment_units",
        ["registered_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_ownership"), "equipment_units", ["ownership"], unique=False
    )
    op.create_index(op.f("ix_equipment_units_name"), "equipment_units", ["name"], unique=False)
    op.create_index(
        op.f("ix_equipment_units_manufacturer_term_id"),
        "equipment_units",
        ["manufacturer_term_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_lab_term_id"),
        "equipment_units",
        ["lab_term_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_instrument_term_id"),
        "equipment_units",
        ["instrument_term_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_instrument_id"),
        "equipment_units",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_edit_workspace_id"),
        "equipment_units",
        ["edit_workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_units_asset_key"), "equipment_units", ["asset_key"], unique=False
    )
    op.create_table(
        "equipment_parts",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("unit_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("kind", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("label", sa.VARCHAR(length=120), autoincrement=False, nullable=False),
        sa.Column("asset_no", sa.VARCHAR(length=80), autoincrement=False, nullable=True),
        sa.Column("manufacturer", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column("model", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column("serial_no", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("capacity", sa.VARCHAR(length=120), autoincrement=False, nullable=True),
        sa.Column("installed_on", sa.DATE(), autoincrement=False, nullable=True),
        sa.Column("removed_on", sa.DATE(), autoincrement=False, nullable=True),
        sa.Column("notes", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["equipment_units.id"],
            name=op.f("fk_equipment_parts_unit_id_equipment_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_parts")),
    )
    op.create_index(
        op.f("ix_equipment_parts_unit_id"), "equipment_parts", ["unit_id"], unique=False
    )
    op.create_index(op.f("ix_equipment_parts_kind"), "equipment_parts", ["kind"], unique=False)
    op.create_table(
        "equipment_calibrations",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("unit_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("part_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("performed_on", sa.DATE(), autoincrement=False, nullable=False),
        sa.Column("valid_until", sa.DATE(), autoincrement=False, nullable=True),
        sa.Column("agency", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column(
            "certificate_no", sa.VARCHAR(length=120), autoincrement=False, nullable=True
        ),
        sa.Column("result", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("storage_path", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("notes", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["part_id"],
            ["equipment_parts.id"],
            name=op.f("fk_equipment_calibrations_part_id_equipment_parts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["equipment_units.id"],
            name=op.f("fk_equipment_calibrations_unit_id_equipment_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_calibrations")),
    )
    op.create_index(
        op.f("ix_equipment_calibrations_valid_until"),
        "equipment_calibrations",
        ["valid_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_calibrations_unit_id"),
        "equipment_calibrations",
        ["unit_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_calibrations_performed_on"),
        "equipment_calibrations",
        ["performed_on"],
        unique=False,
    )
    op.create_index(
        op.f("ix_equipment_calibrations_part_id"),
        "equipment_calibrations",
        ["part_id"],
        unique=False,
    )
