"""처리 결과가 레시피의 몇 번째 판으로, 어떤 단계로 돌았는지 — 판 번호와 단계 지문

Revision ID: d2a8f4c61b37
Revises: c7f1a3e95d26
Create Date: 2026-11-14

VOC 45: 결과에는 레시피 키 · 이름과 그때의 단계만 남고 「몇 번째 판」 이었는지는 없었다. 「같은
레시피로 돌린 결과들」 을 견줄 때 중간에 레시피가 바뀌었는지 알 수 없었다.

- `recipe_revision` — 그 레시피 그대로 돌렸을 때의 판 번호.
- `steps_hash` — 돌린 단계의 지문(sha256). 레시피를 지우거나 키를 다시 써도 견줄 수 있다.

옛 결과는 비어 있다(모름) — 그때의 판을 지금 알 길이 없다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2a8f4c61b37"
down_revision: str | Sequence[str] | None = "c7f1a3e95d26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_results", sa.Column("recipe_revision", sa.Integer(), nullable=True)
    )
    op.add_column("processing_results", sa.Column("steps_hash", sa.String(64), nullable=True))
    op.create_index("ix_processing_results_steps_hash", "processing_results", ["steps_hash"])


def downgrade() -> None:
    op.drop_index("ix_processing_results_steps_hash", table_name="processing_results")
    op.drop_column("processing_results", "steps_hash")
    op.drop_column("processing_results", "recipe_revision")
