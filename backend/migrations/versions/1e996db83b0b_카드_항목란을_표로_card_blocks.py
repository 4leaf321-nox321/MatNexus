"""카드 항목란을 표로 — `card_blocks` (ADR 0033).

화면에서 만든 항목란이 행 하나이고, 기동할 때와 저장할 때 `matcore.cards` 레지스트리에
얹힌다. **내장 12개는 옮기지 않는다** — 코드가 그대로 등록하고, 이 표는 추가만 한다.

자동 생성이 `catalog_links` 의 유니크 제약 이름 정리(`uq_catalog_links_material` →
`…_material_id`)도 함께 내놨는데 **뺐다.** 이 작업과 무관한 남의 표이고, 이름만 바꾸는
변경을 이 마이그레이션에 얹으면 되돌릴 때 함께 딸려 온다.

Revision ID: 1e996db83b0b
Revises: 1239706f7343
Create Date: 2026-09-21 23:03:09.654684

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1e996db83b0b"
down_revision: Union[str, Sequence[str], None] = "1239706f7343"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "card_blocks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("help", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "produces",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "rows",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="200", nullable=False),
        sa.Column("kind_priority", sa.Integer(), nullable=True),
        sa.Column("curve_x", sa.String(length=60), nullable=True),
        sa.Column("curve_y", sa.String(length=60), nullable=True),
        sa.Column(
            "from_tests",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("measured", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_card_blocks_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_blocks")),
    )
    op.create_index(op.f("ix_card_blocks_key"), "card_blocks", ["key"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_card_blocks_key"), table_name="card_blocks")
    op.drop_table("card_blocks")
