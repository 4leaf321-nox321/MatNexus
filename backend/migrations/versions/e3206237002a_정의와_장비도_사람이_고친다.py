"""정의와 장비도 사람이 고친다 (ADR 0035 3단계)

2단계가 자료(재료·시료·시편·시험·카드·묶음)를 사람 기준으로 옮겼다. 여기는 그 나머지다
— 부서 관리자가 고치던 **정의 넷**과 「어느 부서든 관리자면」 고치던 **장비**.

    <정의>.edit_workspace_id       시험 종류 · 장비 파일 정의 · 레시피 · 해석용 물성 정의
    test_types.created_by_id       시험 종류만 등록자 칸이 없었다
    equipment_units.registered_by_id · edit_workspace_id

## 있던 것은 그 부서에 편집을 준다

2단계의 1번과 같은 판단이다 — 개편하는 날 팀이 제 정의를 못 고치면 안 된다.

    정의   ← owner_workspace_id (등록 부서). 부서 없이 올린 것은 비어 있다
    장비   ← workspace_id (장비를 든 조직)

전에는 그 부서의 **관리자**만 고쳤다. 이제는 그 부서 사람이 고친다 — 부서 관리자라는
자리가 고칠 권한을 갖지 않게 되었으므로(D5), 부서에 준 것은 부서 사람 모두의 것이다.
등록자가 언제든 걷거나 바꾼다(「권한」).

**시험 종류와 장비는 등록자가 비어 있다.** 누가 만들었는지 적지 않았다 — 감사에도
만든 기록이 없다. 그런 것은 편집을 받은 부서와 자료 관리자가 고친다.

## 부서를 지우면 부여만 끊긴다

`ON DELETE SET NULL` — 2단계와 같다.

Revision ID: e3206237002a
Revises: 235f7f62f740
Create Date: 2026-09-24 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3206237002a"
down_revision: str | Sequence[str] | None = "235f7f62f740"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 편집 부서를 새로 받는 표와, 있던 행에 채울 값.
BACKFILL = {
    "test_types": "UPDATE test_types SET edit_workspace_id = owner_workspace_id",
    "format_profiles": "UPDATE format_profiles SET edit_workspace_id = owner_workspace_id",
    "processing_recipes": (
        "UPDATE processing_recipes SET edit_workspace_id = owner_workspace_id"
    ),
    "export_profiles": "UPDATE export_profiles SET edit_workspace_id = owner_workspace_id",
    "equipment_units": "UPDATE equipment_units SET edit_workspace_id = workspace_id",
}


def _registrant(table: str, column: str, *, ondelete: str | None) -> None:
    op.add_column(table, sa.Column(column, sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f(f"fk_{table}_{column}_users"),
        table,
        "users",
        [column],
        ["id"],
        ondelete=ondelete,
    )
    op.create_index(op.f(f"ix_{table}_{column}"), table, [column], unique=False)


def upgrade() -> None:
    # 시험 종류 — 다른 정의 셋처럼 `created_by_id`(FK 에 ondelete 없음 — 계정은 지우기 전에
    # 승계하므로 `dependents.OWNER_COLUMNS` 가 옮긴다).
    _registrant("test_types", "created_by_id", ondelete=None)
    # 장비 — 재료처럼 「등록」 이다.
    _registrant("equipment_units", "registered_by_id", ondelete="SET NULL")

    for table, backfill in BACKFILL.items():
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
        op.execute(backfill)


def downgrade() -> None:
    for table in reversed(list(BACKFILL)):
        op.drop_index(op.f(f"ix_{table}_edit_workspace_id"), table_name=table)
        op.drop_constraint(
            op.f(f"fk_{table}_edit_workspace_id_workspaces"), table, type_="foreignkey"
        )
        op.drop_column(table, "edit_workspace_id")
    for table, column in (
        ("equipment_units", "registered_by_id"),
        ("test_types", "created_by_id"),
    ):
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_{column}_users"), table, type_="foreignkey")
        op.drop_column(table, column)
