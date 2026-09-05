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

쓰는 쪽은 `scripts/import_materialtwin.py` (드라이런이 기본, `--apply` 라야
커밋한다 — 원본 파이프라인의 규율 그대로).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
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


class ImportRefused(Exception):
    """이관을 시작할 수 없는 상태 — 파일이 아는 스키마가 아니다."""


@dataclass
class TableReport:
    added: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.added + self.updated + self.unchanged


@dataclass
class Report:
    tables: dict[str, TableReport] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def line(self) -> str:
        parts = [
            f"{name}: 추가 {t.added} · 갱신 {t.updated} · 동일 {t.unchanged}"
            for name, t in self.tables.items()
        ]
        return "\n".join(parts)


def _check_schema(con: sqlite3.Connection) -> None:
    """컬럼 전수 대조 — 모르는 컬럼도, 빠진 컬럼도 거부."""
    for table, expected in EXPECTED_COLUMNS.items():
        rows = con.execute(f'PRAGMA table_info("{table}")').fetchall()
        if not rows:
            raise ImportRefused(f"원본에 {table} 표가 없습니다 — 카탈로그 DB 가 맞습니까?")
        actual = {row[1] for row in rows}
        extra = actual - expected
        missing = expected - actual
        if extra or missing:
            raise ImportRefused(
                f"{table} 표의 컬럼이 아는 스키마와 다릅니다 — "
                f"모르는 컬럼 {sorted(extra)}, 빠진 컬럼 {sorted(missing)}. "
                "새 스냅샷에 컬럼이 생겼다면 매핑을 늘린 뒤 다시 돌리세요 — "
                "조용히 버리는 것보다 멈추는 것이 낫습니다."
            )
    stray = con.execute("select count(*) from material where owner_id is not null").fetchone()[
        0
    ]
    if stray:
        raise ImportRefused(
            f"material.owner_id 가 채워진 행이 {stray}건 — 원본에서 안 쓰던 자리에 "
            "값이 생겼습니다. 무엇인지 확인 전에는 나르지 않습니다."
        )


def _dt(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    return datetime.fromisoformat(str(raw))


def _json(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


def _same(a: Any, b: Any) -> bool:
    """숫자는 수치로 비교한다 — PG JSONB 는 `1e+23` 을 정확한 정수(10²³)로
    정규화해 돌려주는데, 파이썬 float 1e23 과는 `==` 가 어긋난다(이진 표현 차).
    이 차이를 「갱신」 으로 읽으면 재실행마다 같은 행을 다시 쓴다 — 실측
    (springer2020 Prony 조건의 tau_s=1e23)에서 잡았다."""
    if (
        isinstance(a, (int, float))
        and isinstance(b, (int, float))
        and not isinstance(a, bool)
        and not isinstance(b, bool)
    ):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[key], b[key]) for key in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def _existing(db: Session, model: Any) -> dict[int, Any]:
    """mt_id → 행 선적재 — 42,209건에 행마다 SELECT 를 치지 않는다."""
    return {row.mt_id: row for row in db.scalars(select(model))}


def _upsert(
    db: Session,
    cache: dict[int, Any],
    model: Any,
    mt_id: int,
    fields: dict[str, Any],
    report: TableReport,
) -> Any:
    """mt_id 로 대응행을 찾아 넣거나 갱신한다. 지우지 않는다."""
    row = cache.get(mt_id)
    if row is None:
        row = model(mt_id=mt_id, **fields)
        db.add(row)
        cache[mt_id] = row
        report.added += 1
        return row
    changed = False
    for name, value in fields.items():
        if not _same(getattr(row, name), value):
            setattr(row, name, value)
            changed = True
    if changed:
        report.updated += 1
    else:
        report.unchanged += 1
    return row


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
        def_cache = _existing(db, CatalogDefinition)
        for row in con.execute("select * from property_definition"):
            _upsert(
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
                    "condition_axes": _json(row["condition_axes"]),
                    "source_created_at": _dt(row["created_at"]),
                },
                defs,
            )
        db.flush()

        sources = report.tables.setdefault("출처", TableReport())
        source_cache = _existing(db, CatalogSource)
        source_ids: dict[int, Any] = {}
        for row in con.execute("select * from source"):
            item = _upsert(
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
                    "source_retrieved_at": _dt(row["retrieved_at"]),
                    "source_created_at": _dt(row["created_at"]),
                },
                sources,
            )
            source_ids[row["id"]] = item
        db.flush()

        materials = report.tables.setdefault("재료", TableReport())
        material_cache = _existing(db, CatalogMaterial)
        material_ids: dict[int, Any] = {}
        for row in con.execute("select * from material"):
            attributes = _json(row["attributes"])
            facets = {key: (attributes or {}).get(key) or None for key in FACET_KEYS}
            item = _upsert(
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
                    "source_created_at": _dt(row["created_at"]),
                    "source_updated_at": _dt(row["updated_at"]),
                },
                materials,
            )
            material_ids[row["id"]] = item
        db.flush()

        values = report.tables.setdefault("값", TableReport())
        value_cache = _existing(db, CatalogValue)
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
            _upsert(
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
                    "conditions": _json(row["conditions"]),
                    "method": row["method"],
                    "quality_tier": row["quality_tier"],
                    "source_id": (
                        source_ids[row["source_id"]].id
                        if row["source_id"] is not None
                        else None
                    ),
                    "source_detail": row["source_detail"],
                    "notes": row["notes"],
                    "source_created_at": _dt(row["created_at"]),
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

    counts = {
        "property_definition": (CatalogDefinition, "정의"),
        "source": (CatalogSource, "출처"),
        "material": (CatalogMaterial, "재료"),
        "property_value": (CatalogValue, "값"),
    }
    for src_table, (model, label) in counts.items():
        src = con.execute(f"select count(*) from {src_table}").fetchone()[0]
        dst = db.scalar(select(func.count()).select_from(model))
        if src != dst:
            problems.append(f"{label} 행수 불일치 — 원본 {src} vs 이관 {dst}")

    # 출처 없는 값 — 원본이 0건을 유지해 온 불변식이다.
    src_null = con.execute(
        "select count(*) from property_value where source_id is null"
    ).fetchone()[0]
    dst_null = db.scalar(
        select(func.count()).select_from(CatalogValue).where(CatalogValue.source_id.is_(None))
    )
    if src_null != dst_null:
        problems.append(f"출처 없는 값 불일치 — 원본 {src_null} vs 이관 {dst_null}")

    # tier4 개수 — 「근거 없는 값」 표시가 이관에서 떨어졌는지.
    src_t4 = con.execute(
        "select count(*) from property_value where quality_tier = 4"
    ).fetchone()[0]
    dst_t4 = db.scalar(
        select(func.count()).select_from(CatalogValue).where(CatalogValue.quality_tier == 4)
    )
    if src_t4 != dst_t4:
        problems.append(f"tier4 개수 불일치 — 원본 {src_t4} vs 이관 {dst_t4}")

    return problems
