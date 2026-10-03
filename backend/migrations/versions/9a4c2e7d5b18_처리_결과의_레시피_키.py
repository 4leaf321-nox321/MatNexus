"""처리 결과의 레시피 키 (2026-10-03, 이슈 #2)

결과가 어느 레시피로 나왔는지를 키로 남긴다. 전에는 레시피 id 와 이름만 남고 응답의 키는 늘
비어 있었다 — 이름은 바뀌고 id 는 레시피를 지우면 끊긴다.

    processing_results.recipe_key   그 레시피 **그대로** 돌렸을 때의 키. 단계를 고쳐서 저장한
                                    것은 비운다(`routes._recipe_link`)

있던 결과는 아직 살아 있는 레시피에 이어진 것만 그 키로 채운다. 지운 레시피의 결과는 알 길이
없어 비워 둔다.

Revision ID: 9a4c2e7d5b18
Revises: 5d9e3b7f1c42
Create Date: 2026-10-03 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a4c2e7d5b18"
down_revision: str | Sequence[str] | None = "5d9e3b7f1c42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_results",
        sa.Column("recipe_key", sa.String(length=80), nullable=True),
    )
    op.execute(
        "UPDATE processing_results AS r SET recipe_key = p.key"
        " FROM processing_recipes AS p WHERE r.recipe_id = p.id"
    )


def downgrade() -> None:
    op.drop_column("processing_results", "recipe_key")
