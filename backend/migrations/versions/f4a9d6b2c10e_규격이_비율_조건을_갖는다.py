"""규격이 비율 조건을 갖는다

**규격이 치수를 안 주고 비만 주는 일이 흔하다.** DMA 시편 규격표를 보면 숫자를
실제로 주는 파트가 ISO 6721-2·-3·-10 셋뿐이고 나머지는 전부 비율이거나 장비
위임이다.

    ISO 6721-3   L/h >= 50      저장탄성률 ±5 % 정확도 확보
    ISO 6721-4   La/b > 6       클램프의 횡수축 구속 영향 배제
    ISO 6721-6   h/L > 4        굽힘 성분 기여를 무시할 수준으로
    ISO 6721-12  h/D 1~2        프리로드 하 좌굴·배럴링 방지
    ISO 6721-10  D/d 10~50
    ASTM D7028   스팬/두께 > 10 전단 변형 기여 억제
    ISO 4664-1   변/두께 >= 4   단순 전단 상태·균일 가황

**어겼다고 막지 않는다.** ISO 6721-4 는 클램프 간 50~100 mm 를 권하는데 Netzsch
15 · Mettler 20 · TA 30 이 한계라 어느 장비도 만족하지 못한다. 막으면 실제로 잰
데이터를 못 넣게 되고, 그러면 사람은 시스템 밖에서 일한다. 대신 어긴 채로 쟀다는
것이 눈에 보여야 한다 — 규격 이름만 적힌 보고서는 재현이 안 된다.

Revision ID: f4a9d6b2c10e
Revises: e21a5c8b04f7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4a9d6b2c10e"
down_revision = "e21a5c8b04f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vocabulary_terms",
        sa.Column(
            "ratio_checks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("vocabulary_terms", "ratio_checks")
