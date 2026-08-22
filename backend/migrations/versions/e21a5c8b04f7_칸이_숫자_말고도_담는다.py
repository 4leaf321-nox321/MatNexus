"""칸이 숫자 말고도 담는다

규격은 치수만 갖지 않는다.

    판(edition)   `D638-22`. ASTM 이 못 박는다 — "규격 번호만으로는 부족하다.
                  판 연도와 시편 타입을 함께 지정해야 한다." 판이 다르면 치수가
                  다르고, E8 과 E8M 은 환봉 게이지 길이가 4D 대 5D 라 연신율을
                  직접 비교할 수 없다.
    모드          이중 캔틸레버 · 3점 굽힘 · 전단 샌드위치 … DMA 규격은 대개
                  치수를 안 정하고 모드만 정한 뒤 장비 클램프에 넘긴다.
    단부 형식     나사 · 숄더 · 평행 · 버튼헤드 (E8 환봉)

숫자 칸만 두면 이것들이 값 이름에 섞이고, `D638 Type I` 과 `D638-22 Type I` 이
별개 값으로 갈린다 — 애초에 풀려던 병이 되돌아온다.

그리고 **기호**. 규격서와 도면은 뜻이 아니라 글자로 적혀 있고, 같은 글자가
규격마다 다른 뜻이다 — E8 의 `D` 는 직경, D638 의 `D` 는 그립 간 거리다. `key`
는 뜻으로 짓고 글자는 따로 담는다. 분류가 선언한 칸의 글자는 규격마다 다르므로
(게이지 길이가 E8 은 `G`, ISO 527-2 는 `L₀`) 규격이 덮어쓸 수 있어야 한다.

    vocabularies.base_fields         축의 값이면 무엇이든 갖는 칸
    vocabulary_terms.field_symbols   이 규격이 그 칸을 부르는 글자
    specimen_fields.kind/choices/symbol

Revision ID: e21a5c8b04f7
Revises: d7c04f1a9e13
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e21a5c8b04f7"
down_revision = "d7c04f1a9e13"
branch_labels = None
depends_on = None

#: 시편 규격 축이 갖는 칸. `definitions.BUILTIN_AXIS_FIELDS` 의 그때 스냅샷이다.
EDITION = [
    {
        "key": "edition",
        "label": "판(edition)",
        "kind": "text",
        "choices": [],
        "symbol": None,
        "dimension": "dimensionless",
        "si_unit": "1",
        "is_required": False,
        "help": "규격의 판 연도. 판이 다르면 치수가 다릅니다 — "
        "`-22`, `-24`, `-17(2025)` 처럼 규격서 표기 그대로 적으세요.",
    }
]

#: DMA 분류의 변형 모드. **모드가 곧 시편 형상이다.**
MODES = [
    "이중 캔틸레버",
    "단일 캔틸레버",
    "3점 굽힘",
    "인장",
    "압축",
    "전단 샌드위치",
    "비틀림",
    "평행판",
]


def upgrade() -> None:
    op.add_column(
        "vocabularies",
        sa.Column(
            "base_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "vocabulary_terms",
        sa.Column(
            "field_symbols",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "specimen_fields",
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="number"),
    )
    op.add_column(
        "specimen_fields",
        sa.Column(
            "choices",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column("specimen_fields", sa.Column("symbol", sa.String(length=20), nullable=True))

    bind = op.get_bind()

    # **이미 칸이 있으면 안 덮는다** — 관리자가 고쳤을 수 있다.
    bind.execute(
        sa.text(
            "UPDATE vocabularies SET base_fields = :fields "
            "WHERE slug = 'specimen_standard' AND base_fields = '[]'::jsonb"
        ),
        {"fields": json.dumps(EDITION, ensure_ascii=False)},
    )

    # DMA 분류에 변형 모드 칸을 더한다. 같은 키가 이미 있으면 건너뛴다.
    dma = bind.execute(
        sa.text("""
        SELECT t.id FROM vocabulary_terms AS t
          JOIN vocabularies AS v ON v.id = t.vocabulary_id
         WHERE v.slug = 'specimen_category' AND t.value = 'DMA'
        """)
    ).scalar()
    if dma is not None:
        taken = bind.execute(
            sa.text(
                "SELECT 1 FROM specimen_fields WHERE category_term_id = :id AND key = 'mode'"
            ),
            {"id": dma},
        ).scalar()
        if not taken:
            bind.execute(
                sa.text("""
                INSERT INTO specimen_fields
                    (id, category_term_id, key, label, kind, choices, symbol,
                     dimension, si_unit, is_required, help, sort_order)
                VALUES
                    (gen_random_uuid(), :id, 'mode', '변형 모드', 'choice', :choices, NULL,
                     'dimensionless', '1', false, :help, -10)
                """),
                {
                    "id": dma,
                    "choices": json.dumps(MODES, ensure_ascii=False),
                    "help": "모드가 곧 시편 형상입니다. 보고서에는 규격 번호만이 아니라 "
                    "모드·스팬·시편 치수를 함께 적어야 재현이 됩니다.",
                },
            )


def downgrade() -> None:
    op.drop_column("specimen_fields", "symbol")
    op.drop_column("specimen_fields", "choices")
    op.drop_column("specimen_fields", "kind")
    op.drop_column("vocabulary_terms", "field_symbols")
    op.drop_column("vocabularies", "base_fields")
