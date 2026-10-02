"""물성 정의문의 씨앗 지문 (ADR 0050)

문헌 물성 정의 271종의 정의문(`description`)이 원본부터 비어 있었다. 씨앗이 채우고, 자료
관리자가 고친 것은 배포가 안 덮게 한다 — 「아무도 안 고쳤다」 를 가르는 칸이다.

    catalog_definitions.description_seed_digest   씨앗이 마지막으로 쓴 정의문의 sha256.
                                                  사람이 쓴 정의문이면 지금 정의문과 다르다

Revision ID: 8b3d5f7a9c21
Revises: 5c2e8d41a7f3
Create Date: 2026-10-02 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b3d5f7a9c21"
down_revision: str | Sequence[str] | None = "5c2e8d41a7f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_definitions",
        sa.Column("description_seed_digest", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_definitions", "description_seed_digest")
