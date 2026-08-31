"""온도 단 수를 세어 둔다

DMA 는 같은 시험종류 아래 성격이 다른 둘이 온다 — 주파수-온도 스윕(온도 여러 단)과
변형률 스윕(한 단). 시험종류 키로는 못 가른다.

재료 화면이 「마스터커브가 없는 DMA n건」 이라고 재촉할 때 변형률 스윕이 섞여
있으면 **할 수 없는 일을 남은 일로 적는 셈**이다. 목록에서 다시 재려면 시험마다
Parquet 을 열어야 하므로, 읽을 때 세어 칸에 둔다.

**옛 시험은 `NULL`(모름)로 남는다.** 0 으로 채우지 않는다 — 「못 한다」 로 읽혀서
그 시험이 화면에서 조용히 빠진다. `scripts/backfill_temperature_steps.py` 가
곡선을 열어 채운다.

Revision ID: 674ee685adee
Revises: bc089102090d
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "674ee685adee"
down_revision: Union[str, Sequence[str], None] = "bc089102090d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# **autogenerate 가 지우자고 한 것을 안 지운다.** `guide_sections` 의 trgm 색인은
# 손으로 만든 것이라 모델에 안 나타나고, 그래서 매번 「없어졌다」 로 잡힌다.


def upgrade() -> None:
    op.add_column(
        "test_runs", sa.Column("temperature_step_count", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("test_runs", "temperature_step_count")
