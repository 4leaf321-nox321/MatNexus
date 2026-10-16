"""선언 값 승인 요청 기록 — material_approval_requests

Revision ID: e7b1d4f9a2c6
Revises: d5a9c3e7b2f1
Create Date: 2026-10-16

선언 값 승인 요청(2026-10-15)은 알림만 보내고 기록이 없었다. 알림의 중복 막기는 받는 사람마다
마지막 키 하나만 견줘서, 사이에 다른 요청이 끼면 같은 부탁이 다시 갔다. 카드는 코멘트로 하루 한
번을 막는데 재료에는 적어 둘 자리가 없었다 — 그 자리를 둔다. 상태도 큐도 아니다(ADR 0049 결정 5).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7b1d4f9a2c6"
down_revision: Union[str, Sequence[str], None] = "d5a9c3e7b2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pending", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("client", sa.String(length=20), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_material_approval_requests_material_id"),
        "material_approval_requests",
        ["material_id"],
    )
    op.create_index(
        op.f("ix_material_approval_requests_created_by_id"),
        "material_approval_requests",
        ["created_by_id"],
    )
    op.create_index(
        op.f("ix_material_approval_requests_created_at"),
        "material_approval_requests",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_material_approval_requests_created_at"),
        table_name="material_approval_requests",
    )
    op.drop_index(
        op.f("ix_material_approval_requests_created_by_id"),
        table_name="material_approval_requests",
    )
    op.drop_index(
        op.f("ix_material_approval_requests_material_id"),
        table_name="material_approval_requests",
    )
    op.drop_table("material_approval_requests")
