"""시험마다 **무엇으로 읽을지** 고를 수 있게 한다.

자동 선택이 틀리는 자리가 있다 — 같은 장비의 형식이 조금 달라져 프로파일을 하나
더 만들면 지문이 겹치고, 우선순위가 높은 쪽이 이겨서 엉뚱한 것으로 읽거나 아예
실패한다. 그때 「다시 읽기」 만 있으면 **같은 선택을 그대로 반복한다.**

고른 것을 시험에 남긴다. 큐 페이로드에만 실으면 재시도에서 사라지고, 나중에
누가 다시 읽으면 또 자동으로 돌아간다.

비어 있으면 전과 같이 자동이다 — 기존 시험은 손대지 않는다.

Revision ID: d3f5a81c62e7
Revises: c7d21a9f4b60
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3f5a81c62e7"
down_revision = "c7d21a9f4b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("parse_profile_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_test_runs_parse_profile_id"), "test_runs", ["parse_profile_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_test_runs_parse_profile_id_format_profiles"),
        "test_runs",
        "format_profiles",
        ["parse_profile_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_test_runs_parse_profile_id_format_profiles"), "test_runs", type_="foreignkey"
    )
    op.drop_index(op.f("ix_test_runs_parse_profile_id"), table_name="test_runs")
    op.drop_column("test_runs", "parse_profile_id")
