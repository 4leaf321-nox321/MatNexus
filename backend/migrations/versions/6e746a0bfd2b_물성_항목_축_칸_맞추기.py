"""사내 물성 항목 축의 칸을 코드에 맞춘다 — 차원 선택지와 빠진 기본 칸

실측(2026-09-12): 단위표에 44차원이 들어왔는데 「차원」 드롭다운은 축을 만들던 날의
19개 그대로였다 — 선택지가 DB JSON 에 얼어 있었다. 뒤에 코드가 더한 기본 칸
(`measured_key`·`scales`·`level`)도 같은 이유로 안 들어와 있었다. 관리자가 고친
라벨·도움말·자기 칸은 그대로 둔다.

Revision ID: 6e746a0bfd2b
Revises: b2d5bf0e4590
Create Date: 2026-09-12 14:00:00

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = "6e746a0bfd2b"
down_revision: str | Sequence[str] | None = "b2d5bf0e4590"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.modules.vocabulary.definitions import refresh_builtin_axis_fields

    session = Session(bind=op.get_bind())
    refresh_builtin_axis_fields(session)
    session.commit()


def downgrade() -> None:
    # 선택지를 줄이는 되돌림은 두지 않는다 — 이미 그 차원으로 만든 항목이 깨진다.
    pass
