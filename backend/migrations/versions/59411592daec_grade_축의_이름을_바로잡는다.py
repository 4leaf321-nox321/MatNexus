"""Grade 축의 이름을 바로잡는다

Revision ID: 59411592daec
Revises: a37bf9bc1de3
Create Date: 2026-08-24 23:56:17.259629

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "59411592daec"
down_revision: Union[str, Sequence[str], None] = "a37bf9bc1de3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`강종` → `Grade`.

    **강종(鋼種)은 강(鋼)에만 쓰는 말인데 이 축은 재료군을 안 가린다.** 개발
    DB 에 Polymer/PP 의 Grade `S6F58` 이 있고, 그것을 강종이라 부르면 틀린 말이다.

    재료 화면은 처음부터 「Grade」로 부르고 있었다(`NewMaterialDialog`) —
    같은 축을 두 화면이 다르게 부르고 있었던 셈이다.

    **관리자가 일부러 바꾼 것은 안 건드린다.** 시드가 이미 있는 축을 손대지 않는
    것과 같은 판단이라(`ensure_builtin_vocabularies`), 옛 기본값인 `강종` 일
    때만 바꾼다.
    """
    op.execute(
        sa.text(
            "UPDATE vocabularies SET label = 'Grade' WHERE slug = 'grade' AND label = '강종'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE vocabularies SET label = '강종' WHERE slug = 'grade' AND label = 'Grade'"
        )
    )
