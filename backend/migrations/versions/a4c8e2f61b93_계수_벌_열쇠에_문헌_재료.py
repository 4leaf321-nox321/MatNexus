"""모델 파라미터 벌 — 저장 열쇠에 출처 문헌 재료를 더한다(출처 이름 빈 벌끼리 덮이던 것)

Revision ID: a4c8e2f61b93
Revises: f3a9c1d27e58
Create Date: 2026-11-15

`material_parameter_sets` 의 유일 열쇠가 (재료, 모델, source_ref) 라, 출처 이름(`set_id`)이 빈
벌은 source_ref 가 모두 "" 였다 — 다른 문헌 재료에서 받은 같은 모델의 벌이 서로를 조용히 덮었다.

- `catalog_material_id` (nullable, FK 없음 · 색인) — 받아 온 문헌 재료.
- 유일 열쇠: (재료, 모델, catalog_material_id, source_ref), **NULL 을 같은 값으로**
  (`NULLS NOT DISTINCT`) — 손으로 적은 벌 · 예전 줄끼리는 전과 같은 규칙이다.

예전 줄은 비어 있다(어느 문헌 재료였는지 남아 있지 않다). 다시 받아 오면 그 문헌 재료로 채운다
(`materials.routes.adopt_parameter_set`).

되돌리기는 옛 열쇠를 다시 거는데, 문헌 재료만 다른 벌이 이미 생겼으면 실패한다 — 그 줄을 먼저
정리해야 한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4c8e2f61b93"
down_revision: str | Sequence[str] | None = "f3a9c1d27e58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "material_parameter_sets"
UNIQUE = "uq_material_parameter_sets"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("catalog_material_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_material_parameter_sets_catalog_material_id"),
        TABLE,
        ["catalog_material_id"],
        unique=False,
    )
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.create_unique_constraint(
        UNIQUE,
        TABLE,
        ["material_id", "model", "catalog_material_id", "source_ref"],
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.create_unique_constraint(UNIQUE, TABLE, ["material_id", "model", "source_ref"])
    op.drop_index(op.f("ix_material_parameter_sets_catalog_material_id"), table_name=TABLE)
    op.drop_column(TABLE, "catalog_material_id")
