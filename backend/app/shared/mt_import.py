"""MaterialTwin 이관의 공통 부품 — 카탈로그·측정법 이관기가 함께 쓴다.

모듈끼리 직접 부르지 않는다는 경계 규칙 때문에 여기(shared) 산다. 규율은
이관기들의 것과 같다:

    무손실     원본 표에 모르는 컬럼이 있으면(빠져 있어도) 거부한다
    멱등       원본 id(`mt_id`)로 대응행을 찾아 갱신하고, **지우지 않는다**
    수치 비교   PG JSONB 가 `1e+23` 을 정확한 정수로 정규화해 파이썬 float 와
              `==` 가 어긋난다 — 그 차이를 「갱신」 으로 읽으면 재실행마다 같은
              행을 다시 쓴다(실측: springer2020 Prony 의 tau_s)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


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
        return "\n".join(
            f"{name}: 추가 {t.added} · 갱신 {t.updated} · 동일 {t.unchanged}"
            for name, t in self.tables.items()
        )


def check_schema(con: sqlite3.Connection, expected_columns: dict[str, frozenset[str]]) -> None:
    """컬럼 전수 대조 — 모르는 컬럼도, 빠진 컬럼도 거부."""
    for table, expected in expected_columns.items():
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


def parse_dt(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    return datetime.fromisoformat(str(raw))


def parse_json(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


def same(a: Any, b: Any) -> bool:
    """숫자는 수치로 비교한다 — 모듈 머리말의 JSONB 정규화 함정 때문이다."""
    if (
        isinstance(a, (int, float))
        and isinstance(b, (int, float))
        and not isinstance(a, bool)
        and not isinstance(b, bool)
    ):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[key], b[key]) for key in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def existing(db: Session, model: Any) -> dict[int, Any]:
    """mt_id → 행 선적재 — 수만 건에 행마다 SELECT 를 치지 않는다.

    MatNexus 에서 직접 넣은 줄(`mt_id IS NULL`)은 원본에 없으므로 여기 안 든다.
    """
    return {
        row.mt_id: row for row in db.scalars(select(model).where(model.mt_id.is_not(None)))
    }


def upsert(
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
        if not same(getattr(row, name), value):
            setattr(row, name, value)
            changed = True
    if changed:
        report.updated += 1
    else:
        report.unchanged += 1
    return row
