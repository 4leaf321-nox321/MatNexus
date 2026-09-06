"""사용자 정의 덱 단위계 — 질량·길이·시간 셋만 저장한다

Revision ID: b3f7a9c2d4e1
Revises: e7b2c41f9a05
Create Date: 2026-09-05

두 계(SI · mm·N·tonne)가 코드에 박혀 있어 LS-DYNA 의 mm·ms·kg(GPa) 같은 조합은
배포가 필요했다. 기본 단위 셋만 저장하고 기호·인수는 읽을 때마다 유도한다 —
인수를 저장하면 단위 표가 고쳐졌을 때 저장된 것이 낡는다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3f7a9c2d4e1"
down_revision: Union[str, Sequence[str], None] = "e7b2c41f9a05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "unit_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("mass", sa.String(length=20), nullable=False),
        sa.Column("length", sa.String(length=20), nullable=False),
        sa.Column("time", sa.String(length=20), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_unit_systems_key", "unit_systems", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_unit_systems_key", table_name="unit_systems")
    op.drop_table("unit_systems")
