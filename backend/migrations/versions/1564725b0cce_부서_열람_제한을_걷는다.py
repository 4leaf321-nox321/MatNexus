"""부서 열람 제한(`restricted`)을 걷는다 (ADR 0035)

보기는 전원이다. 부서가 켜면 그 부서의 재료·시험이 멤버에게만 보이던 손잡이를 없앤다.
켜졌는지가 막힌 사람 쪽에서는 안 보였다 — 「없다」 와 「가려졌다」 가 같은 모양이라,
권한 때문에 막힌 것을 사람이 알아낼 길이 없었다.

## 켜져 있던 부서는 감사 기록에 남긴다

컬럼을 지우면 **어느 부서가 가리고 있었는지가 사라진다.** `downgrade` 로 컬럼은
돌아와도 값은 전부 꺼진 채다. 그래서 지우기 전에 켜져 있던 부서마다
`workspace.restriction_removed` 를 남긴다 — 다시 가려야 하는 자료가 있는지 사람이
그 목록으로 확인한다.

Revision ID: 1564725b0cce
Revises: e13ac5784136
Create Date: 2026-09-24 10:05:00.000000

"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1564725b0cce"
down_revision: str | Sequence[str] | None = "e13ac5784136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for row in bind.execute(
        sa.text("SELECT id, slug, name FROM workspaces WHERE restricted")
    ).all():
        bind.execute(
            sa.text(
                """
                INSERT INTO audit_entries (
                    id, action, actor_id, actor_label, target_table, target_id,
                    target_label, workspace_id, changes, reason, client
                ) VALUES (
                    :id, 'workspace.restriction_removed', NULL, '마이그레이션', 'workspaces',
                    :target, :label, :target, CAST(:changes AS jsonb), :reason, 'script'
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "target": row.id,
                "label": f"{row.name} ({row.slug})",
                "changes": json.dumps({"restricted": {"before": True, "after": None}}),
                "reason": "보기는 전원이다(ADR 0035) — 부서 열람 제한을 걷었다",
            },
        )
    op.drop_column("workspaces", "restricted")


def downgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("restricted", sa.Boolean(), server_default="false", nullable=False),
    )
