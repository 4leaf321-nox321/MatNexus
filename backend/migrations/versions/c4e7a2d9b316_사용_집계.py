"""사용 집계 표 셋 (2026-10-02)

「실제로 얼마나 잘 쓰고 있나」 — 접근 로그는 쓰기와 로그인만 남겨 조회와 MCP(AI) 사용을 셀 수
없었다. 행을 남기지 않고 날 · 사람 · 길마다 수를 더하는 표 셋이다(`modules/usage`).

    usage_daily         API 요청 — 날 · 사람 · 길(web/mcp) · 메서드 · 라우트 틀
    usage_views_daily   상세 조회 — 날 · 종류 · 대상 · 사람 · 길
    mcp_tool_daily      MCP 도구 호출 — 날 · 사람 · 도구 (호출 · 실패 · 걸린 시간)

사용자 열에 외래키를 안 건다 — 계정을 지워도 그 사람이 쓴 양은 남는다.

Revision ID: c4e7a2d9b316
Revises: 8b3d5f7a9c21
Create Date: 2026-10-02 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e7a2d9b316"
down_revision: str | Sequence[str] | None = "8b3d5f7a9c21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client", sa.String(length=10), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("route", sa.String(length=200), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "user_id", "client", "method", "route"),
    )
    op.create_table(
        "usage_views_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client", sa.String(length=10), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "kind", "entity_id", "user_id", "client"),
    )
    op.create_table(
        "mcp_tool_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool", sa.String(length=80), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elapsed_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "user_id", "tool"),
    )


def downgrade() -> None:
    op.drop_table("mcp_tool_daily")
    op.drop_table("usage_views_daily")
    op.drop_table("usage_daily")
