"""마스터커브 대표 지정

시험마다 마스터커브가 여럿일 수 있는데(기준 온도를 바꿔 가며 만든다), 재료의
글로벌 피팅은 그중 하나만 읽는다. 전에는 **가장 최근 것**을 말없이 썼다 —
20 °C 로 만들어 쓰다가 30 °C 로 하나 더 만들면 그 순간부터 재료 쪽 계산이 바뀌는데
화면 어디에도 그 전환이 안 보였다.

**옛 데이터도 대표를 갖게 채운다.** 안 채우면 마이그레이션 직후 모든 시험의 대표가
비고, 그때 글로벌 피팅은 정렬의 두 번째 키(`created_at`)로 떨어져 옛 동작을 그대로
한다 — 고친 것이 아무 데도 안 드러난다. 지금 쓰이던 것(가장 최근 것)을 그대로
대표로 세워, 이 마이그레이션이 **동작을 바꾸지 않게** 한다.

Revision ID: bc089102090d
Revises: a3a079188c7f
Create Date: 2026-08-31 07:00:15.665205

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bc089102090d"
down_revision: Union[str, Sequence[str], None] = "a3a079188c7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# **autogenerate 가 지우자고 한 것을 안 지운다.** `guide_sections` 의 trgm 색인은
# 손으로 만든 것이라 모델에 안 나타나고, 그래서 매번 「없어졌다」 로 잡힌다.
# 지우면 안내 검색이 조용히 느려진다.


def upgrade() -> None:
    op.add_column(
        "master_curves",
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
    )
    # 시험마다 가장 최근 것 하나 — 지금까지 실제로 쓰이던 그 곡선이다.
    op.execute(
        """
        UPDATE master_curves
           SET is_primary = true
         WHERE id IN (
               SELECT DISTINCT ON (test_run_id) id
                 FROM master_curves
                ORDER BY test_run_id, created_at DESC
         )
        """
    )
    op.create_index(
        "uq_master_curves_primary",
        "master_curves",
        ["test_run_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_master_curves_primary",
        table_name="master_curves",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_column("master_curves", "is_primary")
