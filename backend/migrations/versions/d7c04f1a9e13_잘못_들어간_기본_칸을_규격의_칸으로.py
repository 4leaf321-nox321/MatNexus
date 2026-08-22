"""잘못 들어간 기본 칸을 규격의 칸으로

화면이 **"분류냐 규격이냐" 를 값의 상태로 가늠했다** — 상위 값이 비어 있으면
분류로 봤다. 그런데 분류를 아직 안 정한 규격이 있다. 그런 규격에서 '이 규격만의
칸' 을 만들면 그 칸이 `vocabulary_terms.extra_fields` 가 아니라 **분류 기본 칸
표**(`specimen_fields`)로 들어갔다.

들어간 뒤에는 손댈 길이 없었다. 규격 화면은 그 칸을 자기 칸으로 안 보고, 분류
화면에는 그 값이 안 뜬다. 개발 DB 에서 실제로 그렇게 됐다 —
`ASTM E8 subsize` 에 `aaa` 칸 하나가 남아 있었다.

**지우지 않고 옮긴다.** 사람이 만들려던 것은 "이 규격의 칸" 이었으니, 그 자리로
보내면 의도대로 되고 화면에서 고치거나 지울 수 있게 된다.

옮기는 대상은 `attribute_source='parent'` 인 축의 값에 달린 기본 칸뿐이다 —
그런 축의 값은 기본 칸을 선언하지 않는다(이제 서버도 거절한다). 진짜 분류
(`specimen_category`)의 기본 칸은 건드리지 않는다.

Revision ID: d7c04f1a9e13
Revises: c3b71e94a0d2
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "d7c04f1a9e13"
down_revision = "c3b71e94a0d2"
branch_labels = None
depends_on = None

_STRAYS = sa.text("""
SELECT f.id, f.category_term_id, f.key, f.label, f.dimension, f.si_unit,
       f.is_required, f.help
  FROM specimen_fields AS f
  JOIN vocabulary_terms AS t ON t.id = f.category_term_id
  JOIN vocabularies     AS v ON v.id = t.vocabulary_id
 WHERE v.attribute_source = 'parent'
 ORDER BY f.sort_order
""")


def upgrade() -> None:
    bind = op.get_bind()
    moved: dict[str, list[dict[str, object]]] = {}
    ids: list[str] = []
    for row in bind.execute(_STRAYS).mappings():
        moved.setdefault(str(row["category_term_id"]), []).append(
            {
                "key": row["key"],
                "label": row["label"],
                "dimension": row["dimension"] or "length",
                "si_unit": row["si_unit"] or "m",
                "is_required": bool(row["is_required"]),
                "help": row["help"],
            }
        )
        ids.append(str(row["id"]))

    for term_id, fields in moved.items():
        current = bind.execute(
            sa.text("SELECT extra_fields FROM vocabulary_terms WHERE id = :id"),
            {"id": term_id},
        ).scalar()
        existing = list(current or [])
        have = {str(item.get("key")) for item in existing}
        # **이미 같은 키가 있으면 안 덮는다.** 규격 쪽 값이 사람이 나중에 고친
        # 것일 수 있다.
        existing.extend(item for item in fields if item["key"] not in have)
        bind.execute(
            sa.text("UPDATE vocabulary_terms SET extra_fields = :fields WHERE id = :id"),
            {"fields": json.dumps(existing, ensure_ascii=False), "id": term_id},
        )

    if ids:
        bind.execute(
            sa.text("DELETE FROM specimen_fields WHERE id = ANY(:ids)"),
            {"ids": [__import__("uuid").UUID(one) for one in ids]},
        )


def downgrade() -> None:
    """되돌리지 않는다.

    옮긴 칸을 다시 기본 칸 표로 보내면 **또 손댈 수 없는 상태**가 된다. 값은
    `extra_fields` 에 그대로 있으므로 잃은 것은 없다.
    """
