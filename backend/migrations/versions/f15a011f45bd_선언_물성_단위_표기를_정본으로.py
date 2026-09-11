"""선언 물성 단위 표기를 정본으로

## 왜

시드 스크립트가 선언 물성의 `input_unit` 을 `W/(m·K)`·`J/(kg·K)`(가운뎃점)로 넣었다.
단위표는 `W/(m.K)`·`J/(kg.K)`(온점)만 알아서, 읽을 때마다 단위를 모른다고 지우고
SI 값만 보였다 — 실측(2026-09-11) 재료·시료의 선언 물성 147건. 값은 안 틀렸다(인수가
1인 단위)지만 화면에 단위 없는 숫자가 147개 떠 있었다.

## 무엇을 하나

`materials.declared_properties`·`samples.declared_properties`(JSONB 배열)의 각 줄에서
`input_unit` 이 표기만 다른 것을 정본 기호로 바꾼다. **표가 모르는 것은 그대로 둔다** —
지어내지 않는다. 읽는 쪽(`units.unit_of`)도 이제 표기 차이를 받으므로 이 이관은
데이터를 깨끗이 하는 것이지 화면을 살리는 조건은 아니다.

값(`value_si`)은 건드리지 않는다. 단위 기호만 바뀐다.

## 저장 단위도 줄에 적는다

같은 김에 각 줄에 `si_unit`(저장 단위)을 적는다 — 항목의 차원(기준정보
`property_item`)에서 온다. 전에는 응답이 SI 값만 주고 그 값의 단위는 안 줘서,
MCP 가 AI 에게 `values_si: [2.06e11]` 만 넘겼다. 값과 단위가 떨어져 있으면 언젠가
어긋난다(ADR 0004). 새로 저장되는 줄은 쓰는 쪽(`declared.normalize`)이 적는다.

Revision ID: f15a011f45bd
Revises: fc0ec59d424a
Create Date: 2026-09-11 19:40:00

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from matcore import units

# revision identifiers, used by Alembic.
revision: str = "f15a011f45bd"
down_revision: Union[str, Sequence[str], None] = "fc0ec59d424a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("materials", "samples")


def _fixed(rows: list[dict], si_by_item: dict[str, str]) -> tuple[list[dict], int]:
    """표기만 다른 `input_unit` 을 정본으로, 빠진 `si_unit` 을 채워서. 몇 줄을 고쳤는지 함께."""
    changed = 0
    out: list[dict] = []
    for row in rows:
        symbol = row.get("input_unit")
        if isinstance(symbol, str) and symbol not in units.UNITS:
            found = units.canonical(symbol)
            if found is not None and found != symbol:
                row = {**row, "input_unit": found}
                changed += 1
        if not row.get("si_unit"):
            si_unit = si_by_item.get(str(row.get("item")))
            if si_unit:
                row = {**row, "si_unit": si_unit}
                changed += 1
        out.append(row)
    return out, changed


def _si_by_item(bind) -> dict[str, str]:
    """기준정보 `property_item` 축의 값 → 저장 단위. 차원이 없으면 무차원으로 본다
    (`declared.catalog` 과 같은 규칙)."""
    rows = bind.execute(
        sa.text(
            "SELECT t.value, t.attributes->>'dimension' FROM vocabulary_terms t "
            "JOIN vocabularies v ON v.id = t.vocabulary_id WHERE v.slug = 'property_item'"
        )
    ).all()
    return {
        value: units.SI_UNITS.get(dimension or "dimensionless", "1")
        for value, dimension in rows
    }


def upgrade() -> None:
    bind = op.get_bind()
    si_by_item = _si_by_item(bind)
    for table in TABLES:
        rows = bind.execute(
            sa.text(
                f"SELECT id, declared_properties FROM {table} "
                "WHERE declared_properties IS NOT NULL AND declared_properties::text <> '[]'"
            )
        ).all()
        for row_id, declared in rows:
            if not isinstance(declared, list):
                continue
            fixed, changed = _fixed(declared, si_by_item)
            if changed:
                bind.execute(
                    sa.text(
                        f"UPDATE {table} SET declared_properties = CAST(:value AS jsonb) "
                        "WHERE id = :id"
                    ),
                    {"value": json.dumps(fixed), "id": row_id},
                )


def downgrade() -> None:
    # 기호를 정본으로 바꾼 것뿐이다. 되돌릴 옛 표기가 무엇이었는지는 남기지 않았고,
    # 정본 기호는 옛 코드도 읽는다 — 되돌릴 것이 없다.
    pass
