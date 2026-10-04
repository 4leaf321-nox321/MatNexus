"""물성 **정의문** — 이 물성 키가 무엇인가(ADR 0050, 2026-10-02).

정의문 칸(`catalog_definitions.description`)은 있었는데 271종 전부 비어 있었다 — 원본
(MaterialTwin)부터 비었다. 조회 도구는 이름 · 단위 · 기호만 돌려줬고, 그래서 「항복응력」 이
페이스트가 흐르기 시작하는 응력인지 금속의 항복강도인지를 이름으로만 가렸다.

## 정의문은 한 곳에 둔다

물성의 뜻은 **허브 키**(문헌 물성 정의)가 든다. 사내 물성 항목은 이어진 키(`same_as`)의
정의문을 함께 낸다 — 항목마다 따로 적으면 같은 물성의 뜻이 두 벌이 되고 갈린다.

## 씨앗은 사람이 안 고친 것만 따라간다

정의문은 `seeds/catalog/property-descriptions.json` 이 채운다. 배포마다 맞추되(`scripts/
refresh_builtins.py`), **자료 관리자가 고친 것은 안 덮는다** — 씨앗이 마지막으로 쓴 글의
지문(`description_seed_digest`)과 지금 글이 같을 때만 새 씨앗을 따른다(ADR 0046 · 0047 과 같은
규칙). 원본 이관은 빈 정의문으로 덮지 않는다(`importer.py`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition

SEED = Path(__file__).resolve().parents[3] / "seeds" / "catalog" / "property-descriptions.json"


def digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def load_seed(path: Path = SEED) -> dict[str, str]:
    """`{물성 키: 정의문}`. 파일이 없으면 빈 사전 — 정의문이 없다고 배포를 세우지 않는다."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(text).strip() for key, text in raw.get("descriptions", {}).items()}


def refresh_property_descriptions(
    db: Session, seed: dict[str, str] | None = None
) -> tuple[list[str], list[str]]:
    """씨앗의 정의문을 DB 에 맞춘다. `(채운 키, 사람이 고쳐 안 덮은 키)`.

    채우는 경우는 둘 — 정의문이 비었거나, 지금 글이 씨앗이 마지막으로 쓴 글 그대로다.
    사람이 씨앗과 똑같이 적었으면 지문만 남긴다(다음 씨앗을 따르게).
    """
    texts = load_seed() if seed is None else seed
    if not texts:
        return [], []
    filled: list[str] = []
    kept: list[str] = []
    for one in db.scalars(
        select(CatalogDefinition)
        .where(CatalogDefinition.key.in_(list(texts)))
        .order_by(CatalogDefinition.key)
    ):
        text = texts[one.key]
        # **원본에 정의문이 있으면 원본이 정본이다**(ADR 0050 결정 4) — 씨앗이 그것을 덮으면
        # 배포마다 이관(원본 글)과 씨앗(사내 글)이 번갈아 쓴다.
        if (one.source_description or "").strip():
            continue
        current = (one.description or "").strip()
        if current == text:
            if one.description_seed_digest != digest(text):
                one.description_seed_digest = digest(text)
            continue
        untouched = not current or one.description_seed_digest == digest(current)
        if untouched:
            one.description = text
            one.description_seed_digest = digest(text)
            filled.append(one.key)
        else:
            kept.append(one.key)
    db.flush()
    return filled, kept


__all__ = ["SEED", "digest", "load_seed", "refresh_property_descriptions"]
