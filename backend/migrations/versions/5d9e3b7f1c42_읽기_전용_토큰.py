"""읽기 전용 토큰 (ADR 0054, 2026-10-03)

바깥 시스템(Standard Platform)이 물성 목록을 밤마다 읽어 간다. 그쪽 연동 지침은 「토큰은
읽기 전용으로 준다」 를 요구하는데, 토큰은 만든 사람의 권한 그대로였다 — 읽으라고 준 토큰으로
자료를 고치고 새 토큰까지 만들 수 있었다.

    personal_access_tokens.read_only   참이면 GET · HEAD 밖의 요청을 인증 자리가 막는다.
                                       있던 토큰은 거짓(지금과 같다)

Revision ID: 5d9e3b7f1c42
Revises: 0672d624d142
Create Date: 2026-10-03 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d9e3b7f1c42"
down_revision: str | Sequence[str] | None = "0672d624d142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "personal_access_tokens",
        sa.Column("read_only", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("personal_access_tokens", "read_only")
