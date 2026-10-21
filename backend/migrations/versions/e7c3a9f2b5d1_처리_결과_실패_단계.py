"""처리 결과에 실패한 단계 — 부분 결과를 저장한다

Revision ID: e7c3a9f2b5d1
Revises: d4b9e1f6a3c2
Create Date: 2026-10-22

한 단계라도 실패하면 처리 결과를 저장하지 않던 것을, 나온 값은 부분 결과로 저장하고 실패한
단계를 함께 남기게 바꿨다(v1.285.0 보고: 일괄 처리에서 탄성계수가 안 나오면 인장강도까지
저장되지 않음). 예전 결과는 전부 완전한 결과였으므로 빈 목록이 맞다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7c3a9f2b5d1"
down_revision: Union[str, Sequence[str], None] = "d4b9e1f6a3c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "processing_results",
        sa.Column(
            "failures",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("processing_results", "failures")
