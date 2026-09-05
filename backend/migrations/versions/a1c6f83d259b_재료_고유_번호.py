"""재료 고유 번호 — materials.code (M-000123)

Revision ID: a1c6f83d259b
Revises: f2b8c5d94a17
Create Date: 2026-09-06

`record_name` 은 기준정보 개명이 연쇄로 바꾸는 설계라(ADR 0004), 문서·라벨이
재료를 지칭할 **안 바뀌는 손잡이**를 따로 둔다(사용자 결정 2026-09-05).
DB 시퀀스가 채번하고(server default — 만드는 코드가 몰라도 붙는다), 기존 행은
created_at 순으로 백필한다. 번호는 재사용하지 않는다.

시퀀스에 maxvalue 999999 를 두는 이유: lpad 는 6자리를 넘으면 **조용히
자른다** — 넘치면 시끄럽게 실패하는 쪽을 고른다(models.py 의 설명 참조).
손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c6f83d259b"
down_revision: Union[str, Sequence[str], None] = "f2b8c5d94a17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("create sequence material_code_seq maxvalue 999999")
    op.add_column("materials", sa.Column("code", sa.String(length=20), nullable=True))
    # 백필 — created_at 순(같으면 id). 지워진 재료도 번호를 받는다: 옛 문서가
    # 그 번호로 가리킬 수 있어야 하고, 번호는 어차피 재사용하지 않는다.
    op.execute(
        """
        with ordered as (
            select id, row_number() over (order by created_at, id) as rn
            from materials
        )
        update materials m
        set code = 'M-' || lpad(o.rn::text, 6, '0')
        from ordered o
        where m.id = o.id
        """
    )
    # 다음 채번이 백필의 다음 번호가 되게 맞춘다 (is_called=false → nextval 이 그 값).
    op.execute(
        "select setval('material_code_seq',"
        " coalesce((select count(*) from materials), 0) + 1, false)"
    )
    op.alter_column(
        "materials",
        "code",
        nullable=False,
        server_default=sa.text("'M-' || lpad(nextval('material_code_seq')::text, 6, '0')"),
    )
    op.create_unique_constraint("uq_materials_code", "materials", ["code"])


def downgrade() -> None:
    op.drop_constraint("uq_materials_code", "materials", type_="unique")
    op.drop_column("materials", "code")
    op.execute("drop sequence material_code_seq")
