"""받는 부서 추천 — **이 의뢰의 항목을 할 보유 장비가 있는 부서**(TestScope, 2026-10-23).

측정 조직이 하나가 아니라 낸 사람이 받는 부서를 고르는데, 어느 부서에 그 장비가 있는지는
TestScope 가 안다. 의뢰 항목에는 물성 키가 없다 — 시험 종류(`tensile`)나 무엇을 재는지
(「고온 탄성계수」)뿐이라, 그 글자를 TestScope 의 이름 찾기(`/resolve`)로 시험 항목 · 물성으로
풀어 장비를 묻는다. **여럿으로 풀리면 고르지 않는다** — 그 항목은 추천에서 빠졌다고 말한다.

부서는 이름으로 잇는다. 부서 목록은 RA · TestScope · MatNexus 가 같은 열의 CSV 로 주고받아
이름이 같다(`workspaces/routes.py`). 같은 이름의 MatNexus 부서가 하나일 때만 고를 수 있게 준다.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.commissions.schemas import (
    LabSuggestionOut,
    LabSuggestionRequest,
    LabSuggestionsOut,
    LabUnresolvedOut,
)
from app.modules.tests.models import TestType
from app.modules.workspaces.models import Workspace
from app.shared import testscope

#: TestScope 장비에 부서가 안 적혔을 때의 이름.
NO_WORKSPACE = "(부서 미기재)"


def _norm(name: str) -> str:
    return "".join(name.split()).casefold()


def _tries(db: Session, key: str | None, hint: str | None) -> list[tuple[str, str]]:
    """TestScope 에 물어볼 (축, 글자) — 시험 종류가 먼저다(더 좁다)."""
    out: list[tuple[str, str]] = []
    if key:
        found = db.scalar(
            select(TestType).where(TestType.key == key).order_by(TestType.is_active.desc())
        )
        # 시험 종류 이름은 「인장시험」 인데 TestScope 시험 항목은 「인장」 이다 — 「시험」 을
        # 뗀 것도 묻는다. 「박리 · 이탈력」 처럼 둘을 묶은 이름은 통째로 물으면 의미 검색
        # 후보만 오므로(TestScope 개발 서버 실측) 나눠서도 묻는다.
        names: list[str] = []
        if found:
            bare = found.label.removesuffix("시험").strip()
            parts = re.split(r"\s*[·/,]\s*", bare)
            names = [found.label, bare, *(parts if len(parts) > 1 else []), found.abbr]
        for text in [*names, key]:
            if text and ("test_item", text) not in out:
                out.append(("test_item", text))
    if hint and hint.strip():
        out.append(("property", hint.strip()))
    return out


def suggest(db: Session, payload: LabSuggestionRequest) -> LabSuggestionsOut:
    conn = testscope.connection(db)
    if conn is None:
        return LabSuggestionsOut(
            state="off",
            message="TestScope 연결이 없어 장비가 있는 부서를 모릅니다(「관리 > 외부 연동」).",
        )
    by_name: dict[str, list[Workspace]] = {}
    for one in db.scalars(select(Workspace)):
        by_name.setdefault(_norm(one.name), []).append(one)

    labs: dict[str, LabSuggestionOut] = {}
    unresolved: list[LabUnresolvedOut] = []
    try:
        for index, item in enumerate(payload.items):
            tries = _tries(db, item.test_type_key, item.property_hint)
            if not tries:
                continue
            query = None
            last = None
            for axis, text in tries:
                last = testscope.resolve(conn, axis, text)
                if last.query is not None:
                    query = last.query
                    break
            if query is None:
                unresolved.append(
                    LabUnresolvedOut(
                        item=index,
                        text=tries[0][1],
                        reason=(last.reason if last else None) or "TestScope 에 없음",
                        candidates=last.candidates if last else [],
                    )
                )
                continue
            for unit in testscope.equipment_of(conn, query):
                name = unit.workspace or NO_WORKSPACE
                matched = by_name.get(_norm(name), [])
                lab = labs.setdefault(
                    name,
                    LabSuggestionOut(
                        workspace_slug=matched[0].slug if len(matched) == 1 else None,
                        workspace_name=name,
                        items=[],
                        equipment=[],
                    ),
                )
                if index not in lab.items:
                    lab.items.append(index)
                if all(one.equipment_id != unit.equipment_id for one in lab.equipment):
                    lab.equipment.append(unit)
    except testscope.Unreachable as exc:
        return LabSuggestionsOut(state="error", message=str(exc))

    ordered = sorted(
        labs.values(),
        key=lambda one: (-len(one.items), -len(one.equipment), one.workspace_name),
    )
    asked = sum(
        1 for item in payload.items if _tries(db, item.test_type_key, item.property_hint)
    )
    message = (
        f"항목 {asked}개 가운데 TestScope 에서 장비를 찾은 부서 {len(ordered)}곳."
        if ordered
        else "TestScope 에 이 항목들을 할 보유 장비가 있는 부서가 없거나, 항목을 시험 "
        "항목으로 풀지 못했습니다."
    )
    return LabSuggestionsOut(state="ok", message=message, labs=ordered, unresolved=unresolved)
