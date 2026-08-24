"""시험 없는 카드

`property_cards.test_type_id`·`orientation` 을 비울 수 있게 한다.

선언 물성만으로 만든 카드가 그렇다(ADR 0016). 시험이 하나도 없는 재료 —
개발 DB 기준 94개 중 14개 — 는 대표 곡선이 없어서 지금까지 카드를 만들 길이
아예 없었고, 그래서 선언 물성을 채워도 덱까지 가지 못했다.

**자리표시를 넣지 않는 이유.** 아무 시험종류나 채우면 그 카드가 인장시험에서
나온 것처럼 보이고, 덱을 받은 사람은 그 숫자를 잰 값으로 읽는다. `orientation`
에 `"—"` 를 넣으면 목록이 그것을 방향 이름으로 줄 세운다.

Revision ID: 198f219ea68e
Revises: 02306966487a
Create Date: 2026-08-25 08:18:20.876576

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "198f219ea68e"
down_revision: Union[str, Sequence[str], None] = "02306966487a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("property_cards", "test_type_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column(
        "property_cards", "orientation", existing_type=sa.VARCHAR(length=10), nullable=True
    )


def downgrade() -> None:
    """Downgrade schema.

    **선언 물성 카드가 하나라도 있으면 여기서 멈춘다.** 되돌리려면 그 카드들을
    지워야 하는데, 그 판단은 마이그레이션이 할 것이 아니다 — 이 값으로 해석이
    돌았을 수 있고(그래서 `published_at` 을 남긴다), 조용히 지우면 그 흔적까지
    사라진다. 무엇을 지워야 하는지 사람에게 말하고 멈춘다.
    """
    stranded = (
        op.get_bind()
        .execute(sa.text("select count(*) from property_cards where test_type_id is null"))
        .scalar_one()
    )
    if stranded:
        raise RuntimeError(
            f"시험 없는 물성 카드가 {stranded}장 있습니다. 되돌리려면 먼저 그 카드들을 "
            f"지우세요: delete from property_cards where test_type_id is null"
        )
    op.alter_column(
        "property_cards", "orientation", existing_type=sa.VARCHAR(length=10), nullable=False
    )
    op.alter_column("property_cards", "test_type_id", existing_type=sa.UUID(), nullable=False)
