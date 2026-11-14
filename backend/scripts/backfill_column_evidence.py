"""이미 받아 온 밀도 · 푸아송비에 **문헌 근거**를 되살린다 — 운영 작업(2026-11-14, VOC 50).

문헌값을 채택하면 밀도 · 푸아송비는 숫자만 재료 칸에 써졌다. 이제 칸 옆에 근거(출처 · 근거 문서
· 문헌 등급)를 둔다(`materials/column_evidence`). 그 전에 받아 온 값을 찾아 **화면에서 받아 올
때와 같은 확인**(`declared_catalog.stamp` — 숫자를 대 본다)을 거쳐 근거를 붙인다.

## 무엇을 근거로 「받아 온 값」 이라 하나

둘이 다 맞아야 한다. 하나라도 어긋나면 건드리지 않고 그 이유를 센다.

    문헌 연결      그 재료가 문헌 재료에 이어져 있다(`catalog_links`)
    숫자          칸 값이 이어진 문헌 재료의 그 물성 값과 같다(유효숫자 9자리) — 여럿이 맞으면
                  가장 좋은 등급의 것

출처 · 근거 문서는 MCP `adopt_catalog_values` 와 같은 규칙으로 적는다(등급 4 는 추정). 이미
근거가 있는 칸은 건너뛰므로 몇 번 돌려도 같다. **사람이 친 값과 우연히 같은 수일 수 있다** —
그래서 세어 보기가 기본이고, 맞은 문헌 값 · 재료를 줄마다 보인다.

사용:
    python scripts/backfill_column_evidence.py            # 세어 보기만
    python scripts/backfill_column_evidence.py --apply    # 실제로 붙인다
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

# **모델을 전부 등록시킨다** — 손대는 모델만 import 하면 외래키가 가리키는 테이블을 못 푼다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.catalog.models import CatalogLink, CatalogSource, CatalogValue  # noqa: E402
from app.modules.materials.column_evidence import FIELDS  # noqa: E402
from app.modules.materials.models import Material  # noqa: E402
from app.shared import declared_catalog  # noqa: E402

survive_cp949()

#: 칸 → 문헌 키(`catalog/mapping.PROPERTY_ITEM_MAP` 의 column 자리).
KEYS = {"density": "physical.density", "poisson_ratio": "mechanical.poisson_ratio"}
#: 문헌 출처 종류 → 선언 출처(MCP `adopt_catalog_values` 와 같다).
KINDS = {"standard": "standard", "datasheet": "datasheet"}


def _origin(value: CatalogValue, source: CatalogSource | None) -> tuple[str, str]:
    kind = (
        "estimate" if value.quality_tier == 4 else KINDS.get(source.kind if source else "", "")
    )
    parts = [source.title, str(source.year or "") or None] if source else []
    reference = " · ".join(part for part in parts if part) or "문헌 카탈로그"
    return kind or "literature", f"{reference} [tier {value.quality_tier}]"


def plan(db: Session) -> tuple[list[tuple[Material, str, dict[str, Any], str]], Counter[str]]:
    """붙일 것 `(재료, 칸, 근거 줄, 맞은 문헌 재료 이름)` 과 못 붙인 이유별 수."""
    reasons: Counter[str] = Counter()
    out: list[tuple[Material, str, dict[str, Any], str]] = []
    links: dict[Any, list[Any]] = {}
    for link in db.scalars(select(CatalogLink)):
        links.setdefault(link.material_id, []).append(link.catalog_material_id)
    for material in db.scalars(select(Material).where(Material.deleted_at.is_(None))):
        for field, (column, item) in FIELDS.items():
            value = getattr(material, column)
            if value is None:
                continue
            if field in (material.column_evidence or {}):
                reasons["이미 근거가 있음"] += 1
                continue
            linked = links.get(material.id)
            if not linked:
                reasons["문헌 연결 없음"] += 1
                continue
            found = list(
                db.scalars(
                    select(CatalogValue).where(
                        CatalogValue.material_id.in_(linked),
                        CatalogValue.property_key == KEYS[field],
                        CatalogValue.value_num.is_not(None),
                    )
                )
            )
            row = {"item": item, "points": [{"value_si": float(value)}]}
            hits = [
                one
                for one in found
                if declared_catalog.match(row, declared_catalog.candidates(db, [one]))
            ]
            if not hits:
                reasons["숫자가 이어진 문헌 값과 다름"] += 1
                continue
            best = min(hits, key=lambda one: one.quality_tier or 9)
            source = db.get(CatalogSource, best.source_id) if best.source_id else None
            kind, reference = _origin(best, source)
            stamped = declared_catalog.stamp(
                db, {**row, "source": kind, "reference": reference}, [best.id]
            )
            out.append((material, field, stamped, str(best.material_id)))
    return out, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="실제로 붙인다(없으면 세어 보기만)"
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        found, reasons = plan(db)
        for material, field, row, catalog in found:
            tier = row[declared_catalog.KEY]["tier"]
            print(
                f"  {material.code} {material.record_name}: {field} → 등급 {tier} ({catalog})"
            )
        print(f"붙일 것 {len(found)}건")
        for reason, count in reasons.most_common():
            print(f"  건너뜀 — {reason}: {count}")
        if not args.apply:
            print("세어 보기만 했습니다 — 붙이려면 --apply")
            return 0
        for material, field, row, _catalog in found:
            material.column_evidence = {**(material.column_evidence or {}), field: row}
            flag_modified(material, "column_evidence")
        db.commit()
        print(f"붙였습니다 — {len(found)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
