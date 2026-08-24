"""거래처 판매유형 시편규격 장비 축

Revision ID: 44c8ab691a47
Revises: 678637a142ba
Create Date: 2026-08-20 22:13:55.697570

"""

from typing import Sequence, Union

import logging

from alembic import op
import sqlalchemy as sa

from app.shared.text import clean, compare_key

logger = logging.getLogger("alembic.runtime.migration")


# revision identifiers, used by Alembic.
revision: str = "44c8ab691a47"
down_revision: Union[str, Sequence[str], None] = "678637a142ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- 축 심기와 백필 ---------------------------------------------------------
#
# 1단계(제조사)에서 한 것을 **한 벌의 함수로** 만든다. 축마다 베껴 쓰면 그중
# 하나만 고쳐지는 일이 생긴다 — 시료 폼이 갈렸던 것과 같은 실패다.
#
# `operator`(시험자)는 뺐다. 시험을 돌린 사람이 시스템 계정이 없을 수 있고,
# 계정과 이을지 정해지지 않았다. 집계 축으로 쓸 계획이 없으면 어휘를 만드는
# 비용이 더 크다.

VOCABULARIES = [
    # slug, label, sort_order.  **전부 open** — `closed` 는 만들어 두고 안 켠다.
    ("vendor", "거래처", 20),
    ("sales_type", "판매 유형", 30),
    ("specimen_standard", "시편 규격", 40),
    ("instrument", "장비", 50),
]

#: (축, 표, 문자열 컬럼, FK 컬럼).
#:
#: **유통사와 주 벤더가 한 축을 공유한다** — 같은 회사가 로트에 따라 둘 중 어느
#: 쪽도 된다. 축을 나누면 같은 회사가 두 목록에 따로 쌓인다.
COLUMNS = [
    ("vendor", "samples", "distributor", "distributor_term_id"),
    ("vendor", "samples", "primary_vendor", "primary_vendor_term_id"),
    ("sales_type", "samples", "sales_type", "sales_type_term_id"),
    ("specimen_standard", "specimens", "standard", "standard_term_id"),
    ("instrument", "test_runs", "instrument", "instrument_term_id"),
]


