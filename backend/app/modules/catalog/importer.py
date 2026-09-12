"""materialtwin.db → 카탈로그 이관 — **무손실·멱등·환경 무관** (ADR 0027).

세 가지 약속:

    무손실     원본 컬럼 전부가 1:1 로 간다. 원본 표에 **모르는 컬럼이 있으면
              진행을 거부**한다 — 미래 스냅샷의 새 컬럼이 조용히 버려지는 일을
              구조로 막는다. 컬럼이 빠져 있어도 거부한다(스키마가 다른 파일이다).
    멱등       각 행의 원본 id 를 `mt_id` 로 들고, 재실행은 갱신이지 중복이
              아니다. **지우는 일은 없다.**
    파일이 문   개발이든 운영이든 이 이관기 + 원본 .db 파일로만 데이터가 들어온다.
              개발 DB 를 운영으로 복사하는 경로는 만들지 않는다 — 개발 DB 에는
              테스트 임시 데이터가 섞여 있다.

공통 부품(스키마 대조·멱등 upsert·수치 비교)은 `app/shared/mt_import.py` 에
산다 — 측정법 이관기와 나눠 쓰는데 모듈끼리는 직접 못 부르기 때문이다.
쓰는 쪽은 `scripts/import_materialtwin.py` (드라이런이 기본, `--apply` 라야
커밋한다 — 원본 파이프라인의 규율 그대로).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    QUALITY_TIERS,
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.shared.mt_import import (
    ImportRefused as ImportRefused,  # 재수출 — 테스트·스크립트가 여기서 부른다
)
from app.shared.mt_import import (
    Report as Report,
)
from app.shared.mt_import import (
    TableReport as TableReport,
)
from app.shared.mt_import import (
    check_schema,
    existing,
    parse_dt,
    parse_json,
    upsert,
)

#: 원본 표의 컬럼 전수 — 여기 없는 컬럼이 나타나면 거부한다.
#: `material.owner_id` 는 원본이 만들고 안 쓴 자리다. 컬럼을 받지는 않지만,
#: 값이 하나라도 차 있으면 그것은 "모르는 데이터"이므로 거부한다.
EXPECTED_COLUMNS: dict[str, frozenset[str]] = {
    "material": frozenset(
        {
            "id",
            "name",
            "material_code",
            "category",
            "description",
            "attributes",
            "owner_id",
            "created_at",
            "updated_at",
        }
    ),
    "source": frozenset(
        {
            "id",
            "kind",
            "doi",
            "isbn",
            "url",
            "title",
            "authors",
            "year",
            "publisher",
            "license",
            "local_path",
            "content_hash",
            "retrieved_at",
            "created_at",
        }
    ),
    "property_definition": frozenset(
        {
            "id",
            "key",
            "domain",
            "name",
            "symbol",
            "si_unit",
            "value_type",
            "description",
            "test_standard",
            "condition_axes",
            "created_at",
        }
    ),
    "property_value": frozenset(
        {
            "id",
            "material_id",
            "property_key",
            "value_num",
            "value_text",
            "unit",
            "uncertainty",
            "conditions",
            "method",
            "quality_tier",
            "source_id",
            "source_detail",
            "notes",
            "created_at",
        }
    ),
}

#: attributes 에서 검색용으로 발췌하는 키. 정본은 attributes 쪽이다.
FACET_KEYS = ("subsystem", "role", "manufacturer", "material_class", "grade")


def _check_schema(con: sqlite3.Connection) -> None:
    check_schema(con, EXPECTED_COLUMNS)
    stray = con.execute("select count(*) from material where owner_id is not null").fetchone()[
        0
    ]
    if stray:
        raise ImportRefused(
            f"material.owner_id 가 채워진 행이 {stray}건 — 원본에서 안 쓰던 자리에 "
            "값이 생겼습니다. 무엇인지 확인 전에는 나르지 않습니다."
        )


def run(db: Session, sqlite_path: str | Path) -> Report:
    """이관 본체. **커밋하지 않는다** — 드라이런/적용은 부르는 쪽이 정한다.

    순서는 FK 의존 역순이다: 정의 → 출처 → 재료 → 값.
    """
    path = Path(sqlite_path)
    if not path.is_file():
        raise ImportRefused(f"파일이 없습니다: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        _check_schema(con)
        report = Report()

        defs = report.tables.setdefault("정의", TableReport())
        def_cache = existing(db, CatalogDefinition)
        for row in con.execute("select * from property_definition"):
            upsert(
                db,
                def_cache,
                CatalogDefinition,
                row["id"],
                {
                    "key": row["key"],
                    "domain": row["domain"],
                    "name": row["name"],
                    "symbol": row["symbol"],
                    "si_unit": row["si_unit"],
                    "value_type": row["value_type"],
                    "description": row["description"],
                    "test_standard": row["test_standard"],
                    "condition_axes": parse_json(row["condition_axes"]),
                    "source_created_at": parse_dt(row["created_at"]),
                },
                defs,
            )
        db.flush()

        sources = report.tables.setdefault("출처", TableReport())
        source_cache = existing(db, CatalogSource)
        source_ids: dict[int, Any] = {}
        for row in con.execute("select * from source"):
            item = upsert(
                db,
                source_cache,
                CatalogSource,
                row["id"],
                {
                    "kind": row["kind"],
                    "doi": row["doi"],
                    "isbn": row["isbn"],
                    "url": row["url"],
                    "title": row["title"],
                    "authors": row["authors"],
                    "year": row["year"],
                    "publisher": row["publisher"],
                    "license": row["license"],
                    "local_path": row["local_path"],
                    "content_hash": row["content_hash"],
                    "source_retrieved_at": parse_dt(row["retrieved_at"]),
                    "source_created_at": parse_dt(row["created_at"]),
                },
                sources,
            )
            source_ids[row["id"]] = item
        db.flush()

        materials = report.tables.setdefault("재료", TableReport())
        material_cache = existing(db, CatalogMaterial)
        material_ids: dict[int, Any] = {}
        for row in con.execute("select * from material"):
            attributes = parse_json(row["attributes"])
            facets = {key: (attributes or {}).get(key) or None for key in FACET_KEYS}
            item = upsert(
                db,
                material_cache,
                CatalogMaterial,
                row["id"],
                {
                    "name": row["name"],
                    "material_code": row["material_code"],
                    "category": row["category"],
                    "description": row["description"],
                    "attributes": attributes,
                    **facets,
                    "source_created_at": parse_dt(row["created_at"]),
                    "source_updated_at": parse_dt(row["updated_at"]),
                },
                materials,
            )
            material_ids[row["id"]] = item
        db.flush()

        values = report.tables.setdefault("값", TableReport())
        value_cache = existing(db, CatalogValue)
        known_keys = {one.key for one in def_cache.values()}
        for row in con.execute("select * from property_value"):
            if row["property_key"] not in known_keys:
                raise ImportRefused(
                    f"물성값 #{row['id']} 의 키 {row['property_key']!r} 가 정의에 없습니다."
                )
            if row["quality_tier"] not in QUALITY_TIERS:
                raise ImportRefused(
                    f"물성값 #{row['id']} 의 quality_tier={row['quality_tier']!r} 는 "
                    "아는 등급(1~4)이 아닙니다."
                )
            upsert(
                db,
                value_cache,
                CatalogValue,
                row["id"],
                {
                    "material_id": material_ids[row["material_id"]].id,
                    "property_key": row["property_key"],
                    "value_num": row["value_num"],
                    "value_text": row["value_text"],
                    "unit": row["unit"],
                    "uncertainty": row["uncertainty"],
                    "conditions": parse_json(row["conditions"]),
                    "method": row["method"],
                    "quality_tier": row["quality_tier"],
                    "source_id": (
                        source_ids[row["source_id"]].id
                        if row["source_id"] is not None
                        else None
                    ),
                    "source_detail": row["source_detail"],
                    "notes": row["notes"],
                    "source_created_at": parse_dt(row["created_at"]),
                },
                values,
            )
        db.flush()

        report.problems = verify(db, con)
        return report
    finally:
        con.close()


def verify(db: Session, con: sqlite3.Connection) -> list[str]:
    """이관 뒤 검산 — 원본 무결성 검사의 축소판. 빈 목록이 합격이다."""
    problems: list[str] = []

    counts: list[tuple[str, Any, str]] = [
        ("property_definition", CatalogDefinition.mt_id, "정의"),
        ("source", CatalogSource.mt_id, "출처"),
        ("material", CatalogMaterial.mt_id, "재료"),
        ("property_value", CatalogValue.mt_id, "값"),
    ]
    # 여기서 직접 넣은 줄(`mt_id IS NULL`)은 원본에 없다 — 세면 늘 불일치다.
    for src_table, mt_id, label in counts:
        src = con.execute(f"select count(*) from {src_table}").fetchone()[0]
        dst = db.scalar(select(func.count(mt_id)))
        if src != dst:
            problems.append(f"{label} 행수 불일치 — 원본 {src} vs 이관 {dst}")

    # 출처 없는 값 — 원본이 0건을 유지해 온 불변식이다.
    src_null = con.execute(
        "select count(*) from property_value where source_id is null"
    ).fetchone()[0]
    dst_null = db.scalar(
        select(func.count())
        .select_from(CatalogValue)
        .where(CatalogValue.source_id.is_(None), CatalogValue.mt_id.is_not(None))
    )
    if src_null != dst_null:
        problems.append(f"출처 없는 값 불일치 — 원본 {src_null} vs 이관 {dst_null}")

    # tier4 개수 — 「근거 없는 값」 표시가 이관에서 떨어졌는지.
    src_t4 = con.execute(
        "select count(*) from property_value where quality_tier = 4"
    ).fetchone()[0]
    dst_t4 = db.scalar(
        select(func.count())
        .select_from(CatalogValue)
        .where(CatalogValue.quality_tier == 4, CatalogValue.mt_id.is_not(None))
    )
    if src_t4 != dst_t4:
        problems.append(f"tier4 개수 불일치 — 원본 {src_t4} vs 이관 {dst_t4}")

    return problems
