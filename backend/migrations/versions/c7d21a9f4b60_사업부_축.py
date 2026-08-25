"""시험에 사업부를 붙이고, 기준정보에 그 축을 심는다.

**부서(workspace)와 다르다.** 부서는 누가 볼 수 있는가를 정하는 권한의 축이고,
사업부는 누가 낸 데이터인가를 적는 이름표다. 한 부서 계정으로 여러 사업부의
판을 올리는 일이 실제로 있고, 그때 부서로는 그 둘을 못 가른다.

자유 문자열로 두지 않는 이유는 나머지 축과 같다 — `전장`·`전장사업부`·
`전장 사업부` 가 갈리면 「사업부별로 몇 건」에 답이 셋 나온다.

백필할 것이 없다. 전에 없던 값이라 기존 시험은 사업부가 비어 있고, 그것이 맞다 —
**모르는 것을 지어내지 않는다.**

Revision ID: c7d21a9f4b60
Revises: a1c4b70e2f18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d21a9f4b60"
down_revision = "a1c4b70e2f18"
branch_labels = None
depends_on = None

SLUG = "division"
LABEL = "사업부"
#: 장비(50) 바로 앞. 시험을 적을 때 묻는 순서와 같게 둔다.
ORDER = 45


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("division", sa.String(length=100), nullable=True))
    op.add_column("test_runs", sa.Column("division_term_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_test_runs_division_term_id"), "test_runs", ["division_term_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_test_runs_division_term_id_vocabulary_terms"),
        "test_runs",
        "vocabulary_terms",
        ["division_term_id"],
        ["id"],
    )

    # `open` 이다 — 사업부는 부서가 스스로 늘린다. 관리자가 미리 다 적어 둘 수
    # 있는 목록이 아니고, 못 고르면 사람은 비워 두거나 메모에 적는다.
    op.execute(
        sa.text(
            "INSERT INTO vocabularies (id, slug, label, entry_policy, sort_order)"
            " VALUES (gen_random_uuid(), :slug, :label, 'open', :order)"
            " ON CONFLICT (slug) DO NOTHING"
        ).bindparams(slug=SLUG, label=LABEL, order=ORDER)
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_test_runs_division_term_id_vocabulary_terms"), "test_runs", type_="foreignkey"
    )
    op.drop_index(op.f("ix_test_runs_division_term_id"), table_name="test_runs")
    op.drop_column("test_runs", "division_term_id")
    op.drop_column("test_runs", "division")

    # **심은 축도 걷어낸다.** 안 걷으면 되돌린 뒤에도 관리 화면에 아무도 안
    # 가리키는 축이 남는다. 컬럼이 사라진 뒤라 이 값들을 가리키는 것은 없다.
    for table in ("vocabulary_aliases", "vocabulary_terms"):
        op.execute(
            sa.text(
                f"DELETE FROM {table} WHERE vocabulary_id IN"
                " (SELECT id FROM vocabularies WHERE slug = :slug)"
            ).bindparams(slug=SLUG)
        )
    op.execute(sa.text("DELETE FROM vocabularies WHERE slug = :slug").bindparams(slug=SLUG))
