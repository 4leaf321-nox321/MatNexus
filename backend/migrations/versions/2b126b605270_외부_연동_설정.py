"""외부 연동 설정 — TestScope 주소와 봉인한 읽기 토큰

시스템 관리자가 화면에서 넣는다(`.env` 가 아니라, 사용자 요청 2026-10-23). 토큰은 DPAPI 로
봉인해 둔다(`app.shared.secretbox`).

Revision ID: 2b126b605270
Revises: b0fb5b052995
Create Date: 2026-10-23 21:27:36.552445

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b126b605270"
down_revision: Union[str, Sequence[str], None] = "b0fb5b052995"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("system", sa.String(length=40), nullable=False),
        sa.Column("base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("web_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("token_sealed", sa.Text(), server_default="", nullable=False),
        sa.Column("token_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_ok", sa.Boolean(), nullable=True),
        sa.Column("check_message", sa.Text(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_integration_connections_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_connections")),
        sa.UniqueConstraint("system", name=op.f("uq_integration_connections_system")),
    )


def downgrade() -> None:
    op.drop_table("integration_connections")
