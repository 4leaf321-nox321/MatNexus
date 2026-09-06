"""기본 물성 항목 재시드 — 밀시트 넷(항복·인장·연신·경도)이 옛 DB 에 없다

Revision ID: c7a4e0b93f16
Revises: b9e2f5a8c1d4
Create Date: 2026-09-06

**씨앗이 뒤늦게 늘었는데 이미 돈 마이그레이션은 다시 안 돈다.**

    v1.71.0 (b3cecec7f07c)  물성 항목 축 + 기본값 **다섯**을 심었다
    v1.73.0                 상수에 밀시트 넷(항복강도·인장강도·연신율·경도)이
                            늘었다 — 그런데 그 마이그레이션은 이미 돈 뒤다

그래서 **v1.71.0 이후에 만든 DB 는 아홉 개를 다 받고, 그 전에 만든 DB(개발·
운영)는 다섯 개에서 멈춘다.** 새 DB 로만 도는 시험은 이것을 못 본다 —
실측(2026-09-06): 개발 서버에서 재료에 항복강도를 적으려 하자 「기준정보의
'물성 항목' 축에 먼저 넣으세요」 로 막혔고, 그 바람에 v1.73.0 의 밀시트 대조와
문헌 강도값 채택·합성 곡선이 통째로 닫혀 있었다.

`ensure_builtin_property_items` 는 **이미 있는 것은 손대지 않는다**(부서가 이름을
고치거나 지웠을 수 있고 배포가 그것을 되돌리면 안 된다) — 그래서 다시 부르는
것으로 충분하고, 여러 번 돌아도 같다. 손으로 쓴 마이그레이션이다.
"""

import logging
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = "c7a4e0b93f16"
down_revision: Union[str, Sequence[str], None] = "b9e2f5a8c1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.modules.vocabulary.definitions import ensure_builtin_property_items

    session = Session(bind=op.get_bind())
    made = ensure_builtin_property_items(session)
    session.commit()
    logging.getLogger("alembic").info("물성 항목 보강: %s", made or "없음(이미 다 있었다)")


def downgrade() -> None:
    """되돌리지 않는다.

    이 마이그레이션이 심은 항목에 **사람이 값을 적었을 수 있다.** 항목을 지우면
    그 값들이 「기준정보에 없는 항목」 이 되어 화면에서 고아가 된다 — 되돌릴 수
    없는 것을 되돌리는 척하지 않는다.
    """
