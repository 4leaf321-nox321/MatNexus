"""곡선 모양 — 자릿수 · 점 간격 · 단위 배수만 다른 사본도 같은 측정으로 알아본다

Revision ID: c9e3a7d51f42
Revises: b8d4f2a6c913
Create Date: 2026-11-17

VOC 54 남은 것(ADR 0091): 값 지문(`curves.fingerprint`)은 정확히 같은 값만 알아봐서, 자릿수를 줄여
저장한 사본 · 점을 솎은 사본 · 단위를 잘못 적어 한 열이 일정한 배수로 어긋난 사본은 통계에 두 번
들어갔다. 곡선마다 작은 모양(`matcore.curves.shape` — 늘기만 하는 열을 고르게 나눈 64 자리의 다른
열 값)을 두고, 읽을 때 **같은 재료 · 같은 시험 종류**의 다른 곡선과 견준다. 곡선 파일을 다시 읽지
않으려고 칸에 둔다(재료 하나에 시험이 수백 건이면 업로드마다 그만큼 파일을 열게 된다).

예전 곡선은 비어 있다 — `scripts/backfill_curve_fingerprints.py` 가 저장된 곡선 파일로 지문과 함께
채운다(배포의 채우기 단계가 부른다). 막지 않는다 — 읽을 때 점검(경고)으로 남는다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e3a7d51f42"
down_revision: str | Sequence[str] | None = "b8d4f2a6c913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "curves",
        sa.Column("shape", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("curves", "shape")
