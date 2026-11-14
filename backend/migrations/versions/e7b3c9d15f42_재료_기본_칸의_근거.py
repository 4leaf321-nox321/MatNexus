"""재료 기본 칸(밀도 · 푸아송비)의 근거 — 문헌에서 받아 온 값의 출처 · 근거 · 문헌 등급

Revision ID: e7b3c9d15f42
Revises: d2a8f4c61b37
Create Date: 2026-11-14

VOC 50: 문헌값을 채택하면 밀도 · 푸아송비는 재료의 기본 칸(숫자 하나)에만 써지고 출처가 버려졌다.
카드는 그 값을 「재료에 적힌 공칭값(등급 3)」 으로 봐, 문헌 등급 4(추정)의 값이 3으로 올라가 보였다.

- `column_evidence` — 칸마다 선언 물성 줄과 같은 모양의 근거(`{"density": {...}}`).

예전 재료는 비어 있다(출처를 모르는 값, 등급 3) — 문헌 연결과 값이 맞는 것은 운영 작업의
`scripts/backfill_column_evidence.py` 로 거슬러 채운다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7b3c9d15f42"
down_revision: str | Sequence[str] | None = "d2a8f4c61b37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column(
            "column_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("materials", "column_evidence")
