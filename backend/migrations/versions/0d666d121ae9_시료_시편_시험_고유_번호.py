"""시료 · 시편 · 시험 고유 번호 — samples.code(S-) · specimens.code(P-) · test_runs.code(T-)

Revision ID: 0d666d121ae9
Revises: a337a744b3b6
Create Date: 2026-09-30

재료 번호(`a1c6f83d259b`, M-)를 넷으로 넓힌다(ADR 0043). 이름은 밑줄로 엮여 길고 재료
개명 · 다른 두께로 옮기기에 따라 바뀌어서, 말 · 문서 · 라벨이 가리킬 **안 바뀌는 손잡이**를
따로 둔다(사용자 요청 2026-09-30, 머리글자는 사용자가 골랐다).

재료와 같은 방식이다 — DB 시퀀스가 채번하고(server default), 기존 행은 created_at 순으로
백필한다. **등록 시각이 같으면 이름순이다** — 한 트랜잭션으로 넣은 묶음(이관 · 일괄 등록)은
`now()` 가 같아서, id(무작위 UUID)로 가르면 `__MD_01` · `__MD_02` 의 번호가 뒤섞인다. **지운 행도 번호를 받는다** — 옛 문서가 그 번호로 가리킬 수 있고, 번호는
어차피 재사용하지 않는다. 시퀀스에 maxvalue 999999 를 두는 까닭도 같다(lpad 는 넘치면
조용히 자른다). 손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0d666d121ae9"
down_revision: Union[str, Sequence[str], None] = "a337a744b3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (표, 머리글자, 시퀀스)
TABLES = (
    ("samples", "S", "sample_code_seq"),
    ("specimens", "P", "specimen_code_seq"),
    ("test_runs", "T", "test_run_code_seq"),
)


def upgrade() -> None:
    for table, prefix, sequence in TABLES:
        op.execute(f"create sequence {sequence} maxvalue 999999")
        op.add_column(table, sa.Column("code", sa.String(length=20), nullable=True))
        op.execute(
            f"""
            with ordered as (
                select id, row_number() over (order by created_at, record_name, id) as rn
                from {table}
            )
            update {table} t
            set code = '{prefix}-' || lpad(o.rn::text, 6, '0')
            from ordered o
            where t.id = o.id
            """
        )
        # 다음 채번이 백필의 다음 번호가 되게 맞춘다(is_called=false → nextval 이 그 값).
        op.execute(
            f"select setval('{sequence}', coalesce((select count(*) from {table}), 0) + 1, false)"
        )
        op.alter_column(
            table,
            "code",
            nullable=False,
            server_default=sa.text(
                f"'{prefix}-' || lpad(nextval('{sequence}')::text, 6, '0')"
            ),
        )
        op.create_unique_constraint(f"uq_{table}_code", table, ["code"])


def downgrade() -> None:
    for table, _prefix, sequence in reversed(TABLES):
        op.drop_constraint(f"uq_{table}_code", table, type_="unique")
        op.drop_column(table, "code")
        op.execute(f"drop sequence {sequence}")
