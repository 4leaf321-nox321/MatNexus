"""용도(적용 제품·부위)를 재료의 칸에서 표로 옮긴다.

한 재료가 여러 제품에 들어간다. 칸 하나로 받던 동안 사람들은 한 칸에 두 값을
밀어 넣었고, 그러면 기준정보가 그 덩어리를 새 용어로 만든다 — 「도어 이너」
로는 검색이 안 되고 「쓰는 곳」 도 갈라진다.

**값은 옮긴다.** 지우고 새로 적게 하지 않는다.

되돌리기(downgrade)는 **용도가 둘 이상인 재료가 있으면 거절한다.** 칸이 하나뿐
이라 어느 것을 남길지 정할 방법이 없고, 말없이 하나만 남기면 나머지는 영영
사라진다.

Revision ID: a1c4b70e2f18
Revises: cc213f8690a2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1c4b70e2f18"
down_revision = "cc213f8690a2"
branch_labels = None
depends_on = None

#: 옮길 짝 — (칸, term 칸, 축)
MOVED = (
    ("applied_product", "applied_product_term_id", "product"),
    ("applied_part", "applied_part_term_id", "part"),
)


def upgrade() -> None:
    op.create_table(
        "material_uses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "material_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materials.id"),
            nullable=False,
        ),
        sa.Column("axis", sa.String(length=20), nullable=False),
        sa.Column(
            "term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vocabulary_terms.id"),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "material_id", "axis", "term_id", name="uq_material_uses_axis_term"
        ),
    )
    op.create_index("ix_material_uses_material_id", "material_uses", ["material_id"])
    op.create_index("ix_material_uses_axis", "material_uses", ["axis"])
    op.create_index("ix_material_uses_term_id", "material_uses", ["term_id"])

    for column, term_column, axis in MOVED:
        # **term 이 붙은 것만 옮긴다.** 표는 기준정보를 거친 값만 담는다(ADR 0010).
        # 문자열만 있고 term 이 없는 행은 애초에 어긋난 것이고, `vocabulary.drift`
        # 가 세고 있던 대상이다 — 여기서 조용히 새 용어를 만들면 그 수가 0 이 되어
        # 어긋남이 있었다는 사실 자체가 사라진다.
        op.execute(
            sa.text(
                "INSERT INTO material_uses (id, material_id, axis, term_id, value, position)"
                " SELECT gen_random_uuid(), id, :axis, "
                f"{term_column}, NULLIF({column}, ''), 0"
                f" FROM materials WHERE {term_column} IS NOT NULL"
                f" AND NULLIF({column}, '') IS NOT NULL"
            ).bindparams(axis=axis)
        )

    for column, term_column, _axis in MOVED:
        op.drop_column("materials", term_column)
        op.drop_column("materials", column)


def downgrade() -> None:
    both = op.get_bind()
    for _column, _term_column, axis in MOVED:
        extra = both.execute(
            sa.text(
                "SELECT count(*) FROM ("
                " SELECT material_id FROM material_uses WHERE axis = :axis"
                " GROUP BY material_id HAVING count(*) > 1) AS many"
            ),
            {"axis": axis},
        ).scalar()
        if extra:
            raise RuntimeError(
                f"용도({axis})가 둘 이상인 재료가 {extra}건 있습니다. 칸이 하나뿐이라"
                " 어느 것을 남길지 정할 수 없습니다 — 먼저 하나로 줄이세요."
            )

    for column, term_column, axis in MOVED:
        op.add_column("materials", sa.Column(column, sa.String(length=100), nullable=True))
        op.add_column(
            "materials",
            sa.Column(term_column, postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_materials_{term_column}",
            "materials",
            "vocabulary_terms",
            [term_column],
            ["id"],
        )
        op.create_index(f"ix_materials_{term_column}", "materials", [term_column])
        op.execute(
            sa.text(
                f"UPDATE materials SET {column} = u.value, {term_column} = u.term_id"
                " FROM material_uses AS u"
                " WHERE u.material_id = materials.id AND u.axis = :axis"
            ).bindparams(axis=axis)
        )

    op.drop_table("material_uses")
