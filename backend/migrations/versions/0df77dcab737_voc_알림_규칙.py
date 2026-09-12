"""VOC 알림 규칙을 기존 계정에도 붙인다

기본 규칙은 계정이 활성화될 때만 붙는다(`ensure_rules`). 이미 있는 계정은 그 길을
다시 지나지 않으므로, 새 사건 종류(`voc.changed` 는 모두, `voc.registered` 는
관리자)는 여기서 한 번 붙인다(2026-09-12). 이미 있으면 건너뛴다.

Revision ID: 0df77dcab737
Revises: 4f60297a1774
Create Date: 2026-09-12 11:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0df77dcab737"
down_revision: str | Sequence[str] | None = "4f60297a1774"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _attach(event_kind: str, admins_only: bool) -> None:
    where = "AND u.is_system_admin" if admins_only else ""
    op.execute(
        f"""
        INSERT INTO notification_rules (id, user_id, event_kind, channel, enabled, created_at)
        SELECT gen_random_uuid(), u.id, '{event_kind}', 'inapp', true, now()
        FROM users u
        WHERE u.status = 'active' {where}
          AND NOT EXISTS (
            SELECT 1 FROM notification_rules r
            WHERE r.user_id = u.id AND r.event_kind = '{event_kind}' AND r.channel = 'inapp'
          )
        """
    )


def upgrade() -> None:
    _attach("voc.changed", admins_only=False)
    _attach("voc.registered", admins_only=True)


def downgrade() -> None:
    op.execute(
        "DELETE FROM notification_rules WHERE event_kind IN ('voc.changed', 'voc.registered')"
    )
