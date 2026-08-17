"""장비 항복강도 키를 우리 것과 맞춘다 — proof_stress_02 → proof_stress

**나란히 두려고 source 를 나눴는데 정작 짝이 안 맞았다.** 요약값은
`(test_run_id, key, source)` 로 유일해서, 같은 키에 장비/우리 값이 나란히 서게
설계돼 있다. 그런데 파서가 항복강도만 `proof_stress_02` 로 내고 있었다 — 실측:
장비 160.0 MPa vs 우리 249.5 MPa 로 56% 차이가 났는데 표에서 다른 줄에 섰다.

파서를 고쳤으니 **이미 저장된 행도 맞춘다.** 안 맞추면 다시 읽은 시험과 안 읽은
시험이 서로 다른 키를 갖고, 그 차이가 어디서 왔는지 나중에 알 수 없다.

우리 값이 이미 `proof_stress` 로 들어가 있어도 `source` 가 달라 충돌하지 않는다.


Revision ID: b99a3b229f6c
Revises: 4793f2545a1e
Create Date: 2026-08-17 10:06:31.510805

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b99a3b229f6c"
down_revision: Union[str, Sequence[str], None] = "4793f2545a1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE test_summaries SET key = 'proof_stress' "
            "WHERE key = 'proof_stress_02' AND source = 'instrument'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE test_summaries SET key = 'proof_stress_02' "
            "WHERE key = 'proof_stress' AND source = 'instrument'"
        )
    )
