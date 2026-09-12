"""물성 키 폐기 — 지우지 않고 「그만 쓰고 저 키를 써라」

값·매핑이 걸린 키는 못 지우고, 사전을 받아 간 다른 시스템이 그 키로 잇고 있다 —
지우면 그쪽이 같은 날 깨진다(2026-09-12). 폐기 표시와 후속 키를 정의에 둔다.

Revision ID: 22ccff22a092
Revises: 0df77dcab737
Create Date: 2026-09-12 11:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "22ccff22a092"
down_revision: str | Sequence[str] | None = "0df77dcab737"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_definitions",
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "catalog_definitions", sa.Column("superseded_by", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "catalog_definitions", sa.Column("deprecation_note", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("catalog_definitions", "deprecation_note")
    op.drop_column("catalog_definitions", "superseded_by")
    op.drop_column("catalog_definitions", "deprecated_at")
