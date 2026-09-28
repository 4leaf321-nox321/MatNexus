"""기본 제공 형식의 사용 중단 (ADR 0037)

코드로 만든 솔버 형식은 화면에서 고칠 수 없다. 틀린 것이 발견되면 고쳐 배포하기까지
사람들이 틀린 덱을 계속 내려받는다 — 시스템 관리자가 그 형식을 메뉴에서 내리는 자리다.

    export_format_holds     key(코드 렌더러) · 사유 · 누가 · 언제. 다시 쓰면 행을 지운다

걸고 푼 일은 감사 기록에 남는다(`export_format.held` · `export_format.released`).

Revision ID: b17901e24c40
Revises: 23e1f2c2d047
Create Date: 2026-09-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b17901e24c40"
down_revision: str | Sequence[str] | None = "23e1f2c2d047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_format_holds",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("held_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "held_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["held_by_id"], ["users.id"], name=op.f("fk_export_format_holds_held_by_id_users")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_export_format_holds")),
    )


def downgrade() -> None:
    op.drop_table("export_format_holds")
