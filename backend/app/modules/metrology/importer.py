"""materialtwin.db → 측정법 이관 — 카탈로그 이관과 같은 무늬.

무손실(모르는 컬럼 거부) · 멱등(`mt_id`) · 지우지 않음 · 파일이 유일한 문.
`scripts/import_materialtwin.py` 가 카탈로그 다음에 부른다 — 능력의
`property_key` 가 카탈로그 정의를, `source_id` 가 카탈로그 출처를 가리키므로
**카탈로그가 먼저 들어가 있어야 한다.**
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogSource
from app.modules.metrology.models import Instrument, InstrumentCapability
from app.shared.mt_import import (
    ImportRefused,
    Report,
    TableReport,
    check_schema,
    existing,
    parse_dt,
    upsert,
)

EXPECTED_COLUMNS: dict[str, frozenset[str]] = {
    "instrument": frozenset(
        {
            "id",
            "vendor",
            "model",
            "category",
            "technique",
            "description",
            "doc_path",
            "source_id",
            "notes",
            "created_at",
            "owned",
            "owned_note",
            "owner_name",
            "owner_contact",
            "owned_checked_at",
        }
    ),
    "instrument_capability": frozenset(
        {
            "id",
            "instrument_id",
            "property_key",
            "technique",
            "standard",
            "range_min",
            "range_max",
            "range_unit",
            "resolution",
            "accuracy",
            "temperature_min_k",
            "temperature_max_k",
            "specimen",
            "mapping_confidence",
            "source_detail",
            "notes",
            "created_at",
        }
    ),
}


def _text(raw: Any) -> str | None:
    """sqlite 의 동적 타입이 숫자로 돌려주는 문자 칸을 문자열로 고정한다.

    실측: `resolution` 이 `0.01`(float) 로 나와 String 컬럼의 `'0.01'` 과 매번
    어긋나 재실행 30건이 「갱신」 으로 읽혔다 — 값은 같은데 타입이 달랐다.
    정수값 float(`1.0`)은 `'1'` 로 적는다 — PG 가 float 를 varchar 로 받으면
    그렇게 적기 때문에, 안 맞추면 그 4건이 영원히 「갱신」 으로 남는다(실측).
    """
    if raw is None:
        return None
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw)


def run(db: Session, sqlite_path: str | Path) -> Report:
    """이관 본체. 커밋하지 않는다 — 드라이런/적용은 부르는 쪽이 정한다."""
    path = Path(sqlite_path)
    if not path.is_file():
        raise ImportRefused(f"파일이 없습니다: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        check_schema(con, EXPECTED_COLUMNS)
        report = Report()

        sources = {row.mt_id: row for row in db.scalars(select(CatalogSource))}
        known_keys = set(db.scalars(select(CatalogDefinition.key)))
        if not known_keys:
            raise ImportRefused(
                "카탈로그 정의가 비어 있습니다 — 카탈로그를 먼저 이관하세요 "
                "(능력의 property_key 가 정의를 가리킵니다)."
            )

        instruments = report.tables.setdefault("장비", TableReport())
        instrument_cache = existing(db, Instrument)
        instrument_ids: dict[int, Any] = {}
        for row in con.execute("select * from instrument"):
            source_mt = row["source_id"]
            if source_mt is not None and source_mt not in sources:
                raise ImportRefused(
                    f"장비 #{row['id']} 의 출처(mt {source_mt})가 카탈로그에 없습니다."
                )
            item = upsert(
                db,
                instrument_cache,
                Instrument,
                row["id"],
                {
                    "vendor": row["vendor"],
                    "model": row["model"],
                    "category": row["category"],
                    "technique": row["technique"],
                    "description": row["description"],
                    "doc_path": row["doc_path"],
                    "source_id": sources[source_mt].id if source_mt is not None else None,
                    "notes": row["notes"],
                    "owned": bool(row["owned"]),
                    "owned_note": row["owned_note"],
                    "owner_name": row["owner_name"],
                    "owner_contact": row["owner_contact"],
                    "owned_checked_at": parse_dt(row["owned_checked_at"]),
                    "source_created_at": parse_dt(row["created_at"]),
                },
                instruments,
            )
            instrument_ids[row["id"]] = item
        db.flush()

        capabilities = report.tables.setdefault("측정 능력", TableReport())
        capability_cache = existing(db, InstrumentCapability)
        for row in con.execute("select * from instrument_capability"):
            if row["property_key"] not in known_keys:
                raise ImportRefused(
                    f"측정 능력 #{row['id']} 의 물성 키 {row['property_key']!r} 가 "
                    f"카탈로그 정의에 없습니다."
                )
            upsert(
                db,
                capability_cache,
                InstrumentCapability,
                row["id"],
                {
                    "instrument_id": instrument_ids[row["instrument_id"]].id,
                    "property_key": row["property_key"],
                    "technique": row["technique"],
                    "standard": row["standard"],
                    "range_min": row["range_min"],
                    "range_max": row["range_max"],
                    "range_unit": row["range_unit"],
                    "resolution": _text(row["resolution"]),
                    "accuracy": _text(row["accuracy"]),
                    "temperature_min_k": row["temperature_min_k"],
                    "temperature_max_k": row["temperature_max_k"],
                    "specimen": row["specimen"],
                    "mapping_confidence": row["mapping_confidence"],
                    "source_detail": row["source_detail"],
                    "notes": row["notes"],
                    "source_created_at": parse_dt(row["created_at"]),
                },
                capabilities,
            )
        db.flush()

        # 검산 — 행수가 원본과 같아야 한다.
        for src_table, model, label in (
            ("instrument", Instrument, "장비"),
            ("instrument_capability", InstrumentCapability, "측정 능력"),
        ):
            src = con.execute(f"select count(*) from {src_table}").fetchone()[0]
            dst = db.scalar(select(func.count()).select_from(model))
            if src != dst:
                report.problems.append(f"{label} 행수 불일치 — 원본 {src} vs 이관 {dst}")
        return report
    finally:
        con.close()
