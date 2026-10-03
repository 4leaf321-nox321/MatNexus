"""이미 받아 온 문헌 값에 **그 문헌 값의 등급**을 되살린다 — 배포마다 도는 보정(2026-10-03).

문헌 카탈로그에서 받아 온 선언 값은 이제 그 문헌 값의 등급을 잇는다(`shared/declared_catalog`).
그 전에 받아 온 줄은 근거 없이 출처로만 등급이 매겨졌다 — 논문에서 잰 1등급 값이 3 이다. 그
줄들을 찾아 **화면에서 받아 올 때와 같은 확인**을 거쳐 근거를 붙인다.

## 무엇을 근거로 「받아 온 줄」 이라 하나

셋이 다 맞아야 한다. 하나라도 어긋나면 건드리지 않고 그 이유를 센다.

    받아 오기가 남긴 비고     「문헌 물성 카탈로그에서 채택」 — 화면 · MCP 가 같은 말을 적는다
    근거 문서의 출처 제목     줄의 근거 문서에 그 문헌 값의 출처 제목(또는 발행처)이 들어 있다
    숫자                     줄의 점이 전부 그 출처의 값(또는 묶은 중앙값)과 같다 — 지문과
                             같은 유효숫자 9자리, 물성도 사내 항목에 이어진 키여야 한다

등급은 거기서 읽는다 — 여러 값이면 가장 낮은 것(`declared_catalog.match`). 이미 근거가
있는 줄은 건너뛰므로 몇 번 돌려도 같다.

사용:
    python scripts/backfill_declared_catalog.py            # 세어 보기만
    python scripts/backfill_declared_catalog.py --apply    # 실제로 붙인다
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

# **모델을 전부 등록시킨다.** 스크립트가 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다 — 앱에서는 안 드러나고 배포용 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.catalog.models import CatalogSource, CatalogValue  # noqa: E402
from app.modules.catalog.ontology_models import PropertyLink  # noqa: E402
from app.modules.materials.models import Material, Sample  # noqa: E402
from app.modules.vocabulary.models import VocabularyTerm  # noqa: E402
from app.shared import declared_approval, declared_catalog  # noqa: E402
from app.shared.text import compare_key  # noqa: E402

survive_cp949()

#: 받아 오기(화면 `AdoptDialog` · MCP `adopt_catalog_values`)가 줄의 비고에 적는 말의 앞머리.
ADOPTED_NOTE = "문헌 물성 카탈로그에서 채택"


def linked_keys(db: Session) -> dict[str, set[str]]:
    """사내 항목(비교키) → 그 항목에 `same_as` 로 이어진 문헌 키들(눈금별로 여럿일 수 있다)."""
    out: dict[str, set[str]] = {}
    for key, item in db.execute(
        select(PropertyLink.property_key, VocabularyTerm.value)
        .join(VocabularyTerm, VocabularyTerm.id == PropertyLink.term_id)
        .where(PropertyLink.kind == "same_as")
    ).all():
        out.setdefault(compare_key(str(item)), set()).add(str(key))
    return out


def evidence_for(
    db: Session, row: dict[str, Any], keys: set[str]
) -> tuple[dict[str, Any] | None, str]:
    """근거를 붙인 줄과 「무엇을 했나」. 못 붙이면 (None, 이유)."""
    if not str(row.get("note") or "").startswith(ADOPTED_NOTE):
        return None, "받아 온 줄이 아님"
    if not keys:
        return None, "사내 항목에 이어진 문헌 키가 없음"
    reference = str(row.get("reference") or "")
    named = [
        source.id
        for source in db.scalars(select(CatalogSource))
        if any(
            name and len(name) >= 4 and name in reference
            for name in (source.title, source.publisher)
        )
    ]
    if not named:
        return None, "근거 문서에서 출처 제목을 못 찾음"
    values = list(
        db.scalars(
            select(CatalogValue).where(
                CatalogValue.property_key.in_(keys),
                CatalogValue.source_id.in_(named),
                CatalogValue.value_num.is_not(None),
            )
        )
    )
    found = (
        declared_catalog.match(row, declared_catalog.candidates(db, values))
        if values
        else None
    )
    if found is None:
        return None, "숫자가 그 출처의 값과 다름"
    tier, used = found
    return declared_catalog.evidence(row, tier, used), f"등급 {tier}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="실제로 붙인다 (없으면 세어 보기만)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        keys = linked_keys(db)
        fixed = 0
        reasons: dict[str, int] = {}
        for owner in [*db.scalars(select(Material)), *db.scalars(select(Sample))]:
            rows = list(owner.declared_properties or [])
            changed = False
            for index, row in enumerate(rows):
                if (
                    not isinstance(row, dict)
                    or declared_approval.catalog_tier(row) is not None
                ):
                    continue
                item = str(row.get("item") or "")
                made, said = evidence_for(db, row, keys.get(compare_key(item), set()))
                if made is None:
                    if said != "받아 온 줄이 아님":
                        reasons[said] = reasons.get(said, 0) + 1
                    continue
                before = declared_approval.tier(row)
                after = declared_approval.tier(made)
                print(f"  {owner.record_name} · {item}: 등급 {before} → {after}")
                rows[index] = made
                changed = True
                fixed += 1
            if changed and args.apply:
                owner.declared_properties = rows
                flag_modified(owner, "declared_properties")
        print(
            f"받아 온 문헌 등급을 되살린 줄 {fixed}개"
            + ("" if args.apply else " (세어 보기만)")
        )
        for said, count in sorted(reasons.items(), key=lambda one: -one[1]):
            print(f"  건너뜀 — {said}: {count}개")
        if args.apply:
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
