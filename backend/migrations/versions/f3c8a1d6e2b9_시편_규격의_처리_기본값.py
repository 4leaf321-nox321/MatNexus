"""시편 규격의 처리 기본값 — vocabulary_terms.processing_defaults

Revision ID: f3c8a1d6e2b9
Revises: e7b1d4f9a2c6
Create Date: 2026-10-16

굽힘 · 압축(2026-10-16)에서 처리 로직이 **시험 종류로만** 골라졌다. 규격마다 다른 방법(D790 은
접선, ISO 178 은 현, ISO 7743 은 4번째 하중 구간)은 사람이 매번 바꿔야 했고, 안 바꾸면 몇 %
다른 값이 조용히 남았다. 규격이 그 방법을 들고, 처리 화면이 시편의 규격을 보고 채운다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3c8a1d6e2b9"
down_revision: Union[str, Sequence[str], None] = "e7b1d4f9a2c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vocabulary_terms",
        sa.Column(
            "processing_defaults",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("vocabulary_terms", "processing_defaults")
