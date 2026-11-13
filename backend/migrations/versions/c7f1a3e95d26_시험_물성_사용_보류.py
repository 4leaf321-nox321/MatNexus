"""시험의 「물성 사용 보류」 — 자료 관리자가 걸고 풀며, 걸리면 채택 · 카드 · 통계에서 빠진다

Revision ID: c7f1a3e95d26
Revises: b5e9c2d47a18
Create Date: 2026-11-14

VOC 60: 문제가 의심되는 시험을 「쓰지 말라」 고 표시할 자리가 없었다. 메모에 적어도 채택 · 카드 ·
통계는 그것을 몰랐고, 시험 메모는 MCP 응답에 아예 안 실려 AI 도 몰랐다.

- `hold_reason` — 비어 있지 않으면 보류 중이다(사유가 곧 상태다 — 사유 없는 보류는 없다).
- `held_at` · `held_by_id` — 누가 언제 걸었나. 푸는 것은 감사 기록에 남는다.

예전 시험은 보류가 아니다(빈 칸).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7f1a3e95d26"
down_revision: str | Sequence[str] | None = "b5e9c2d47a18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("hold_reason", sa.Text(), nullable=True))
    op.add_column("test_runs", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "test_runs",
        sa.Column("held_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_test_runs_held_by_id_users", "test_runs", "users", ["held_by_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_test_runs_held_by_id_users", "test_runs", type_="foreignkey")
    op.drop_column("test_runs", "held_by_id")
    op.drop_column("test_runs", "held_at")
    op.drop_column("test_runs", "hold_reason")
