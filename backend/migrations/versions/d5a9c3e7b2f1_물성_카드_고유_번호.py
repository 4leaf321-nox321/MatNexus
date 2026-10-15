"""물성 카드 고유 번호 — property_cards.code(C-)

Revision ID: d5a9c3e7b2f1
Revises: c4d7e2a9f1b3
Create Date: 2026-10-16

재료 · 시료 · 시편 · 시험 번호(ADR 0043)를 카드로 넓힌다(사용자 요청 2026-10-16, 머리글자 C 는
사용자가 골랐다). 카드 이름은 사람이 짓고 고칠 수 있고 같은 재료에 「인장 MD」 가 여러 장이라,
덱 머리 · 메신저 · 확정 요청이 한 장을 가리킬 **안 바뀌는 손잡이**가 따로 있어야 한다.

같은 방식이다 — DB 시퀀스가 채번하고(server default), 기존 행은 created_at 순, **등록 시각이
같으면 이름순**으로 백필한다(한 트랜잭션으로 지은 묶음 카드가 id 순으로 뒤섞이지 않게).
시퀀스에 maxvalue 999999(lpad 는 넘치면 조용히 자른다). 손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a9c3e7b2f1"
down_revision: Union[str, Sequence[str], None] = "c4d7e2a9f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "property_cards"
PREFIX = "C"
SEQUENCE = "property_card_code_seq"


def upgrade() -> None:
    op.execute(f"create sequence {SEQUENCE} maxvalue 999999")
    op.add_column(TABLE, sa.Column("code", sa.String(length=20), nullable=True))
    op.execute(
        f"""
        with ordered as (
            select id, row_number() over (order by created_at, label, id) as rn
            from {TABLE}
        )
        update {TABLE} t
        set code = '{PREFIX}-' || lpad(o.rn::text, 6, '0')
        from ordered o
        where t.id = o.id
        """
    )
    # 다음 채번이 백필의 다음 번호가 되게 맞춘다(is_called=false → nextval 이 그 값).
    op.execute(
        f"select setval('{SEQUENCE}', coalesce((select count(*) from {TABLE}), 0) + 1, false)"
    )
    op.alter_column(
        TABLE,
        "code",
        nullable=False,
        server_default=sa.text(f"'{PREFIX}-' || lpad(nextval('{SEQUENCE}')::text, 6, '0')"),
    )
    op.create_unique_constraint(f"uq_{TABLE}_code", TABLE, ["code"])


def downgrade() -> None:
    op.drop_constraint(f"uq_{TABLE}_code", TABLE, type_="unique")
    op.drop_column(TABLE, "code")
    op.execute(f"drop sequence {SEQUENCE}")
