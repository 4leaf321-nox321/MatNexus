"""선언 물성이 온도 표를 든다

한 줄에 값 하나였던 것을 `points` 배열로 옮긴다.

    {value_si, temperature_k, ...}  →  {points: [{value_si, temperature_k}], ...}

강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어지고, 열간
성형·용접·화재 해석은 그 곡선이 필요하다. 그렇다고 줄을 여럿 두면 「한 항목은
한 줄」이 깨져 카드가 어느 것을 쓸지 못 정한다 — **항목은 하나이고 그 하나가
온도에 따라 변할 뿐**이므로 줄 안에 점을 넣는다.

**옛 값이 살아남는다.** 온도를 처음부터 받아 두었으므로(ADR 0016 1단계) 옮길
때 지어낼 것이 없다 — 있던 온도가 그 점의 온도가 된다.

Revision ID: cc213f8690a2
Revises: 9efc6878b742
Create Date: 2026-08-25 13:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cc213f8690a2"
down_revision: Union[str, Sequence[str], None] = "9efc6878b742"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: 재료와 시료가 같은 모양을 쓴다(ADR 0016). 한쪽만 옮기면 읽는 코드가 갈래를
#: 둬야 하고, 그 갈래는 언젠가 한쪽만 고쳐진다.
TABLES = ("materials", "samples")

FORWARD = """
update {table} set declared_properties = (
    select coalesce(jsonb_agg(
        (row - 'value_si' - 'temperature_k')
        || jsonb_build_object('points', jsonb_build_array(
               jsonb_build_object(
                   'value_si', row -> 'value_si',
                   'temperature_k', row -> 'temperature_k'
               )
           ))
    ), '[]'::jsonb)
    from jsonb_array_elements(declared_properties) as row
)
where jsonb_array_length(coalesce(declared_properties, '[]'::jsonb)) > 0
  and declared_properties -> 0 ? 'value_si'
"""

#: 되돌릴 때는 **첫 점만 남는다.** 여러 온도를 적어 둔 줄은 그 표가 사라지므로
#: 되돌리기 전에 알아야 한다 — 아래 `downgrade` 가 그것을 먼저 센다.
BACKWARD = """
update {table} set declared_properties = (
    select coalesce(jsonb_agg(
        (row - 'points')
        || jsonb_build_object(
               'value_si', row -> 'points' -> 0 -> 'value_si',
               'temperature_k', row -> 'points' -> 0 -> 'temperature_k'
           )
    ), '[]'::jsonb)
    from jsonb_array_elements(declared_properties) as row
)
where jsonb_array_length(coalesce(declared_properties, '[]'::jsonb)) > 0
  and declared_properties -> 0 ? 'points'
"""


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.execute(sa.text(FORWARD.format(table=table)))


def downgrade() -> None:
    """Downgrade schema.

    **점이 둘 이상인 줄이 있으면 멈춘다.** 되돌리면 그 표가 첫 점만 남기고
    사라지는데, 그것은 사람이 적어 둔 것을 조용히 지우는 일이다. 무엇을 잃는지
    말하고 멈춘다.
    """
    bind = op.get_bind()
    for table in TABLES:
        stranded = bind.execute(
            sa.text(f"""
            select count(*) from {table}, jsonb_array_elements(declared_properties) as row
            where jsonb_array_length(coalesce(row -> 'points', '[]'::jsonb)) > 1
            """)
        ).scalar_one()
        if stranded:
            raise RuntimeError(
                f"{table} 에 온도 표를 든 선언 물성이 {stranded}줄 있습니다. 되돌리면 "
                f"첫 점만 남고 나머지 온도의 값이 사라집니다 — 사람이 적어 둔 것을 "
                f"조용히 지울 수는 없습니다. 먼저 그 줄들을 손보세요."
            )
    for table in TABLES:
        op.execute(sa.text(BACKWARD.format(table=table)))
