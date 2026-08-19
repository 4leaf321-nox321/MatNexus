"""적용 제품·부위를 시료에서 재료로

**용도는 재료의 성질이다.** 시료에 두면 "도어 이너용 재료가 뭐가 있나" 를 물을
때 로트를 전부 뒤져야 하고, 같은 재료의 로트 다섯 개에 같은 용도를 다섯 번 적게
된다 — 푸아송비를 올린 것과 같은 이유다.

로트가 실제로 어디로 갔는지는 생산관리의 일이고 이 시스템의 질문이 아니다.

## 갈리는 경우

한 재료의 시료들이 서로 다른 용도를 적었으면 **아무것도 안 옮긴다.** 하나를
골라 올리면 나머지는 소리 없이 사라진다. 두 필드를 **각각** 판정한다 — 제품은
같은데 부위만 갈리는 경우가 있다.

Revision ID: b371627c5768
Revises: 272ae2dcc452
Create Date: 2026-08-19

"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b371627c5768"
down_revision: Union[str, Sequence[str], None] = "272ae2dcc452"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

FIELDS = (("applied_product", "적용 제품"), ("applied_part", "적용 부위"))


def upgrade() -> None:
    """Upgrade schema."""
    for column, _ in FIELDS:
        op.add_column("materials", sa.Column(column, sa.String(length=100), nullable=True))

    bind = op.get_bind()
    for column, label in FIELDS:
        moved = bind.execute(
            sa.text(
                f"""
                UPDATE materials AS m
                   SET {column} = agreed.value
                  FROM (
                        SELECT s.material_id, MIN(s.{column}) AS value
                          FROM samples AS s
                         WHERE s.{column} IS NOT NULL AND s.{column} <> ''
                         GROUP BY s.material_id
                        HAVING COUNT(DISTINCT s.{column}) = 1
                       ) AS agreed
                 WHERE m.id = agreed.material_id
                """  # 컬럼 이름은 위 FIELDS 상수에서만 온다 — 사용자 입력이 아니다
            )
        ).rowcount
        logger.info("%s 를 재료로 옮김: %s건", label, moved)

        conflicts = bind.execute(
            sa.text(
                f"""
                SELECT m.record_name, STRING_AGG(DISTINCT s.{column}, ', ')
                  FROM samples AS s
                  JOIN materials AS m ON m.id = s.material_id
                 WHERE s.{column} IS NOT NULL AND s.{column} <> ''
                 GROUP BY m.id, m.record_name
                HAVING COUNT(DISTINCT s.{column}) > 1
                """  # 컬럼 이름은 FIELDS 상수에서만 온다
            )
        ).all()
        for name, values in conflicts:
            logger.warning(
                "%s 가 시료마다 다릅니다 — 옮기지 않았습니다: %s (%s). "
                "재료 수정에서 쓸 값을 정하세요.",
                label,
                name,
                values,
            )

    for column, _ in FIELDS:
        op.drop_column("samples", column)


def downgrade() -> None:
    """Downgrade schema.

    재료의 값을 그 재료의 모든 시료에 되돌려 적는다. 갈렸던 재료는 애초에
    올라가지 않았으므로 되돌릴 값이 없다.
    """
    bind = op.get_bind()
    for column, _ in FIELDS:
        op.add_column("samples", sa.Column(column, sa.String(length=100), nullable=True))
        bind.execute(
            sa.text(
                f"""
                UPDATE samples AS s
                   SET {column} = m.{column}
                  FROM materials AS m
                 WHERE m.id = s.material_id AND m.{column} IS NOT NULL
                """  # 컬럼 이름은 FIELDS 상수에서만 온다
            )
        )
        op.drop_column("materials", column)
