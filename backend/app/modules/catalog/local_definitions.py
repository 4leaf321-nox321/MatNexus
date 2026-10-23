"""MatNexus 가 정한 **문헌 정의 키의 씨앗**(2026-10-23, ADR 0068).

개발 서버에서 손으로 만든 정의는 운영에 없다(ADR 0047 의 교훈) — 서버마다
`add_catalog_property` 를 따로 부르면 설명 · 조건축이 갈린다. 반입 묶음이 쓰는 새 키(압축
곡선 · ε-N)는 씨앗으로 두고 배포(`refresh_builtins`)가 없는 것만 만든다. 키는 직접 넣기
규약 그대로 `local.` 로 시작한다 — 원본(MaterialTwin)이 나중에 같은 이름을 들여와도 겹치지
않는다.

있는 키는 건드리지 않는다 — 화면에서 고친 이름 · 정의문을 씨앗이 덮지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition
from matcore import units

SEED = Path(__file__).resolve().parents[3] / "seeds" / "catalog" / "local-definitions.json"


def load_seed(path: Path = SEED) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return rows


def ensure_local_definitions(
    db: Session, seed: list[dict[str, Any]] | None = None
) -> list[str]:
    """씨앗의 키 가운데 **없는 것만** 만든다. 만든 키를 돌려준다."""
    rows = load_seed() if seed is None else seed
    made: list[str] = []
    for row in rows:
        key = str(row["key"])
        if not key.startswith("local."):
            raise ValueError(f"씨앗 키는 local. 로 시작해야 합니다: {key}")
        if db.scalar(select(CatalogDefinition.id).where(CatalogDefinition.key == key)):
            continue
        si_unit = row.get("si_unit")
        if si_unit is not None and units.canonical(si_unit) is None:
            raise ValueError(f"씨앗 '{key}' 의 단위 '{si_unit}' 가 단위표에 없습니다.")
        db.add(
            CatalogDefinition(
                mt_id=None,
                created_by_id=None,
                key=key,
                domain=str(row["domain"]),
                name=str(row["name"]),
                symbol=row.get("symbol"),
                si_unit=units.canonical(si_unit) if si_unit is not None else None,
                value_type=str(row.get("value_type") or "numeric"),
                description=row.get("description"),
                test_standard=row.get("test_standard"),
                condition_axes=list(row.get("condition_axes") or []) or None,
            )
        )
        made.append(key)
    if made:
        db.flush()
    return made
