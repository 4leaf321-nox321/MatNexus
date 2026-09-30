"""기본 형식 정의판의 씨앗 지문 (ADR 0047)

기본 형식을 정의로 다시 적은 정의판 50벌(ADR 0038)은 코드판이 틀렸을 때 대신 켜는
비상용인데, 운영에 넣는 길이 없었다. 배포가 넣고, 아무도 손대지 않은 것만 새 씨앗을
따르게 한다 — 「손대지 않았다」 를 가르는 칸이다.

    export_profiles.seed_digest     씨앗이 마지막으로 쓴 이름 · 설명 · 정의의 sha256.
                                    사람이 만든 정의는 NULL

Revision ID: 5c2e8d41a7f3
Revises: 0d666d121ae9
Create Date: 2026-10-01 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c2e8d41a7f3"
down_revision: str | Sequence[str] | None = "0d666d121ae9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_profiles", sa.Column("seed_digest", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("export_profiles", "seed_digest")
