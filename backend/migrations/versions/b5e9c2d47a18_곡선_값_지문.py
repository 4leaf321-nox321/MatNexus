"""곡선 값 지문 — 단위 · 형식만 다른 사본도 같은 측정으로 알아본다

Revision ID: b5e9c2d47a18
Revises: a8d2f4c61e07
Create Date: 2026-11-14

VOC 54: 같은 파일을 두 번 올리면 원본 SHA 로 알았지만, 줄끝 · 머리말 · 형식 · 단위만 달라도 다른
파일이 되어 통계에 이중으로 들어갔다(개발 DB: 같은 재료 · 시험 종류에 같은 SHA 의 채택 시험이 둘 이상인
조합 8개). 곡선은 SI 로 저장되므로 SI 값의 지문은 단위만 다른 사본도 같게 본다.

예전 곡선은 비어 있다 — `scripts/backfill_curve_fingerprints.py` 가 저장된 곡선 파일로 채운다(다시 읽지
않는다). 막지 않는다 — 읽을 때 점검(경고)으로 남고, 통계가 「같은 지문은 하나로」 를 고른다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e9c2d47a18"
down_revision: str | Sequence[str] | None = "a8d2f4c61e07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("curves", sa.Column("fingerprint", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_curves_fingerprint"), "curves", ["fingerprint"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_curves_fingerprint"), table_name="curves")
    op.drop_column("curves", "fingerprint")
