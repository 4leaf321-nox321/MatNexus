"""문헌 카탈로그 — 원본에서 사라진 행을 표시한다 (2026-10-04)

이관(`import_materialtwin.py`)은 배포마다 돌고 **지우지 않는다.** 원본 스냅샷에서 줄이 빠지면
MatNexus 에는 그대로 남았고, 그것을 알 길이 없었다 — 더구나 이관 뒤 검산이 행 수를 견줘서, 원본이
한 줄이라도 지우면 **적재가 통째로 거부**되어 그 뒤로 문헌 데이터가 영영 안 바뀌었을 것이다.

    catalog_materials.source_missing_at
    catalog_sources.source_missing_at
    catalog_definitions.source_missing_at
    catalog_values.source_missing_at

비어 있으면 원본에 있는 줄이다. 채우는 것은 이관이고(마이그레이션은 칸만 만든다), 지금 원본에서
빠진 줄은 없으므로 이 칸은 전부 빈 채로 시작한다 — **배포해도 지금 동작은 안 바뀐다.**

함께 — 원본의 정의문을 따로 든다:

    catalog_definitions.source_description

원본에 정의문이 생기면 이관이 정의문 칸을 원본 글로 덮게 되어 있었다(ADR 0050 결정 4). 그러면
자료 관리자가 고친 글이 배포마다 원본 글로 되돌아간다 — 정의문 고치기 경로는 「배포가 안 덮는다」
고 약속하는데. 원본 글을 따로 들고 있어야 씨앗이 그것을 덮지 않고(배포마다 둘이 번갈아 쓰이지
않고), 사람이 고친 글은 둘 다 안 덮는다. 지금 원본의 정의문은 271종 전부 비어 있다.

Revision ID: c4d7e2a9f1b3
Revises: b3f8a1c6d2e9
Create Date: 2026-10-04 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d7e2a9f1b3"
down_revision: str | Sequence[str] | None = "b3f8a1c6d2e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("catalog_materials", "catalog_sources", "catalog_definitions", "catalog_values")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table, sa.Column("source_missing_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.add_column(
        "catalog_definitions", sa.Column("source_description", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("catalog_definitions", "source_description")
    for table in TABLES:
        op.drop_column(table, "source_missing_at")
