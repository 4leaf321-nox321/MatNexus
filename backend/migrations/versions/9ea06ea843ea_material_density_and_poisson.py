"""푸아송비를 시료에서 재료로, 재료에 공칭 밀도

푸아송비는 **재료의 성질이다.** 같은 강종의 다른 로트가 푸아송비가 다르지
않고, 인장시험은 이 값을 주지도 않는다(횡변형을 따로 재야 한다). 시료에 두면
로트 5개에 0.3 을 다섯 번 적어야 하고, 그중 하나만 0.28 로 고쳐지면 같은
재료가 두 값을 갖는다.

밀도는 **양쪽에 둔다.** 강판은 로트가 달라도 7850 이지만 복합재·발포재·소결재는
로트마다 실제로 다르고 그건 재는 값이다. 재료에 공칭, 시료에 실측.

## 옮기면서 값이 갈리는 경우

한 재료의 시료들이 서로 다른 푸아송비를 갖고 있으면 **아무것도 안 옮긴다.**
하나를 골라 올리면 나머지는 소리 없이 사라지고, 그 사실이 어디에도 안 남는다.
그런 재료는 사람이 보고 정해야 하므로 로그로 남긴다 — 마이그레이션이 조용히
결정을 내리는 것이 가장 나쁘다.

Revision ID: 9ea06ea843ea
Revises: 297cac8eb557
Create Date: 2026-08-18 22:21:28.538179

"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ea06ea843ea"
down_revision: Union[str, Sequence[str], None] = "297cac8eb557"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("materials", sa.Column("density_si", sa.Float(), nullable=True))
    op.add_column("materials", sa.Column("poisson_ratio", sa.Float(), nullable=True))

    bind = op.get_bind()

    # 값이 하나로 모이는 재료만 올린다.
    moved = bind.execute(
        sa.text(
            """
            UPDATE materials AS m
               SET poisson_ratio = agreed.value
              FROM (
                    SELECT s.material_id,
                           MIN(s.poisson_ratio) AS value
                      FROM samples AS s
                     WHERE s.poisson_ratio IS NOT NULL
                     GROUP BY s.material_id
                    HAVING COUNT(DISTINCT s.poisson_ratio) = 1
                   ) AS agreed
             WHERE m.id = agreed.material_id
            """
        )
    ).rowcount
    logger.info("푸아송비를 재료로 옮김: %s건", moved)

    # 갈리는 것은 옮기지 않고 이름을 남긴다. 사람이 정해야 한다.
    conflicts = bind.execute(
        sa.text(
            """
            SELECT m.record_name,
                   STRING_AGG(DISTINCT s.poisson_ratio::text, ', ' ORDER BY s.poisson_ratio::text)
              FROM samples AS s
              JOIN materials AS m ON m.id = s.material_id
             WHERE s.poisson_ratio IS NOT NULL
             GROUP BY m.id, m.record_name
            HAVING COUNT(DISTINCT s.poisson_ratio) > 1
            """
        )
    ).all()
    for name, values in conflicts:
        logger.warning(
            "푸아송비가 시료마다 다릅니다 — 옮기지 않았습니다: %s (%s). "
            "재료 수정에서 쓸 값을 정하세요.",
            name,
            values,
        )

    op.drop_column("samples", "poisson_ratio")


def downgrade() -> None:
    """Downgrade schema.

    재료의 값을 그 재료의 모든 시료에 되돌려 적는다. 갈렸던 재료는 애초에
    올라가지 않았으므로 되돌릴 값도 없다 — 시료 값은 이미 지워진 뒤라 복구되지
    않는다. 되돌리기 전에 백업을 확인해야 하는 이유다.
    """
    op.add_column(
        "samples",
        sa.Column("poisson_ratio", sa.DOUBLE_PRECISION(precision=53), nullable=True),
    )
    op.get_bind().execute(
        sa.text(
            """
            UPDATE samples AS s
               SET poisson_ratio = m.poisson_ratio
              FROM materials AS m
             WHERE m.id = s.material_id
               AND m.poisson_ratio IS NOT NULL
            """
        )
    )
    op.drop_column("materials", "poisson_ratio")
    op.drop_column("materials", "density_si")
