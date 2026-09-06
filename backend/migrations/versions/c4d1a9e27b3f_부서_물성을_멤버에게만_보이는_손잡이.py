"""부서 물성을 멤버에게만 보이는 손잡이

Revision ID: c4d1a9e27b3f
Revises: 8d0e713c5c48
Create Date: 2026-09-05

**기본은 모두에게 보인다.** 전에는 「전역 + 내 부서」 만 보여서 시스템 관리자가
아닌 계정에게 다른 사업부의 물성이 통째로 없는 것처럼 보였다. 물성은 사업부 간
공유가 목적인 데이터라 가리는 쪽이 예외여야 한다 — 그 예외를 부서마다 켤 수
있게 열 하나를 둔다(`restricted`, 기본 false). 기존 부서는 전부 열린 채로 시작한다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d1a9e27b3f"
down_revision: Union[str, Sequence[str], None] = "8d0e713c5c48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("restricted", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "restricted")
