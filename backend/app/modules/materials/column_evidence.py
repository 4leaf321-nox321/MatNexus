"""재료 기본 칸(밀도 · 푸아송비)의 **근거** — 문헌에서 받아 온 값은 출처 · 근거 · 문헌
등급을 든다(2026-11-14, VOC 50 · 가안).

## 왜

문헌값을 채택하면 탄성계수는 선언 물성으로 들어가 출처 · 문헌 등급이 함께 간다. 밀도 ·
푸아송비는 재료의 기본 칸(숫자 하나)에만 써지고 출처가 버려졌다 — 카드는 그 값을 「재료에 적힌
공칭값(등급 3)」 으로 봤고, 문헌 등급 4(추정)의 값이 더 믿을 만한 3으로 올라가 보였다. 기본
칸을 읽는 화면 · 통계 · 검색이 27곳이라 값을 선언 물성으로 옮기지 않고(나안) 칸 옆에 근거만
둔다.

## 선언 물성과 같은 줄 모양

근거는 선언 물성 줄과 같은 모양(`item` · `points` · `source` · `reference` · 문헌 근거)으로
`Material.column_evidence[칸]` 에 둔다. 그래서 문헌 대조(`declared_catalog.stamp`)와 지문
(`declared_approval.digest`)을 그대로 쓴다 — 값이 어떤 길로 바뀌어도 지문이 갈려 문헌 등급은
저절로 풀린다(`shared/declared_card`).

## 사람이 값만 고치면 근거를 지운다

선언 물성과 같은 규칙이다. 같은 값을 되보내면(화면이 폼째 저장) 근거를 그대로 둔다 — 안 그러면
다른 칸을 고칠 때마다 근거가 사라진다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.materials import declared
from app.modules.materials.models import Material
from app.shared import declared_catalog
from app.shared.errors import AppError
from app.shared.text import clean

#: 요청의 칸 이름 → (재료 열, 근거 줄의 항목 이름).
FIELDS = {"density": ("density_si", "밀도"), "poisson_ratio": ("poisson_ratio", "푸아송비")}


def _same(before: float | None, after: float | None) -> bool:
    if before is None or after is None:
        return before is after
    return abs(before - after) <= 1e-12 * max(abs(before), abs(after), 1.0)


def apply(
    db: Session, material: Material, data: dict[str, Any], before: dict[str, float | None]
) -> None:
    """고친 칸의 근거를 맞춘다. `before` 는 고치기 전 값(`FIELDS` 의 열)."""
    evidence = dict(material.column_evidence or {})
    for field, (column, item) in FIELDS.items():
        value = getattr(material, column)
        source = data.get(f"{field}_source")
        if source is None:
            # 근거를 안 보냈다 — 값이 바뀌었으면 옛 근거는 그 값의 것이 아니다.
            if not _same(before.get(column), value):
                evidence.pop(field, None)
            continue
        if value is None:
            raise AppError(
                "MNX-MATERIALS-0070",
                f"{item} 값 없이 출처만 적을 수 없습니다 — 값을 함께 보내세요.",
                status=422,
            )
        if source not in declared.SOURCES:
            raise AppError(
                "MNX-MATERIALS-0070",
                f"{item} 의 출처는 {' · '.join(declared.SOURCES)} 중 하나입니다 — "
                f"받은 것: {source!r}",
                status=422,
            )
        reference = clean(str(data.get(f"{field}_reference") or ""))
        if reference is None:
            raise AppError(
                "MNX-MATERIALS-0070",
                f"{item} 의 근거 문서가 없습니다. 출처만으로는 어느 문헌 몇 판인지 알 수 "
                "없습니다.",
                status=422,
            )
        row: dict[str, Any] = {
            "item": item,
            "points": [{"value_si": float(value)}],
            "source": source,
            "reference": reference,
        }
        ids = data.get(f"{field}_catalog_value_ids")
        if ids:
            # 받아 왔다는 문헌 값과 **대 보고** 근거를 붙인다 — 안 맞으면 422(선언 물성과
            # 같다).
            row = declared_catalog.stamp(db, row, ids)
        evidence[field] = row
    material.column_evidence = evidence
