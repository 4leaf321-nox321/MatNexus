"""항목란이 방향을 가로지른다고 선언한다

카드 한 장은 방향 하나다(ADR 0034). 세 방향을 함께 써야 나오는 값은 그 규칙의
예외인데, 예외를 켜는 선언을 **코드로 만든 블록만** 할 수 있었다. 화면에서 만든
항목란에도 그 칸을 준다.

**기본은 꺼짐이다** — 이미 있는 항목란의 뜻이 이 마이그레이션으로 바뀌면 안 된다.

autogenerate 가 함께 낸 `catalog_links` 의 유니크 제약 이름 바꾸기는 **뺐다.**
이름만 다른 같은 제약이고, 그 표는 이 작업의 범위가 아니다.

Revision ID: 41c1f6f09646
Revises: 1e996db83b0b
Create Date: 2026-09-23 17:28:28.192952

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41c1f6f09646"
down_revision: str | Sequence[str] | None = "1e996db83b0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "card_blocks",
        sa.Column("cross_orientation", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("card_blocks", "cross_orientation")
