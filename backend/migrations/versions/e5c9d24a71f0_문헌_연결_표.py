"""문헌 연결 표 — 사내 재료가 카탈로그 재료를 가리킨다

Revision ID: e5c9d24a71f0
Revises: d8a3f61c07b2
Create Date: 2026-09-06

사내 재료 상세가 문헌 값을 나란히 보여 주고 채택(채우기)의 기본 대상이 되게
하는 1:1 참조. materials 표는 불변(ADR 0027) — 연결은 카탈로그 쪽 표로 둔다.
재료가 지워지면(CASCADE) 연결도 사라진다. 손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5c9d24a71f0"
down_revision: Union[str, Sequence[str], None] = "d8a3f61c07b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["catalog_material_id"], ["catalog_materials.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", name="uq_catalog_links_material"),
    )
    op.create_index(
        "ix_catalog_links_catalog_material_id", "catalog_links", ["catalog_material_id"]
    )


def downgrade() -> None:
    op.drop_table("catalog_links")
