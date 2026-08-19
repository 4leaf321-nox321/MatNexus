"""시편 규격을 시험 조건에서 시편으로

**규격은 자를 때 정해진다.** 시험할 때 정하는 것이 아니고, 게이지 길이·폭을
정하는 쪽이다 — 정해지는 값(치수)은 시편에, 정하는 값(규격)은 시험에 있어
인과가 반대로 놓여 있었다.

장비 파일에도 없다. Zwick `.tra` 가 주는 시편 정보는 번호·두께 a0·폭 b0 셋뿐이고
(업로드된 112건 전수 확인), 규격은 사람이 아는 값이다. 시험마다 넣게 하면 같은
시편의 시험 두 건에 다른 규격이 적히는 것을 막을 방법이 없다.

## 갈리는 경우

한 시편의 시험들이 서로 다른 규격을 적었으면 **아무것도 안 옮긴다.** 하나를
골라 올리면 나머지는 소리 없이 사라진다. 사람이 보고 정해야 하므로 로그로
남긴다 — 푸아송비를 옮길 때와 같은 규칙이다.

옮긴 뒤 `conditions` 에서 그 키를 지우고, 시험 종류의 조건 항목 정의도 지운다.
남겨 두면 업로드 창에 칸이 계속 뜨고, **같은 값을 두 자리에 넣게 된다.**

Revision ID: 272ae2dcc452
Revises: 9ea06ea843ea
Create Date: 2026-08-19

"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "272ae2dcc452"
down_revision: Union[str, Sequence[str], None] = "9ea06ea843ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

KEY = "specimen_standard"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("specimens", sa.Column("standard", sa.String(length=100), nullable=True))
    bind = op.get_bind()

    moved = bind.execute(
        sa.text(
            """
            UPDATE specimens AS s
               SET standard = agreed.value
              FROM (
                    SELECT r.specimen_id,
                           MIN(r.conditions ->> :key) AS value
                      FROM test_runs AS r
                     WHERE r.conditions ->> :key IS NOT NULL
                       AND r.conditions ->> :key <> ''
                     GROUP BY r.specimen_id
                    HAVING COUNT(DISTINCT r.conditions ->> :key) = 1
                   ) AS agreed
             WHERE s.id = agreed.specimen_id
            """
        ),
        {"key": KEY},
    ).rowcount
    logger.info("시편 규격을 시편으로 옮김: %s건", moved)

    conflicts = bind.execute(
        sa.text(
            """
            SELECT s.record_name,
                   STRING_AGG(DISTINCT r.conditions ->> :key, ', ')
              FROM test_runs AS r
              JOIN specimens AS s ON s.id = r.specimen_id
             WHERE r.conditions ->> :key IS NOT NULL
               AND r.conditions ->> :key <> ''
             GROUP BY s.id, s.record_name
            HAVING COUNT(DISTINCT r.conditions ->> :key) > 1
            """
        ),
        {"key": KEY},
    ).all()
    for name, values in conflicts:
        logger.warning(
            "시편 규격이 시험마다 다릅니다 — 옮기지 않았습니다: %s (%s). "
            "시편 수정에서 쓸 값을 정하세요.",
            name,
            values,
        )

    # 조건에서 지운다. 두 자리에 있으면 어느 쪽이 맞는지 물어야 한다.
    bind.execute(
        sa.text("UPDATE test_runs SET conditions = conditions - :key WHERE conditions ? :key"),
        {"key": KEY},
    )
    # 입력 단위 기록도 함께(텍스트라 단위는 없지만, 남으면 유령 키가 된다).
    bind.execute(
        sa.text(
            "UPDATE test_runs SET input_units = input_units - :key WHERE input_units ? :key"
        ),
        {"key": KEY},
    )
    removed = bind.execute(
        sa.text("DELETE FROM test_condition_fields WHERE key = :key"), {"key": KEY}
    ).rowcount
    logger.info("시험 종류의 '시편 규격' 조건 항목 삭제: %s건", removed)


def downgrade() -> None:
    """Downgrade schema.

    시편의 값을 그 시편의 모든 시험에 되돌려 적고, 조건 항목 정의도 되살린다.
    갈렸던 시편은 애초에 올라가지 않았으므로 되돌릴 값이 없다 — 그 값은 이미
    지워진 뒤다.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO test_condition_fields
                   (id, test_type_id, key, label, value_type, dimension, si_unit,
                    choices, is_required, sort_order)
            SELECT gen_random_uuid(), t.id, :key, '시편 규격', 'text', NULL, NULL,
                   NULL, false, 90
              FROM test_types AS t
             WHERE t.key = 'tensile'
            """
        ),
        {"key": KEY},
    )
    bind.execute(
        sa.text(
            """
            UPDATE test_runs AS r
               SET conditions = r.conditions || jsonb_build_object(:key, s.standard)
              FROM specimens AS s
             WHERE s.id = r.specimen_id
               AND s.standard IS NOT NULL
            """
        ),
        {"key": KEY},
    )
    op.drop_column("specimens", "standard")
