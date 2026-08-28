"""자동 등록은 커넥터가 고른다 — 기본은 승인 대기.

지금까지는 후보가 하나로 정해지면 승인 없이 바로 시험이 만들어졌다. 규칙이
「틀리게 맞으면」 엉뚱한 시편에 시험이 붙고, 사람은 나중에 목록을 훑을 때에야
안다 — 재료·시편이 「오타 하나로 유령이 생긴다」 며 보수적 기본값을 고른 것과
같은 맥락으로, 자동 등록도 기본을 승인 대기로 바꾼다.

`auto_register` 는 커넥터 단위다. 파일럿에서 대조 열이 한동안 전부 맞으면 **그
커넥터만** 켠다.

상태에 `suggested`(후보 하나 — 승인 대기)가 늘었다. 컬럼 변경은 없다 — 상태는
문자열이다.

기존 커넥터도 `false` 로 시작한다. 켜져 있던 동작이 꺼지는 쪽의 변화라 조용히
지나가지 않도록 릴리스 노트에 적는다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c9d4e2f7a1b6"
down_revision: Union[str, Sequence[str], None] = "b3e8f1a2c9d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "pipeline_connectors",
        sa.Column("auto_register", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("pipeline_connectors", "auto_register")
