"""곡선 출처 — 덱 카드에서 복원한 곡선이 실측처럼 쓰이던 것

Revision ID: d4a8c2e61b37 Revises: c9e3a7d51f42 Create Date: 2026-11-17

HWAX 연결 3단계(ADR 0096): 시험에 곡선의 출처를 적는 칸이 없어, 해석 덱의 소성 표에서 복원한
곡선이 시험으로 올라오면 실측과 구별되지 않았다. 기본은 실측(`measured`) — 예전 시험은 모두
장비 파일이다. 막지 않는다 — 실측이 아니면 카드 근거 · 덱 머리 · 시험 응답에 경고가 선다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a8c2e61b37"
down_revision: str | Sequence[str] | None = "c9e3a7d51f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_runs",
        sa.Column(
            "curve_origin", sa.String(length=20), nullable=False, server_default="measured"
        ),
    )


def downgrade() -> None:
    op.drop_column("test_runs", "curve_origin")
