"""시험 점검 · 처리 결과 경고 — 사람이 확인할 것을 결과 · 채택 · 카드까지 남긴다

Revision ID: a8d2f4c61e07
Revises: c4e8a1d7f203
Create Date: 2026-11-14

VOC 53 · 55 · 56 · 57 의 공통 원인은 「원본과 기록이 다르다」 는 말이 화면에만 뜨고 처리 결과 ·
채택 · 카드에는 안 남는 것이었다. 파싱 경고는 `source_metadata._warnings` 의 「 / 」 로 이은 문자열
하나였고, 처리 단계에는 노트만 있었다.

- `test_runs.checks` — 읽을 때 잰 점검 `[{code, message}]`(실측 칸이 공칭과 같은데 파일 값과 다름 ·
  파일 속도가 입력과 다름 · 응력처럼 보이는 무차원 채널). 다시 읽으면 새로 잰다.
- `processing_results.warnings` — 처리할 때의 시험 점검 + 단계 경고 `[{source, label, message}]`.
  결과는 불변이라 처리한 그때의 것을 적어 둔다.

예전 시험 · 결과는 잰 적이 없으므로 빈 목록이다(점검을 안 했다는 뜻이지 문제가 없다는 뜻은 아니다 —
다시 읽거나 다시 처리하면 선다).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8d2f4c61e07"
down_revision: str | Sequence[str] | None = "c4e8a1d7f203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_runs",
        sa.Column(
            "checks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "processing_results",
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("processing_results", "warnings")
    op.drop_column("test_runs", "checks")
