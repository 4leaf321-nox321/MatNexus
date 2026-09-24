"""감사에 「누구의 자료에 일어난 일인가」 (ADR 0035 남은 것)

보기가 모두에게 열리고 고치기가 자료 관리자·편집을 받은 부서로 넓어진 뒤, 등록자가
「내 자료에 무슨 일이 있었나」 를 물을 자리가 없었다 — 감사 화면은 관리자 것이다.

    audit_entries.subject_id     그때 대상의 등록자. 등록자에게 제 자료의 기록만 연다

## 있던 기록도 채운다

대상이 아직 있으면 지금의 등록자를 적는다 — 삭제는 휴지통에 남아 있어 대개 읽힌다.
**넘기기(`ownership.changed`)는 안 채운다**: 그 기록의 주인은 넘기기 **전의** 등록자인데,
지금 표에는 넘겨받은 사람이 적혀 있다. 틀린 사람에게 여는 것보다 비워 두는 편이 낫다.

처리 결과는 제 등록자가 없다 — 그 결과를 낸 **시험의 등록자**다.

## FK 를 안 건다

`target_id`·`workspace_id` 와 같다 — 사람이 지워져도 기록은 남아야 한다.

Revision ID: 23e1f2c2d047
Revises: e3206237002a
Create Date: 2026-09-25 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "23e1f2c2d047"
down_revision: str | None = "e3206237002a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (표, 등록자 칸) — `shared/permissions._REGISTRANT` 의 그날 모습. 마이그레이션은 코드를
#: 부르지 않는다(코드가 바뀌면 옛 마이그레이션의 뜻이 바뀐다).
_REGISTRANTS = (
    ("materials", "registered_by_id"),
    ("samples", "registered_by_id"),
    ("specimens", "registered_by_id"),
    ("test_runs", "registered_by_id"),
    ("equipment_units", "registered_by_id"),
    ("property_cards", "created_by_id"),
    ("group_results", "created_by_id"),
    ("test_types", "created_by_id"),
    ("format_profiles", "created_by_id"),
    ("processing_recipes", "created_by_id"),
    ("export_profiles", "created_by_id"),
    ("workbench_runs", "owner_id"),
)


def upgrade() -> None:
    op.add_column(
        "audit_entries",
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_audit_entries_subject_id", "audit_entries", ["subject_id"])

    for table, column in _REGISTRANTS:
        op.execute(
            f"""
            UPDATE audit_entries AS a
               SET subject_id = t.{column}
              FROM {table} AS t
             WHERE a.target_table = '{table}'
               AND a.target_id = t.id
               AND a.subject_id IS NULL
               AND a.action <> 'ownership.changed'
            """
        )
    op.execute(
        """
        UPDATE audit_entries AS a
           SET subject_id = r.registered_by_id
          FROM processing_results AS p
          JOIN test_runs AS r ON r.id = p.test_run_id
         WHERE a.target_table = 'processing_results'
           AND a.target_id = p.id
           AND a.subject_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_audit_entries_subject_id", table_name="audit_entries")
    op.drop_column("audit_entries", "subject_id")
