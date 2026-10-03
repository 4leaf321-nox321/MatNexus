"""문헌 값 검색 색인 — (물성 키, 값) (2026-10-03)

값으로 찾는 자리(`shared/property_search`)는 「물성 키 = X 이고 값이 low ~ high」 를 묻는다. 키
하나짜리 색인만 있으면 그 키의 값을 전부 읽고 거른다.

    ix_catalog_values_key_value   catalog_values(property_key, value_num)

Revision ID: b3f8a1c6d2e9
Revises: 9a4c2e7d5b18
Create Date: 2026-10-03 17:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3f8a1c6d2e9"
down_revision: str | Sequence[str] | None = "9a4c2e7d5b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_catalog_values_key_value",
        "catalog_values",
        ["property_key", "value_num"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_values_key_value", table_name="catalog_values")
