"""감사 로그 — 무엇이 바뀌었고 누가 승인했는가

접근 로그(`access_logs`)와 **목적이 다르다.** 접근 로그는 *"그 화면에서 안 돼요"*
를 재현하는 지원용이고, 이것은 무결성용이다. 보존 기간이 다르므로 나눠 둔다 —
접근 로그는 몇 달이면 지워도 되지만 감사 로그는 남아야 한다.

Phase 1 에서 *"기록할 것이 아직 없어 Phase 2 에서 시험 데이터와 함께"* 로 미뤘고,
지금은 기록할 것이 넘친다 — 시험·처리 결과·카드·기준정보·시편 규격.

**소급이 안 된다.** 데이터가 쌓인 뒤에 넣으면 그 전 변경 이력은 영영 없다.
계산 재현 기록(c9a1d3e75b28)을 미루지 않은 것과 같은 이유다.

## 외래키를 안 건다

`target_id` 와 `workspace_id` 에 FK 가 없다. **지워진 대상의 기록이 그 삭제 때문에
사라지면 안 된다** — 카드를 지워도 "그 카드를 누가 언제 확정했는지" 는 남아야 한다.
`actor_id` 만 `SET NULL` 로 두고, 사람 이름은 따로 박아 둔다.

Revision ID: d4b8c2f61a09
Revises: c9a1d3e75b28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "d4b8c2f61a09"
down_revision = "c9a1d3e75b28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_label", sa.String(length=200), nullable=False),
        sa.Column("target_table", sa.String(length=60), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_label", sa.String(length=300), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    for column in (
        "action",
        "actor_id",
        "target_table",
        "target_id",
        "workspace_id",
        "request_id",
        "created_at",
    ):
        op.create_index(f"ix_audit_entries_{column}", "audit_entries", [column])


def downgrade() -> None:
    op.drop_table("audit_entries")
