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


# --- 이관 정의에 축 덧붙이기 (2026-10-24, ADR 0071) ------------------------------------
#
# 원본(MaterialTwin) 정의의 조건축은 원본이 정한다 — 그런데 반입 묶음이 쓸 축이 원본에 없을
# 때가 있다(균열 성장률에 ΔK). DB 의 칸만 고치면 **배포마다 도는 이관이 원본 축으로 덮어**
# 조용히 되돌아간다. 그래서 덧붙일 축을 씨앗(`axis-extensions.json`)으로 두고 이관기와 씨앗
# 맞추기가 둘 다 붙인다 — 이관이 덮는 틈에도 빠지지 않게. 원본 축은 지우지도 바꾸지도 않고
# **뒤에 덧붙이기만** 한다.

AXIS_SEED = SEED.with_name("axis-extensions.json")


def axis_extensions(path: Path = AXIS_SEED) -> dict[str, list[str]]:
    """키 → 덧붙일 축."""
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["key"]): [str(one) for one in row["axes"]] for row in rows}


def extended_axes(
    key: str, axes: list[str] | None, extra: dict[str, list[str]] | None = None
) -> list[str] | None:
    """원본 축 뒤에 덧붙일 축을 — 이미 있는 것은 건너뛴다. 덧붙일 것이 없으면 그대로."""
    wanted = (axis_extensions() if extra is None else extra).get(key)
    if not wanted:
        return axes
    merged = list(axes or [])
    merged.extend(one for one in wanted if one not in merged)
    return merged


def ensure_axis_extensions(
    db: Session, extra: dict[str, list[str]] | None = None
) -> list[str]:
    """씨앗의 축이 빠진 정의에 덧붙인다. 바꾼 키를 돌려준다(정의가 없으면 건너뛴다)."""
    table = axis_extensions() if extra is None else extra
    changed: list[str] = []
    for key in table:
        found = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key))
        if found is None:
            continue
        merged = extended_axes(key, found.condition_axes, table)
        if merged != (found.condition_axes or []):
            found.condition_axes = merged
            changed.append(key)
    if changed:
        db.flush()
    return changed


# --- 문헌 조건 칸 목록 (2026-10-24, ADR 0071) -----------------------------------------
#
# 조건은 자유 칸이라 서버가 무엇이든 받는다 — 그러면 같은 뜻이 `aging_hours` · `aging_weeks`
# 처럼 둘로 갈리고, 검색 · 비교에서 서로를 못 찾는다. 반입하는 쪽(수집기)이 「공통 칸」 을 제
# 쪽에 따로 들고 있었는데 정본은 여기다. 정의의 조건축 밖이어도 이 목록의 이름이면 경고하지
# 않는다.

FIELD_SEED = SEED.with_name("condition-fields.json")


def condition_fields(path: Path = FIELD_SEED) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return rows


def condition_keys() -> set[str]:
    return {str(one["key"]) for one in condition_fields()}
