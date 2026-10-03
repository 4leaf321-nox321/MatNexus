"""물성 분류 — 분야 ⊃ 물성군 ⊃ 물성 (ADR 0054, 2026-10-03)

문헌 물성 정의는 키 앞머리로 열두 갈래로만 나뉘어 있었다. 세 층의 분류를 이관물 옆에 둔다
(`catalog/taxonomy_models.py`).

    property_fields          물성 분야. 씨앗 열둘은 배포의 `refresh_builtins` 가 심는다
    property_groups          물성군 — 분야 하나에 든다
    property_group_members   물성 → 물성군. 물성 하나에 줄 하나(기본 키가 물성 키)

    catalog_definitions.updated_at   바깥(SP)이 물성 목록을 읽을 때 행마다 싣는 「언제 것인가」.
                                     있던 줄은 들어온 때(폐기했으면 폐기한 때)로 채운다

autogenerate 가 `catalog_links` 의 고유 제약 이름 차이도 잡았는데 이 일과 무관한 오래된
어긋남이라 뺐다.

Revision ID: 0672d624d142
Revises: c4e7a2d9b316
Create Date: 2026-10-03 13:35:34.655385

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0672d624d142"
down_revision: str | Sequence[str] | None = "c4e7a2d9b316"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
    ]


def upgrade() -> None:
    op.create_table(
        "property_fields",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_property_fields_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_fields")),
    )
    op.create_index(op.f("ix_property_fields_key"), "property_fields", ["key"], unique=True)

    op.create_table(
        "property_groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("field_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_property_groups_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["field_id"],
            ["property_fields.id"],
            name=op.f("fk_property_groups_field_id_property_fields"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_groups")),
    )
    op.create_index(
        op.f("ix_property_groups_field_id"), "property_groups", ["field_id"], unique=False
    )
    op.create_index(op.f("ix_property_groups_key"), "property_groups", ["key"], unique=True)

    op.create_table(
        "property_group_members",
        sa.Column("property_key", sa.String(length=120), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_property_group_members_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["property_groups.id"],
            name=op.f("fk_property_group_members_group_id_property_groups"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("property_key", name=op.f("pk_property_group_members")),
    )
    op.create_index(
        op.f("ix_property_group_members_group_id"),
        "property_group_members",
        ["group_id"],
        unique=False,
    )

    op.add_column(
        "catalog_definitions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # 있던 줄은 마이그레이션 시각이 아니라 마지막으로 바뀐 때에 가깝게 — 들어온 때, 폐기했으면
    # 폐기한 때. 안 하면 271줄이 전부 「오늘 바뀌었다」 로 나간다.
    op.execute(
        "UPDATE catalog_definitions"
        " SET updated_at = GREATEST(imported_at, COALESCE(deprecated_at, imported_at))"
    )


def downgrade() -> None:
    op.drop_column("catalog_definitions", "updated_at")
    op.drop_index(
        op.f("ix_property_group_members_group_id"), table_name="property_group_members"
    )
    op.drop_table("property_group_members")
    op.drop_index(op.f("ix_property_groups_key"), table_name="property_groups")
    op.drop_index(op.f("ix_property_groups_field_id"), table_name="property_groups")
    op.drop_table("property_groups")
    op.drop_index(op.f("ix_property_fields_key"), table_name="property_fields")
    op.drop_table("property_fields")
