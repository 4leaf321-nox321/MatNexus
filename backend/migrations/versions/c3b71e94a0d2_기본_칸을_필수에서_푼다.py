"""기본 칸을 필수에서 푼다

시편 분류의 기본 칸을 "그 분류의 규격이면 **예외 없이** 갖는 것" 으로 여기고
필수로 두었는데, ASTM·ISO 규격표가 그것을 반증했다.

    인장  D3039·D3518·D5766 은 게이지 길이를 시편에 새기지 않는다 — 그립 간
          거리가 곧 게이지다. D1708 은 표점 게이지를 두지 않고, D412 링은
          표점이 아니라 내부 원주로 초기 길이를 정의한다.

    DMA   자유길이·폭·두께 셋을 다 갖는 파트는 ISO 6721-4(인장) 하나뿐이다.
          -2·-3·-8·-10 은 자유길이가 없고, -6 전단·-10 평행판·-12 압축은
          폭이 없다(직경이다). ASTM D4065 는 "specimen size is not fixed by
          this practice" 라고 문장으로 못 박는다.

필수로 두면 그런 규격은 **저장 자체가 안 된다.** 필수 여부는 부서가 자기 규격을
보고 화면에서 정한다.

**우리가 넣은 네 줄만 되돌린다.** 관리자가 스스로 필수로 표시한 칸은 그대로 둔다
— 운영 중의 판단을 배포가 되돌리면 안 된다(기본 분류를 보장할 때와 같은 규칙).

Revision ID: c3b71e94a0d2
Revises: faf0432b7b88
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3b71e94a0d2"
down_revision = "faf0432b7b88"
branch_labels = None
depends_on = None

#: (분류 값, 칸 키). 우리가 기본으로 넣었던 것들.
SHIPPED = (
    ("인장", "gauge_length"),
    ("DMA", "free_length"),
    ("DMA", "width"),
    ("DMA", "thickness"),
)

_SQL = """
UPDATE specimen_fields AS f
   SET is_required = :required
  FROM vocabulary_terms AS t
  JOIN vocabularies AS v ON v.id = t.vocabulary_id
 WHERE f.category_term_id = t.id
   AND v.slug = 'specimen_category'
   AND t.value = :value
   AND f.key = :key
"""


def upgrade() -> None:
    bind = op.get_bind()
    for value, key in SHIPPED:
        bind.execute(sa.text(_SQL), {"required": False, "value": value, "key": key})


def downgrade() -> None:
    bind = op.get_bind()
    for value, key in SHIPPED:
        bind.execute(sa.text(_SQL), {"required": True, "value": value, "key": key})
