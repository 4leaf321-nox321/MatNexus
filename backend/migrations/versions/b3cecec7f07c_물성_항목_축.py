"""물성 항목 축

Revision ID: b3cecec7f07c
Revises: 59411592daec
Create Date: 2026-08-25 02:05:51.769385

"""

from typing import Sequence, Union

import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "b3cecec7f07c"
down_revision: Union[str, Sequence[str], None] = "59411592daec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """물성 항목 축과 기본 값 다섯.

    **시험이 주지 않는 물성을 넣을 자리가 없었다.** 탄성계수는 처리 결과에서만
    오고, 열팽창계수·비열·열전도도는 아예 자리가 없었다 — 그런데 그것들은
    인장시험이 안 주고 핸드북·규격에서 온다.

    **목록을 코드에 안 박는다**(D7). 열해석을 안 하는 부서에 비열 칸이 뜰 이유가
    없고, 반대로 코드에 박으면 필요한 항목을 넣으려고 배포를 기다려야 한다.

    값마다 **차원**을 든다. 그래야 값을 넣을 때 단위가 검사되고 「비열 자리에
    열전도도」가 막힌다 — ADR 0013 이 적어 둔 구멍이다.
    """
    from app.modules.vocabulary.definitions import (
        ensure_builtin_axis_fields,
        ensure_builtin_property_items,
        ensure_builtin_vocabularies,
    )

    session = Session(bind=op.get_bind())
    made = ensure_builtin_vocabularies(session)
    fields = ensure_builtin_axis_fields(session)
    items = ensure_builtin_property_items(session)
    session.commit()
    logging.getLogger("alembic").info(
        "축 %s · 칸 %s · 물성 항목 %s", made or "없음", fields or "없음", items or "없음"
    )


def downgrade() -> None:
    """축과 그 값을 지운다.

    **재료에 넣어 둔 선언 물성은 여기서 안 본다.** 그 컬럼은 다음 마이그레이션이
    만들고, 되돌리기는 역순이라 이 시점에는 이미 지워진 뒤다.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM vocabulary_terms WHERE vocabulary_id IN"
            " (SELECT id FROM vocabularies WHERE slug = 'property_item')"
        )
    )
    bind.execute(sa.text("DELETE FROM vocabularies WHERE slug = 'property_item'"))
