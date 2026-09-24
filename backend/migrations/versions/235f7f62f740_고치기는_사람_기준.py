"""고치기는 사람 기준 — 자료 관리자와 편집을 받은 부서 (ADR 0035 D4)

자료를 고치는 사람은 넷이다: 시스템 관리자 · 자료 관리자 · 그 자료의 등록자 · 그 자료에
편집을 받은 부서의 멤버. 소속 부서는 더 이상 권한을 정하지 않는다.

    users.is_data_manager          자료 관리자 — 사람에게 붙는 전사 역할
    <자료>.edit_workspace_id       편집을 받은 부서 — 재료·시료·시편·시험·카드·묶음

## 있던 자료는 지금 소속 부서에 편집을 준다

새 자료는 등록자만 고친다(부서는 필요할 때 준다). 그런데 있던 자료까지 그렇게 두면
**개편하는 날 팀이 제 자료를 못 고친다** — 이관 계정 하나로 올라간 자료는 사실상 관리자
전용이 된다. 그래서 있던 자료는 지금 고치던 사람들(그 소속 부서)이 계속 고치게 둔다.
누가 고치는지는 화면에 보이고, 등록자가 언제든 걷거나 바꿀 수 있다.

    재료   ← owner_workspace_id (전역 재료는 비어 있다 — 부서가 없다)
    시료·시편·시험·묶음  ← workspace_id
    카드   ← 그 재료의 owner_workspace_id

## 부서를 지우면 부여만 끊긴다

`ON DELETE SET NULL` 이다. 부여 때문에 부서를 못 지우게 되면 안 된다 — 부서는 어차피
보관하지 지우지 않고, 합치기는 FK 를 걸어 옮기므로 부여도 새 부서로 따라간다.

Revision ID: 235f7f62f740
Revises: 1564725b0cce
Create Date: 2026-09-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "235f7f62f740"
down_revision: str | Sequence[str] | None = "1564725b0cce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "materials",
    "samples",
    "specimens",
    "test_runs",
    "property_cards",
    "group_results",
)

#: 있던 자료의 편집 부서 — 지금 소속 부서.
BACKFILL = {
    "materials": "UPDATE materials SET edit_workspace_id = owner_workspace_id",
    "samples": "UPDATE samples SET edit_workspace_id = workspace_id",
    "specimens": "UPDATE specimens SET edit_workspace_id = workspace_id",
    "test_runs": "UPDATE test_runs SET edit_workspace_id = workspace_id",
    "group_results": "UPDATE group_results SET edit_workspace_id = workspace_id",
    "property_cards": (
        "UPDATE property_cards AS c SET edit_workspace_id = m.owner_workspace_id "
        "FROM materials AS m WHERE m.id = c.material_id"
    ),
}


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_data_manager", sa.Boolean(), server_default="false", nullable=False),
    )
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("edit_workspace_id", sa.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            op.f(f"fk_{table}_edit_workspace_id_workspaces"),
            table,
            "workspaces",
            ["edit_workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            op.f(f"ix_{table}_edit_workspace_id"), table, ["edit_workspace_id"], unique=False
        )
        op.execute(BACKFILL[table])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(op.f(f"ix_{table}_edit_workspace_id"), table_name=table)
        op.drop_constraint(
            op.f(f"fk_{table}_edit_workspace_id_workspaces"), table, type_="foreignkey"
        )
        op.drop_column(table, "edit_workspace_id")
    op.drop_column("users", "is_data_manager")
