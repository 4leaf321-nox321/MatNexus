"""공지 씨앗 키 — 배포에 실려 온 안내는 그 파일 이름을 든다

새 기능은 코드와 함께 도착하는데 그것을 알리는 글은 사람이 따로 써야 했다
(2026-09-12). `seeds/notices/*.md` 가 배포마다 초안으로 들어오고, 같은 키는 두 번
안 들어온다.

Revision ID: b2d5bf0e4590
Revises: 22ccff22a092
Create Date: 2026-09-12 12:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d5bf0e4590"
down_revision: str | Sequence[str] | None = "22ccff22a092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notices", sa.Column("seed_key", sa.String(length=100), nullable=True))
    op.create_unique_constraint(op.f("uq_notices_seed_key"), "notices", ["seed_key"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_notices_seed_key"), "notices", type_="unique")
    op.drop_column("notices", "seed_key")
