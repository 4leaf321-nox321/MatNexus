"""로그인 실패 기록 — 같은 계정의 실패가 쌓이면 응답을 늦춘다

Revision ID: e7b2c41f9a05
Revises: c4d1a9e27b3f
Create Date: 2026-09-05

**잠그지 않는다.** 관리자 복구가 서버 콘솔뿐인 시스템에서 잠금은 자해다(계획 문서
「관리자 기능 개발」 4번). 5회부터 2초씩 늘어 최대 30초 — 무차별 시도는 시간당 몇
번으로 줄고, 비밀번호를 아는 사람은 한 번 기다리면 된다. 세는 자리가 계정 행이라
프로세스가 여럿이어도 같은 수를 본다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7b2c41f9a05"
down_revision: Union[str, Sequence[str], None] = "c4d1a9e27b3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("failed_logins", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_failed_login_at")
    op.drop_column("users", "failed_logins")
