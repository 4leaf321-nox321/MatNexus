"""선언 값의 **문헌 근거** — 받아 온 문헌 값은 그 값의 등급을 잇는다 (2026-10-03).

## 왜

선언 물성의 등급은 출처로 정해졌다 — 제품 시트 1 · 규격 2 · 문헌 3 · 추정 4
(`shared/tiers`). 문헌이 3 인 까닭은 「어느 문헌인지 · 그 문헌의 등급을 모른다」
였다. 그런데 **문헌 카탈로그에서 받아 온 값은 안다** — 카탈로그가 값마다 1~4 를
든다. 논문에서 잰 1등급 값을 받아 오면 3등급(「옮겨 적음」)이 됐다(2026-10-03
사용자 보고). 근거가 있는데 버린 것이다.

## 등급은 서버가 그 값에서 읽는다

받는 쪽(화면 · MCP)은 **어느 문헌 값에서 왔는지(id)만** 준다. 서버가 그 값들을
꺼내 줄의 숫자와 대 보고 — 값 그대로이거나, 조건이 같은 중복을 묶은 중앙값이거나
— 점이 전부 맞을 때만 근거를 붙인다. 안 대 보면 id 하나 붙여 아무 숫자에나
1등급을 달 수 있다(「사람이 매기지 않는다」). 한 줄이 여러 값(온도별 · 주파수별)
이면 **가장 낮은 등급**이 줄의 등급이다.

## 값에 묶인다 — 승인과 같은 규칙(ADR 0049)

근거에는 그때 값의 지문(`declared_approval.digest`)을 남긴다. 값 · 단위 · 조건 ·
출처 · 근거 문서 중 하나라도 바뀌면 근거는 없는 것이 되고 등급은 출처로 돌아간다
(문헌 3). 통째 교체(PATCH)로 같은 줄을 되보내면 **저장돼 있던 근거를 이어받는다**
(`carry`) — 받는 쪽이 근거를 실어 나르게 하면 다른 항목을 고칠 때마다 등급이
사라진다. 받은 줄에 근거 칸이 있어도 버린다 — 근거는 id 를 준 줄만 여기서 짓는다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogValue
from app.shared import declared_approval, representative
from app.shared.errors import AppError
from app.shared.text import compare_key

KEY = declared_approval.CATALOG_KEY

#: 한 줄이 받아 왔다고 댈 수 있는 문헌 값의 상한 — 온도 · 주파수 점이 이만큼이면 충분하다.
MAX_VALUES = 200


def _key(value: float) -> float:
    """지문과 같은 자릿수(유효숫자 9)로 견준다 — 화면이 값을 12자리로 되돌려 보내도 같다."""
    return float(f"{float(value):.{declared_approval.DIGITS}g}")


def candidates(db: Session, values: list[CatalogValue]) -> list[tuple[float, int, uuid.UUID]]:
    """받아 온 값이 될 수 있는 숫자 — (숫자, 등급, 값 id).

    값 그대로가 기본이고, **조건이 같은 중복을 묶은 중앙값**도 든다 — 문헌 상세에서 그런 값이
    여럿이면 화면은 대표값 자리에서 그 중앙값을 받아 온다(`representative._summary`). 중앙값의
    등급은 묶인 값들 가운데 **가장 낮은 것**이다 — 3등급이 섞인 중앙값을 1등급이라 할 수 없다.
    """
    out = [
        (float(one.value_num), int(one.quality_tier), one.id)
        for one in values
        if one.value_num is not None
    ]
    for material_id, property_key in {(one.material_id, one.property_key) for one in values}:
        members = list(
            db.scalars(
                select(CatalogValue).where(
                    CatalogValue.material_id == material_id,
                    CatalogValue.property_key == property_key,
                )
            )
        )
        marks = representative.annotate(members)
        numbered = [one for one in members if one.value_num is not None]
        for one in values:
            mark = marks.get(one.id)
            if one.material_id != material_id or mark is None or not mark.summary:
                continue
            # 중앙값을 낸 그 무리만 — 변수 값은 스칼라와 따로 묶인다(`representative.group`).
            pooled = [
                member
                for member in numbered
                if representative.group(member) == representative.group(one)
            ]
            worst = max(int(member.quality_tier) for member in pooled)
            out.append((float(mark.summary["median"]), worst, one.id))
    return out


def match(
    row: dict[str, Any], found: list[tuple[float, int, uuid.UUID]]
) -> tuple[int, list[str]] | None:
    """줄의 점이 **전부** 후보에 맞으면 (줄의 등급, 맞은 값 id) — 하나라도 안 맞으면 None.

    점마다 맞은 후보 가운데 가장 좋은 등급을 그 점의 근거로 삼고, 줄의 등급은 점들 가운데 가장
    낮은 것이다.
    """
    worst = 0
    used: set[str] = set()
    points = [point for point in row.get("points") or [] if isinstance(point, dict)]
    if not points:
        return None
    for point in points:
        value = point.get("value_si")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        hits = [one for one in found if _key(one[0]) == _key(value)]
        if not hits:
            return None
        best = min(hits, key=lambda one: one[1])
        worst = max(worst, best[1])
        used.add(str(best[2]))
    return worst, sorted(used)


def evidence(row: dict[str, Any], tier: int, value_ids: list[str]) -> dict[str, Any]:
    """근거를 붙인 새 줄 — 그때 값의 지문과 함께."""
    return {
        **row,
        KEY: {"value_ids": value_ids, "tier": tier, "digest": declared_approval.digest(row)},
    }


def stamp(
    db: Session, row: dict[str, Any], value_ids: Iterable[uuid.UUID | str]
) -> dict[str, Any]:
    """받아 왔다는 문헌 값들과 **대 보고** 근거를 붙인 줄. 안 맞으면 거절한다(422).

    조용히 출처 등급으로 떨어뜨리지 않는다 — 받는 쪽은 받아 온 줄 알고 있는데 등급이 3 으로
    남으면 그 차이를 아무도 모른다. 문헌 값을 고쳐 적은 것이면 받아 온 값이 아니므로 id 없이
    보내면 된다(그때 등급은 출처로 정해진다).
    """
    name = str(row.get("item") or "")
    try:
        wanted = {uuid.UUID(str(one)) for one in value_ids}
    except ValueError as caught:
        raise AppError(
            "MNX-MATERIALS-0047",
            f"'{name}' 을 받아 왔다는 문헌 값 id 가 형식에 맞지 않습니다.",
            status=422,
        ) from caught
    if len(wanted) > MAX_VALUES:
        raise AppError(
            "MNX-MATERIALS-0047",
            f"'{name}' 을 받아 왔다는 문헌 값이 {len(wanted)}개입니다 — "
            f"{MAX_VALUES}개까지입니다.",
            status=422,
        )
    values = list(db.scalars(select(CatalogValue).where(CatalogValue.id.in_(wanted))))
    if len(values) != len(wanted):
        raise AppError(
            "MNX-MATERIALS-0047",
            f"'{name}' 을 받아 왔다는 문헌 값 가운데 카탈로그에 없는 것이 있습니다 — "
            "지워졌거나 다시 이관됐을 수 있습니다. 문헌 상세에서 다시 받아 오세요.",
            status=422,
        )
    found = match(row, candidates(db, values))
    if found is None:
        raise AppError(
            "MNX-MATERIALS-0048",
            f"'{name}' 의 값이 받아 왔다는 문헌 값과 다릅니다. 문헌 값을 고쳐 적었다면 "
            "받아 온 값이 아니니 받아 온 표시(catalog_value_ids) 없이 보내세요 — 그때 "
            "등급은 출처로 정해집니다.",
            status=422,
        )
    tier, used = found
    return evidence(row, tier, used)


def carry(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """저장돼 있던 근거를 **값이 그대로인 줄에만** 옮긴다. 이번에 지은 근거가 이긴다."""
    stored = {
        compare_key(str(row.get("item") or "")): row[KEY]
        for row in before
        if isinstance(row, dict) and declared_approval.catalog_tier(row) is not None
    }
    out: list[dict[str, Any]] = []
    for given in after:
        if declared_approval.catalog_tier(given) is not None:
            out.append(given)  # 이번 요청에서 `stamp` 가 지은 것
            continue
        row = {key: value for key, value in given.items() if key != KEY}
        previous = stored.get(compare_key(str(row.get("item") or "")))
        if previous is not None and previous.get("digest") == declared_approval.digest(row):
            row[KEY] = previous
        out.append(row)
    return out
