"""공지 씨앗 — 넣은 키를 공지와 따로 기억한다(지운 초안이 다음 배포에 되살아나던 것)

Revision ID: f3a9c1d27e58
Revises: e7b3c9d15f42
Create Date: 2026-11-15

`scripts/import_notices.py` 는 「넣었나」 를 `notices.seed_key` 행으로만 봤다. 관리자가 초안을
지우면 행이 사라져, 다음 배포가 그 씨앗(약 100개)을 또 초안으로 넣었다.

- `notice_seed_keys(key PK, imported_at)` — 넣은 적이 있는 씨앗 키. 공지와 FK 로 묶지 않는다.
- 데이터: 지금 공지에 남은 `seed_key` 로 채운다(SQL — 지금의 ORM 모델을 읽지 않는다).

이미 지워 버린 초안의 키는 알 길이 없다 — 그 씨앗은 이 배포에 한 번 더 초안으로 들어오고,
그것을 지우면 그다음부터는 안 들어온다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a9c1d27e58"
down_revision: str | Sequence[str] | None = "e7b3c9d15f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notice_seed_keys",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_notice_seed_keys")),
    )
    op.execute(
        """
        INSERT INTO notice_seed_keys (key, imported_at)
        SELECT seed_key, coalesce(created_at, now())
        FROM notices
        WHERE seed_key IS NOT NULL
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("notice_seed_keys")
