"""카탈로그에 직접 넣기 — 이관 밖의 물성·재료·값

MaterialTwin 에 없는 물성을 쓰려면 저쪽에 넣고 다시 이관해야 했다(2026-09-12).
네 표의 `mt_id` 를 비울 수 있게 하고 `created_by_id` 를 더한다 — `mt_id IS NULL`
이 「여기서 직접 넣은 줄」 이다. 정의의 키는 `local.` 으로 시작한다.

Revision ID: 27ea22e88a43
Revises: 7c51b72321d5
Create Date: 2026-09-12 09:34:40.158247

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27ea22e88a43"
down_revision: str | Sequence[str] | None = "7c51b72321d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("catalog_definitions", "catalog_materials", "catalog_sources", "catalog_values")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("created_by_id", sa.UUID(), nullable=True))
        op.alter_column(table, "mt_id", existing_type=sa.INTEGER(), nullable=True)
        op.create_foreign_key(
            op.f(f"fk_{table}_created_by_id_users"),
            table,
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # 직접 넣은 줄은 원본이 없어 NOT NULL 로 못 돌아간다 — 값부터 지운다.
    op.execute("DELETE FROM catalog_values WHERE mt_id IS NULL")
    op.execute("DELETE FROM catalog_sources WHERE mt_id IS NULL")
    op.execute("DELETE FROM catalog_materials WHERE mt_id IS NULL")
    op.execute("DELETE FROM catalog_definitions WHERE mt_id IS NULL")
    for table in reversed(TABLES):
        op.drop_constraint(op.f(f"fk_{table}_created_by_id_users"), table, type_="foreignkey")
        op.alter_column(table, "mt_id", existing_type=sa.INTEGER(), nullable=False)
        op.drop_column(table, "created_by_id")
