"""계산이 무엇으로 나왔는지 남긴다

이 저장소는 재현을 위해 이미 여러 가지를 남긴다 — 레시피 스냅샷, 단계별 플러그인
버전, 적합의 **경계와 초기값**까지. 그 이유가 코드에 적혀 있다.

    경계와 초기값을 함께 남긴다. 비선형 적합은 여기에 따라 다른 답에 수렴한다.
    남기지 않으면 같은 데이터로 다시 돌려도 재현이 안 된다.

**그 논리의 나머지 절반이 빠져 있었다.** 우리 적합은 `scipy.optimize.least_squares`
를 쓴다. scipy 가 바뀌면 신뢰영역 구현이 달라지고, 같은 데이터·같은 플러그인
버전에서 **다른 파라미터가 나올 수 있다.**

`processing_results.runtime` 에 python·numpy·scipy·pyarrow 버전을 담는다. 물성
카드는 `source` 가 이미 dict 라 거기에 넣는다(마이그레이션 불필요).

**소급이 안 되는 값이다.** 오늘 만든 것이 어느 scipy 로 계산됐는지는 오늘 적어야
안다 — 그래서 값이 작아도 미루지 않았다. 이 리비전 이전의 결과는 빈 `{}` 이고,
그것이 "안 적혔다" 는 사실 자체로 남는다.

Revision ID: c9a1d3e75b28
Revises: b6e2f7c918da
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9a1d3e75b28"
down_revision = "b6e2f7c918da"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_results",
        sa.Column(
            "runtime",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("processing_results", "runtime")
