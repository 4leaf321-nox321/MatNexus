"""카드 코멘트 — 근거 시험이 다른 재료로 옮겨졌을 때 카드에 남는 말

두께를 잘못 넣은 시편을 「같은 재료, 기준 두께만 다른 것」 으로 옮기는 길이 생겼다. 그 시험으로
만든 카드(확정 포함)가 원 재료에 남으므로, 옮긴 사실과 사람의 말을 카드 곁에 둔다. 카드의 값·
근거는 불변이라 카드 행이 아니라 따로 둔다.

    property_card_remarks    카드 · 종류(relocated · comment) · 사실 · 사람의 말 · 무엇이 어디로 · 누가 · 언제

Revision ID: a337a744b3b6
Revises: b17901e24c40
Create Date: 2026-09-29 20:44:18.805088

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a337a744b3b6"
down_revision: str | Sequence[str] | None = "b17901e24c40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "property_card_remarks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("card_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["property_cards.id"],
            name=op.f("fk_property_card_remarks_card_id_property_cards"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_property_card_remarks_created_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_card_remarks")),
    )
    op.create_index(
        op.f("ix_property_card_remarks_card_id"),
        "property_card_remarks",
        ["card_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_card_remarks_created_by_id"),
        "property_card_remarks",
        ["created_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_property_card_remarks_created_by_id"), table_name="property_card_remarks"
    )
    op.drop_index(op.f("ix_property_card_remarks_card_id"), table_name="property_card_remarks")
    op.drop_table("property_card_remarks")