def _seed_and_backfill() -> None:
    bind = op.get_bind()
    ids: dict[str, object] = {}
    for slug, label, order in VOCABULARIES:
        bind.execute(
            sa.text(
                "INSERT INTO vocabularies (id, slug, label, entry_policy, sort_order)"
                " VALUES (gen_random_uuid(), :slug, :label, 'open', :order)"
            ),
            {"slug": slug, "label": label, "order": order},
        )
        ids[slug] = bind.execute(
            sa.text("SELECT id FROM vocabularies WHERE slug = :slug"), {"slug": slug}
        ).scalar_one()

    for slug, table, text_column, fk_column in COLUMNS:
        vocabulary_id = ids[slug]

        # 값 만들기. **비교키로 묶는다** — 파이썬 정규화(NFKC·제로폭·공백)를
        # 쓰므로 SQL 의 lower(btrim()) 보다 강하다.
        rows = (
            bind.execute(
                sa.text(
                    f"SELECT DISTINCT {text_column} FROM {table}"
                    f" WHERE {text_column} IS NOT NULL AND {text_column} <> ''"
                )
            )
            .scalars()
            .all()
        )

        for raw in rows:
            key = compare_key(raw)
            value = clean(raw)
            if not key or value is None:
                continue
            # 같은 축에 이미 있으면(유통사·주 벤더가 같은 회사) 건너뛴다.
            existing = bind.execute(
                sa.text(
                    "SELECT id FROM vocabulary_terms"
                    " WHERE vocabulary_id = :vid AND normalized = :key"
                ),
                {"vid": vocabulary_id, "key": key},
            ).scalar()
            if existing is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO vocabulary_terms"
                        " (id, vocabulary_id, value, normalized, status, usage_count)"
                        " VALUES (gen_random_uuid(), :vid, :value, :key, 'active', 0)"
                    ),
                    {"vid": vocabulary_id, "value": value, "key": key},
                )

        filled = bind.execute(
            sa.text(
                f"""
                UPDATE {table} AS x
                   SET {fk_column} = t.id
                  FROM vocabulary_terms AS t
                 WHERE t.vocabulary_id = :vid
                   AND t.normalized = lower(btrim(x.{text_column}))
                   AND x.{text_column} IS NOT NULL
                """
            ),
            {"vid": vocabulary_id},
        ).rowcount
        logger.info("%s.%s → %s 어휘: %s건 연결", table, text_column, slug, filled)

        leftover = (
            bind.execute(
                sa.text(
                    f"SELECT DISTINCT {text_column} FROM {table}"
                    f" WHERE {text_column} IS NOT NULL AND {text_column} <> ''"
                    f"   AND {fk_column} IS NULL"
                )
            )
            .scalars()
            .all()
        )
        for value in leftover:
            logger.warning(
                "%s.%s 의 %r 를 어휘로 못 옮겼습니다 — 눈에 안 보이는 문자가 있을 수 "
                "있습니다. 수정 화면에서 다시 고르세요.",
                table,
                text_column,
                value,
            )

    # usage_count. **한 축을 여러 컬럼이 가리키므로 합산한다**(거래처).
    for slug, _label, _order in VOCABULARIES:
        parts = [
            f"(SELECT count(*) FROM {table} WHERE {fk} = t.id)"
            for axis, table, _text, fk in COLUMNS
            if axis == slug
        ]
        bind.execute(
            sa.text(
                f"UPDATE vocabulary_terms AS t SET usage_count = {' + '.join(parts)}"
                f" WHERE t.vocabulary_id = :vid"
            ),
            {"vid": ids[slug]},
        )


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("samples", sa.Column("distributor_term_id", sa.UUID(), nullable=True))
    op.add_column("samples", sa.Column("primary_vendor_term_id", sa.UUID(), nullable=True))
    op.add_column("samples", sa.Column("sales_type_term_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_samples_distributor_term_id"),
        "samples",
        ["distributor_term_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_samples_primary_vendor_term_id"),
        "samples",
        ["primary_vendor_term_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_samples_sales_type_term_id"), "samples", ["sales_type_term_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_samples_distributor_term_id_vocabulary_terms"),
        "samples",
        "vocabulary_terms",
        ["distributor_term_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_samples_primary_vendor_term_id_vocabulary_terms"),
        "samples",
        "vocabulary_terms",
        ["primary_vendor_term_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_samples_sales_type_term_id_vocabulary_terms"),
        "samples",
        "vocabulary_terms",
        ["sales_type_term_id"],
        ["id"],
    )
    op.add_column("specimens", sa.Column("standard_term_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_specimens_standard_term_id"), "specimens", ["standard_term_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_specimens_standard_term_id_vocabulary_terms"),
        "specimens",
        "vocabulary_terms",
        ["standard_term_id"],
        ["id"],
    )
    op.add_column("test_runs", sa.Column("instrument_term_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_test_runs_instrument_term_id"),
        "test_runs",
        ["instrument_term_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_test_runs_instrument_term_id_vocabulary_terms"),
        "test_runs",
        "vocabulary_terms",
        ["instrument_term_id"],
        ["id"],
    )
    # ### end Alembic commands ###
    _seed_and_backfill()


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("fk_test_runs_instrument_term_id_vocabulary_terms"),
        "test_runs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_test_runs_instrument_term_id"), table_name="test_runs")
    op.drop_column("test_runs", "instrument_term_id")
    op.drop_constraint(
        op.f("fk_specimens_standard_term_id_vocabulary_terms"), "specimens", type_="foreignkey"
    )
    op.drop_index(op.f("ix_specimens_standard_term_id"), table_name="specimens")
    op.drop_column("specimens", "standard_term_id")
    op.drop_constraint(
        op.f("fk_samples_sales_type_term_id_vocabulary_terms"), "samples", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_samples_primary_vendor_term_id_vocabulary_terms"),
        "samples",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_samples_distributor_term_id_vocabulary_terms"), "samples", type_="foreignkey"
    )
    op.drop_index(op.f("ix_samples_sales_type_term_id"), table_name="samples")
    op.drop_index(op.f("ix_samples_primary_vendor_term_id"), table_name="samples")
    op.drop_index(op.f("ix_samples_distributor_term_id"), table_name="samples")
    op.drop_column("samples", "sales_type_term_id")
    op.drop_column("samples", "primary_vendor_term_id")
    op.drop_column("samples", "distributor_term_id")
    # ### end Alembic commands ###
