"""정의의 key 를 전사에서 하나로 (ADR 0035)

장비 파일 정의·처리 레시피·해석용 물성 정의의 key 는 **부서 안에서만** 하나였다.
보기를 전원에게 열면 같은 key 가 둘 이상 보이고, key 로 하나를 집는 조회
(`/formats/{key}` · `/recipes/{key}` · 덱 형식)가 그중 **아무거나** 집는다.

## 이미 겹친 것은 뒤에 꼬리를 붙인다

**전역 것이 원래 key 를 지킨다** — 여러 부서가 이미 그 이름으로 부르고 있다. 부서
것끼리면 먼저 만든 쪽이 지킨다. 나머지는 `<원래 key>_<16진 8자리>` 가 된다. 이름
(label)은 그대로라 화면에서 사람이 읽는 것은 안 바뀐다.

**바뀐 것은 감사 기록에 남긴다**(`definition.key_renamed`). key 는 주소라서 북마크·
배치 설정·옮겨 온 파일에 적혀 있을 수 있다 — 「어제까지 되던 주소가 404」 를 설명할
근거가 있어야 한다.

## 되돌려도 key 는 안 돌아온다

`downgrade` 는 부서 범위 인덱스를 되살릴 뿐이다. 꼬리를 뗀 원래 key 로 돌리면 다시
겹치고, 그 사이에 새 key 로 저장한 설정이 있으면 그것이 끊긴다.

Revision ID: e13ac5784136
Revises: 41c1f6f09646
Create Date: 2026-09-24 10:00:00.000000

"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e13ac5784136"
down_revision: str | Sequence[str] | None = "41c1f6f09646"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (표, key 칸 길이, 옛 인덱스, 새 인덱스)
TABLES = (
    ("format_profiles", 50, "uq_format_profiles_scope_key", "uq_format_profiles_key"),
    ("processing_recipes", 80, "uq_processing_recipes_scope_key", "uq_processing_recipes_key"),
    ("export_profiles", 50, "uq_export_profiles_scope_key", "uq_export_profiles_key"),
)

LIVE = sa.text("deleted_at IS NULL")


def _free_key(bind: sa.Connection, table: str, key: str, width: int) -> str:
    """안 쓰인 key. **지운 행까지 센다** — 휴지통에서 되살릴 때 부딪히지 않게."""
    for _ in range(5):
        candidate = f"{key[: width - 9]}_{uuid.uuid4().hex[:8]}"
        taken = bind.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE key = :key"), {"key": candidate}
        ).first()
        if taken is None:
            return candidate
    raise RuntimeError(f"{table}: {key} 의 새 key 를 짓지 못했습니다")


def upgrade() -> None:
    bind = op.get_bind()
    for table, width, old, new in TABLES:
        # 전역(NULL) 먼저, 그다음 먼저 만든 것 — 그 순서의 첫째가 key 를 지킨다.
        losers = bind.execute(
            sa.text(
                f"""
                SELECT id, key, label, owner_workspace_id FROM (
                    SELECT id, key, label, owner_workspace_id,
                           row_number() OVER (
                               PARTITION BY key
                               ORDER BY (owner_workspace_id IS NOT NULL), created_at, id
                           ) AS rank
                    FROM {table}
                    WHERE deleted_at IS NULL
                ) ranked
                WHERE rank > 1
                """
            )
        ).all()
        for row in losers:
            renamed = _free_key(bind, table, row.key, width)
            bind.execute(
                sa.text(f"UPDATE {table} SET key = :key WHERE id = :id"),
                {"key": renamed, "id": row.id},
            )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO audit_entries (
                        id, action, actor_id, actor_label, target_table, target_id,
                        target_label, workspace_id, changes, reason, client
                    ) VALUES (
                        :id, 'definition.key_renamed', NULL, '마이그레이션', :table, :target,
                        :label, :workspace, CAST(:changes AS jsonb), :reason, 'script'
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "table": table,
                    "target": row.id,
                    "label": f"{row.label} ({renamed})",
                    "workspace": row.owner_workspace_id,
                    "changes": json.dumps(
                        {"key": {"before": row.key, "after": renamed}}, ensure_ascii=False
                    ),
                    "reason": "key 를 전사에서 하나로(ADR 0035) — 같은 key 를 먼저 쓴 것이 있었다",
                },
            )

        op.drop_index(old, table_name=table, postgresql_where=LIVE)
        op.create_index(new, table, ["key"], unique=True, postgresql_where=LIVE)


def downgrade() -> None:
    for table, _width, old, new in TABLES:
        op.drop_index(new, table_name=table, postgresql_where=LIVE)
        op.create_index(
            old,
            table,
            ["owner_workspace_id", "key"],
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=LIVE,
        )
