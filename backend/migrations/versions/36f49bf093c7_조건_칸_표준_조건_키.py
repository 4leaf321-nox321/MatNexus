"""조건 칸 표준 조건 키

시험 종류의 조건 칸이 어느 표준 조건(`shared/standard_conditions`)인지를 적는 칸.
부서마다 `temp`·`temperature` 로 갈려 적어도 값 검색은 이 키로 거른다(2026-09-16).

이미 있는 칸은 **이름으로 짐작해 채운다** — `temperature`·`temp`·`reference_temperature`
가 아니라 정확히 표준 키·별칭에 맞는 것만. 못 맞춘 것은 비운 채 두고 사람이 정의
화면에서 고른다.

Revision ID: 36f49bf093c7
Revises: 38358a31c0a6
Create Date: 2026-09-16 19:20:41.412704

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "36f49bf093c7"
down_revision: str | Sequence[str] | None = "38358a31c0a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 표준 키 ← 조건 칸이 흔히 쓰는 이름. `shared/standard_conditions.STANDARD` 의 별칭과
#: 같은 뜻이지만 **마이그레이션은 앱 코드를 import 하지 않는다** — 나중에 별칭이 바뀌어도
#: 이 파일은 그때의 판단을 그대로 남긴다.
_GUESS: dict[str, tuple[str, str]] = {
    # 이름 → (표준 키, 저장 단위)
    "temperature": ("temperature", "K"),
    "temp": ("temperature", "K"),
    "strain_rate": ("strain_rate", "1/s"),
    "rate": ("strain_rate", "1/s"),
    "frequency": ("frequency", "Hz"),
    "freq": ("frequency", "Hz"),
    "humidity": ("humidity", "1"),
    "rh": ("humidity", "1"),
    "pressure": ("pressure", "Pa"),
    "crosshead_speed": ("crosshead_speed", "m/s"),
    "speed": ("crosshead_speed", "m/s"),
    "speed_plastic": ("crosshead_speed", "m/s"),
    "speed_elastic": ("crosshead_speed", "m/s"),
    "preload": ("preload", "N"),
    "aging_time": ("aging_time", "s"),
}


def upgrade() -> None:
    op.add_column(
        "test_condition_fields",
        sa.Column("canonical_key", sa.String(length=40), nullable=True),
    )
    op.create_index(
        op.f("ix_test_condition_fields_canonical_key"),
        "test_condition_fields",
        ["canonical_key"],
        unique=False,
    )
    bind = op.get_bind()
    for name, (canonical, si_unit) in _GUESS.items():
        # 숫자 칸이고 저장 단위가 맞는 것만 — 이름만 온도인 칸을 온도로 읽으면 검색이 틀린다.
        bind.execute(
            sa.text(
                "UPDATE test_condition_fields SET canonical_key = :canonical "
                "WHERE lower(key) = :name AND value_type = 'number' "
                "AND (si_unit IS NULL OR si_unit = :si_unit) AND canonical_key IS NULL"
            ),
            {"canonical": canonical, "name": name, "si_unit": si_unit},
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_test_condition_fields_canonical_key"), table_name="test_condition_fields"
    )
    op.drop_column("test_condition_fields", "canonical_key")
