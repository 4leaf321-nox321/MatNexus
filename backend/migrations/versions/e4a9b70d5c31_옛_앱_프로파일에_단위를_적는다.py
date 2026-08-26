"""이미 깔린 **옛 앱 프로파일**의 시편 치수 규칙에 단위를 적는다.

`legacy_profiles.py` 의 기본값은 고쳤지만, 시드는 **이미 있으면 손대지 않는다** —
운영 중에 관리자가 고친 것을 되돌리면 안 되기 때문이다. 그래서 먼저 깔린
설치본은 고장 난 정의를 그대로 갖고 있다.

무엇이 고장 났나: `.mtet` 은 단위를 **열 이름 안에**만 갖고 있고(`(mm)`) 값 옆에는
`0.986` 뿐이다. 규칙이 키만 적으면 메타에 숫자만 들어가고, 읽는 쪽은 단위를
모르면 포기한다(`app/shared/curvedata.py`). **시편 치수가 조용히 안 채워지고
오류도 안 난다** — 세 단계 뒤 처리 1단계의 `@specimen_area` 가 그제서야 멈춘다.

**손대는 조건이 좁다.** 규칙이 처음 시드한 모양 그대로일 때만 바꾼다. 관리자가
한 글자라도 고쳤으면 그건 그 사람의 판단이므로 두고, 대신 아무것도 안 한다 —
자동 수리가 남의 결정을 덮는 것이 이 표에서 제일 나쁜 일이다.

되돌리기는 그 반대로, **이 마이그레이션이 적은 모양 그대로일 때만** 되돌린다.

Revision ID: e4a9b70d5c31
Revises: d3f5a81c62e7
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "e4a9b70d5c31"
down_revision = "d3f5a81c62e7"
branch_labels = None
depends_on = None

KEY = "legacy_mtet"

BEFORE = {
    "Specimen thickness a0 (mm)": "specimen_thickness",
    "Specimen width b0 (mm)": "specimen_width",
}

AFTER = {
    "Specimen thickness a0 (mm)": {"key": "specimen_thickness", "unit": "mm"},
    "Specimen width b0 (mm)": {"key": "specimen_width", "unit": "mm"},
}


def _swap(want: dict[str, object], give: dict[str, object]) -> None:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT id, definition FROM format_profiles "
                "WHERE key = :key AND owner_workspace_id IS NULL"
            ),
            {"key": KEY},
        )
        .all()
    )

    for row in rows:
        definition = row.definition
        if isinstance(definition, str):
            definition = json.loads(definition)
        if definition.get("specimen") != want:
            # 관리자가 고쳤다. 그 판단을 덮지 않는다.
            continue
        op.get_bind().execute(
            sa.text("UPDATE format_profiles SET definition = :definition WHERE id = :id"),
            {"definition": json.dumps({**definition, "specimen": give}), "id": row.id},
        )


def upgrade() -> None:
    _swap(BEFORE, AFTER)


def downgrade() -> None:
    _swap(AFTER, BEFORE)
