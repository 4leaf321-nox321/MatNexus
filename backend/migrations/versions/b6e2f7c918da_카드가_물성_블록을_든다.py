"""카드가 물성 블록을 든다

**물성의 갈래가 컬럼 이름이었다.** `elastic`·`hardening`·`table` 셋을 모델·스키마·
라우트·화면이 각각 이름으로 알고 있어서, 점탄성을 더하려면 네 번째 컬럼이,
초탄성이면 다섯 번째가 필요했다 — 매번 마이그레이션과 스키마와 화면이 딸려 온다.

폴리머 점탄성 슬라이스에서 D7 이 못 미친 45%(저장·API·화면)의 정체가 그것이다.
경화식은 이미 데이터였는데(`FAMILIES`), **물성의 갈래는 코드였다.**

셋 다 이미 JSONB 였다. 안은 형식이 없는데 바깥의 컬럼 이름만 굳어 있었다.

여기서 `blocks` 한 칸으로 모은다. 무엇이 들어갈 수 있는지는 `matcore.cards`
레지스트리가 알고, 새 물성 1종에 드는 것은 `BlockSpec` 하나다 — 마이그레이션 0.

## 담기는 모양

    {블록 key: {"values": {키: 값}, "rows": [{열: 값}], "notes": [문장]}}

경화식의 `parameters` 가 `rows` 로, `notes` 가 `notes` 로 간다. 나머지 스칼라는
전부 `values` 다. 탄성은 통째로 `values` 이고, 소성 표는 통째로 `rows` 다.

**지금이 제일 싸다.** 카드가 쌓일수록 백필이 무겁고, 컬럼 이름을 아는 코드가 는다.

Revision ID: b6e2f7c918da
Revises: f4a9d6b2c10e
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6e2f7c918da"
down_revision = "f4a9d6b2c10e"
branch_labels = None
depends_on = None


#: 빈 블록은 안 싣는다. `{}` 가 있는 것과 없는 것이 같은 뜻이면, 화면이 "탄성을
#: 아직 안 넣었다" 와 "탄성이 비어 있다" 를 가를 수 없다.
BACKFILL = """
UPDATE property_cards SET blocks =
      (CASE WHEN elastic <> '{}'::jsonb
            THEN jsonb_build_object('elastic', jsonb_build_object('values', elastic))
            ELSE '{}'::jsonb END)
   || (CASE WHEN hardening <> '{}'::jsonb
            THEN jsonb_build_object('hardening', jsonb_build_object(
                     'values', hardening - 'parameters' - 'notes',
                     'rows', COALESCE(hardening -> 'parameters', '[]'::jsonb),
                     'notes', COALESCE(hardening -> 'notes', '[]'::jsonb)))
            ELSE '{}'::jsonb END)
   || (CASE WHEN "table" <> '[]'::jsonb
            THEN jsonb_build_object('table', jsonb_build_object('rows', "table"))
            ELSE '{}'::jsonb END)
"""

#: 되돌리기. **점탄성 블록은 갈 곳이 없다** — 옛 스키마에 그 컬럼이 없다.
#: 조용히 버리지 않고 여기 적어 둔다: 되돌리면 점탄성 카드는 값을 잃는다.
RESTORE = """
UPDATE property_cards SET
    elastic = COALESCE(blocks -> 'elastic' -> 'values', '{}'::jsonb),
    hardening = COALESCE(blocks -> 'hardening' -> 'values', '{}'::jsonb)
        || jsonb_build_object(
               'parameters', COALESCE(blocks -> 'hardening' -> 'rows', '[]'::jsonb),
               'notes', COALESCE(blocks -> 'hardening' -> 'notes', '[]'::jsonb)),
    "table" = COALESCE(blocks -> 'table' -> 'rows', '[]'::jsonb)
WHERE blocks <> '{}'::jsonb
"""


def upgrade() -> None:
    op.add_column(
        "property_cards",
        sa.Column(
            "blocks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(BACKFILL)
    op.drop_column("property_cards", "elastic")
    op.drop_column("property_cards", "hardening")
    op.drop_column("property_cards", "table")


def downgrade() -> None:
    for name, default in (("elastic", "{}"), ("hardening", "{}"), ("table", "[]")):
        op.add_column(
            "property_cards",
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=default,
            ),
        )
    op.execute(RESTORE)
    op.drop_column("property_cards", "blocks")
