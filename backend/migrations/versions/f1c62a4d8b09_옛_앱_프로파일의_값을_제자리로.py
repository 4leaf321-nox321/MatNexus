"""이미 깔린 **옛 앱 프로파일**의 값들을 제자리로 옮긴다.

시험이 낸 결과가 아닌 것이 결과 자리에 있지도 않았고, 그렇다고 제자리에 있지도
않았다 — 다섯이 전부 `metadata`(원문 보관)에 있었다. 보관은 글자로만 남아서
비교도 통계도 안 되는데, 그 값들이 갈 **제자리가 이미 있었다.**

    Operator          → 시험 기록의 시험자
    Instrument name   → 시험 기록의 장비 (기준정보로 묶인다)
    rundate           → 시험 기록의 시험일
    Sensor Type       → 시험 조건 `sensor_type`  (인장 종류가 선언한 칸)
    Testing Group     → 시험 조건 `testing_group`
    Specimen Number   → 어느 시편인지 짚기

`legacy_profiles.py` 의 기본값은 고쳤지만, 시드는 **이미 있으면 손대지 않는다** —
운영 중에 관리자가 고친 것을 되돌리면 안 되기 때문이다. 그래서 먼저 깔린
설치본은 옛 배치를 그대로 갖고 있다.

**손대는 조건이 좁다.** `metadata` 가 처음 시드한 목록 그대로이고 `record`·
`conditions`·`identity` 가 아직 없을 때만 바꾼다. 관리자가 한 자리라도 고쳤으면
그건 그 사람의 판단이므로 아무것도 안 한다.

**이미 들어온 시험은 안 건드린다.** 이 마이그레이션은 앞으로 읽을 파일에만
영향을 준다 — 옛 시험을 고치려면 원본을 **다시 읽으면** 되고, 그것이 원본을
보관하는 이유다(ADR 0005).

Revision ID: f1c62a4d8b09
Revises: e4a9b70d5c31
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "f1c62a4d8b09"
down_revision = "e4a9b70d5c31"
branch_labels = None
depends_on = None

KEY = "legacy_mtet"

OLD_METADATA = [
    "rundate",
    "Instrument name",
    "Operator",
    "Specimen Number",
    "Specimen Standard",
    "Sensor Type",
    "Testing Group",
    "Technical Data Record Name",
    "Tensile Data ID",
]

NEW_METADATA = [
    "Specimen Standard",
    "Technical Data Record Name",
    "Tensile Data ID",
]

MOVED: dict[str, Any] = {
    "record": {
        "Operator": {"field": "operator"},
        "Instrument name": {"field": "instrument"},
        "rundate": {"field": "tested_at", "format": "%Y-%m-%d %H:%M:%S"},
    },
    "conditions": {
        "Sensor Type": {"field": "sensor_type"},
        "Testing Group": {"field": "testing_group"},
    },
    "identity": {"Specimen Number": {"field": "specimen_seq_no"}},
}


def _rows() -> list[Any]:
    return list(
        op.get_bind().execute(
            sa.text(
                "SELECT id, definition FROM format_profiles "
                "WHERE key = :key AND owner_workspace_id IS NULL"
            ),
            {"key": KEY},
        )
    )


def _definition(row: Any) -> dict[str, Any]:
    found = row.definition
    return json.loads(found) if isinstance(found, str) else dict(found)


def _write(row_id: Any, definition: dict[str, Any]) -> None:
    op.get_bind().execute(
        sa.text("UPDATE format_profiles SET definition = :definition WHERE id = :id"),
        {"definition": json.dumps(definition, ensure_ascii=False), "id": row_id},
    )


def upgrade() -> None:
    for row in _rows():
        definition = _definition(row)
        untouched = definition.get("metadata") == OLD_METADATA and not any(
            definition.get(where) for where in MOVED
        )
        if not untouched:
            # 관리자가 고쳤다. 그 판단을 덮지 않는다.
            continue
        _write(row.id, {**definition, **MOVED, "metadata": NEW_METADATA})


def downgrade() -> None:
    for row in _rows():
        definition = _definition(row)
        if definition.get("metadata") != NEW_METADATA:
            continue
        if any(definition.get(where) != rule for where, rule in MOVED.items()):
            continue
        back = {key: value for key, value in definition.items() if key not in MOVED}
        _write(row.id, {**back, "metadata": OLD_METADATA})
