"""기준정보 축 `part` 의 이름을 「적용 부위」 → 「적용 파트」 로

**코드만 고치면 새 DB 에서만 바뀐다.** 축을 심는 코드는 이미 있는 slug 를
건너뛰므로(`if slug in existing: continue`), 운영·개발 DB 의 라벨은 옛 이름으로
남는다 — 그러면 새로 만든 환경과 쓰던 환경이 **다른 이름을 보인다.**

값은 안 건드린다. 바뀌는 것은 축의 이름뿐이다.

Revision ID: a3a079188c7f
Revises: f5ddedc5ac97
Create Date: 2026-08-30 17:06:54.544638

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3a079188c7f"
down_revision: Union[str, Sequence[str], None] = "f5ddedc5ac97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE vocabularies SET label = '적용 파트' "
            "WHERE slug = 'part' AND label = '적용 부위'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE vocabularies SET label = '적용 부위' "
            "WHERE slug = 'part' AND label = '적용 파트'"
        )
    )
