"""시편을 가로질러 찾는다 — 시료·시편에 trigram 인덱스.

시편 평면 목록(`GET /specimens`)과 **열 머리의 거르기**가 생겼다. 둘 다
`ILIKE '%낱말%'` 로 도는데, 그것은 B-tree 를 못 탄다 — 앞의 와일드카드 때문에
어느 접두사부터 볼지 정할 수가 없다.

재료가 이미 같은 이유로 trigram GIN 을 넷 갖고 있다(`ix_materials_*_trgm`).
시료·시편에는 없었다 — 지금까지 중첩 경로로만 닿아서 한 재료 안의 몇 건만 훑으면
됐기 때문이다. 가로지르는 순간 그 전제가 사라진다.

**규격이 이 표의 열쇠다.** 「ASTM E8/E8M 박판형 시편 전부」 가 이 화면을 만든
물음이고, 그 답은 `specimens.standard` 를 부분 일치로 훑는 데서 나온다.

지금 데이터로는 인덱스 없이도 빠르다. 그래서 지금 넣는다 — 느려진 뒤에 넣으면
그때는 이미 사람이 "검색이 안 된다" 로 겪은 뒤다.

Revision ID: d8f4a17c2e60
Revises: c3d7b21f9a04
Create Date: 2026-08-28 03:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f4a17c2e60"
down_revision: Union[str, Sequence[str], None] = "c3d7b21f9a04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (인덱스 이름, 표, 컬럼). 재료 쪽과 같은 모양이라 한 줄씩 늘리면 된다.
INDEXES = (
    ("ix_samples_record_name_trgm", "samples", "record_name"),
    ("ix_samples_lot_no_trgm", "samples", "lot_no"),
    ("ix_specimens_record_name_trgm", "specimens", "record_name"),
    ("ix_specimens_standard_trgm", "specimens", "standard"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, column in INDEXES:
        op.create_index(
            name,
            table,
            [column],
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )


def downgrade() -> None:
    """Downgrade schema."""
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
