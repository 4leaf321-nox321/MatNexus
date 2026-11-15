"""반복 시편 통계의 시험 온도를 정식 칸으로 — `curve` JSON 안에 두던 것

Revision ID: b8d4f2a6c913
Revises: a4c8e2f61b93
Create Date: 2026-11-15

v1.337.0 에서 통계 묶음을 시험 온도로 가르면서, 남긴 통계(`ensemble_results`)의 온도는 표에 칸이
없어 `curve->'temperature_k'` 에 두었다. 같은 재료 · 종류 · 방향 · 온도의 통계를 찾으려면 JSON 을
뒤져야 하고, 곡선 기록과 묶음 열쇠가 한 칸에 섞인다.

- `temperature_k` (Float, nullable) — 그 묶음의 시험 온도(K). `NULL` 은 미기재 묶음이거나 온도로
  가르기 전에 남긴 통계(모름).
- 있는 행은 `curve->>'temperature_k'` 로 채운다(**SQL 로** — 지금의 ORM 모델을 읽지 않는다). 숫자가
  아닌 값(`null` · 키 없음)은 비워 둔다.
- 옛 행의 `curve` 에 남은 키는 지우지 않는다 — 남긴 통계는 불변이고, 읽는 길이 칸을 먼저 본다.

되돌리기는 칸의 값을 `curve` 에 다시 적은 뒤(그 키가 없는 행만 — 이 마이그레이션 뒤에 남긴 통계)
칸을 지운다. 옛 코드는 `curve` 에서 읽는다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4f2a6c913"
down_revision: str | Sequence[str] | None = "a4c8e2f61b93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ensemble_results"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("temperature_k", sa.Float(), nullable=True))
    op.execute(
        "UPDATE ensemble_results "
        "SET temperature_k = (curve->>'temperature_k')::double precision "
        "WHERE jsonb_typeof(curve->'temperature_k') = 'number'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ensemble_results "
        "SET curve = curve || jsonb_build_object('temperature_k', temperature_k) "
        "WHERE temperature_k IS NOT NULL AND NOT (curve ? 'temperature_k')"
    )
    op.drop_column(TABLE, "temperature_k")
