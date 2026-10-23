"""TestScope 에 묻기 — **보유 장비 · 교정의 정본은 TestScope 다**(ADR 0069).

MatNexus 는 장비를 복사해 두지 않고 그때 묻는다. 두 시스템은 물성 키(MaterialTwin 271 키)를
같이 쓰므로 대응표가 필요 없다.

    물성 키 → 우리 장비(측정법 · MCP)
        GET /properties → POST /search/test-items {property_term_id}
    글자 → 우리 장비(측정 의뢰)
        POST /resolve {term · test_item|property} → POST /search/test-items

## 「없음」 과 「모름」 을 가른다

TestScope 는 물성 ↔ 시험 항목 연결이 없는 물성에 결과를 0 으로 준다 — 그것을 「우리는 못
잰다」 로 옮기면 틀린다(TestScope 자신의 규칙). 그래서 답에 상태를 붙인다:

    off        연결 설정이 없다(「관리 > 외부 연동」)
    error      못 닿았거나 거절됐다
    unlinked   TestScope 에 그 물성을 내는 시험 항목 연결이 없다 — **모름**
    none       시험 항목은 이어졌는데 쓸 수 있는 보유 장비가 0 — **없음**
    found      장비가 있다

토큰 주인이 TestScope 에서 볼 수 있는 부서의 장비만 온다. 시험은 `TRANSPORT` 에
`httpx.MockTransport` 를 넣어 TestScope 없이 돈다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.integrations.models import IntegrationConnection
from app.shared import secretbox

SYSTEM = "testscope"
#: 시험이 모의 TestScope 를 끼우는 자리. 운영에서는 비어 있다.
TRANSPORT: httpx.BaseTransport | None = None
#: 화면이 기다리는 한계 — 넘으면 「못 닿음」 으로 답한다(측정법 화면이 멈추지 않게).
TIMEOUT_SECONDS = 8.0
#: 측정법 · MCP 에 싣는 장비 수 — 넘으면 「외 N대」 와 TestScope 링크.
EQUIPMENT_SHOWN = 30
#: 후보가 **하나**일 때 받는 근거 — 글자가 겹친 것. 「DMA」 → 「DMA (동적기계)」 가
#: `candidates` 로 온다(실측). 「뜻이 가까움」(의미 검색)은 하나여도 안 받는다 — 「고온
#: 탄성계수」 에 「초탄성 계수」 가 온다.
LITERAL_WHY = ("정확히 같음", "별칭", "이름에 포함")
#: 물성 키 → TestScope 물성 표를 들고 있는 시간. 연결은 사람이 고치므로 몇 분이면 된다.
PROPERTY_CACHE_SECONDS = 600.0


@dataclass(frozen=True)
class Connection:
    api: str
    token: str
    web: str
    """사람이 여는 화면 주소 — 장비 링크(`{web}/equipment/{id}`)에 쓴다."""


class Unreachable(Exception):
    """못 닿았거나 거절됐다 — 사람이 읽을 한 줄을 든다."""


def connection(db: Session) -> Connection | None:
    """설정이 덜 됐거나 이 서버가 토큰을 못 풀면 None(지어 쓰지 않는다)."""
    row = db.scalar(
        select(IntegrationConnection).where(IntegrationConnection.system == SYSTEM)
    )
    if row is None or not row.base_url:
        return None
    token = secretbox.unseal(row.token_sealed)
    if not token:
        return None
    web = row.web_url or row.base_url.removesuffix("/api")
    return Connection(row.base_url, token, web)


def client(api: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=api,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
        transport=TRANSPORT,
    )


def refused(response: httpx.Response) -> str:
    if response.status_code in (401, 403):
        return (
            f"TestScope 가 토큰을 거절했습니다(HTTP {response.status_code}) — 만료됐거나 지운 "
            "토큰입니다. TestScope 에서 읽기 토큰을 새로 발급해 넣으세요."
        )
    if response.status_code == 404:
        return (
            "그 주소에 TestScope API 가 없습니다(HTTP 404) — API 주소가 `…:8020/api` 꼴인지 "
            "확인하세요."
        )
    return f"TestScope 가 HTTP {response.status_code} 로 답했습니다."


def _call(conn: Connection, method: str, path: str, **kwargs: Any) -> Any:
    try:
        with client(conn.api, conn.token) as http:
            response = http.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise Unreachable(
            f"TestScope 에 닿지 못했습니다 — 주소 · 방화벽 · 서비스 확인({exc})."
        ) from exc
    if response.status_code != 200:
        raise Unreachable(refused(response))
    try:
        return response.json()
    except ValueError as exc:
        raise Unreachable("TestScope 가 아닌 곳이 답했습니다(JSON 이 아님).") from exc


# --- 물성 키 → TestScope 물성 -------------------------------------------------------


@dataclass(frozen=True)
class Property:
    term_id: str
    name: str
    test_items: tuple[str, ...]
    suggested: bool
    """이어진 시험 항목 가운데 사람이 확인하지 않은(기계 제안) 것이 있다."""


_properties: dict[str, tuple[float, dict[str, Property]]] = {}


def forget() -> None:
    """물성 표 캐시를 비운다 — 연결 설정을 바꿨거나 시험이 새로 시작할 때."""
    _properties.clear()


def properties(conn: Connection) -> dict[str, Property]:
    """물성 키 → 시험 항목이 이어진 TestScope 물성(한 번에 받아 잠깐 든다)."""
    cached = _properties.get(conn.api)
    if cached is not None and time.monotonic() - cached[0] < PROPERTY_CACHE_SECONDS:
        return cached[1]
    found = _call(conn, "GET", "/properties", params={"include_unlinked": "false"})
    table: dict[str, Property] = {}
    for one in found if isinstance(found, list) else []:
        code = str(one.get("code") or "")
        links = [link for link in one.get("links") or [] if isinstance(link, dict)]
        if not code or not links:
            continue
        table[code] = Property(
            term_id=str(one.get("id")),
            name=str(one.get("value") or code),
            test_items=tuple(sorted({str(link.get("test_item") or "") for link in links})),
            suggested=any(link.get("status") == "suggested" for link in links),
        )
    _properties[conn.api] = (time.monotonic(), table)
    return table


# --- 답 ------------------------------------------------------------------------------


class OwnedEquipmentOut(BaseModel):
    """보유 장비 한 대 — TestScope 가 준 그대로 + 그 장비 화면 링크."""

    equipment_id: str
    name: str
    asset_no: str
    status: str
    workspace: str | None
    site: str | None
    location: str | None
    contact: str | None
    test_item: str
    method_code: str | None
    calibration_due_on: str | None
    link: str


class OwnedOut(BaseModel):
    """「이것을 잴 우리 장비」 — 상태가 먼저다(`off · error · unlinked · none · found`)."""

    state: str
    message: str
    test_items: list[str] = []
    """TestScope 가 이 물성으로 펼친 시험 항목."""
    suggested: bool = False
    """그 연결 일부가 기계 제안(사람 미확인)이다."""
    equipment: list[OwnedEquipmentOut] = []
    """앞의 `EQUIPMENT_SHOWN` 대까지 — 나머지는 TestScope 에서 본다."""
    equipment_total: int = 0
    """찾은 장비 전체 대수. 실측(TestScope 개발 서버): 인장강도 하나에 109대."""
    catalog_series: int | None = None
    """보유는 0 인데 그 시험을 하는 카탈로그 계열 수 — 0 이 아니면 「사면 된다」."""
    link: str | None = None
    """TestScope 화면 — 사람이 더 볼 자리."""


def _equipment(conn: Connection, hits: list[dict[str, Any]]) -> list[OwnedEquipmentOut]:
    seen: dict[str, OwnedEquipmentOut] = {}
    for hit in hits:
        key = str(hit.get("equipment_id"))
        if key in seen:
            continue
        seen[key] = OwnedEquipmentOut(
            equipment_id=key,
            name=str(hit.get("equipment_name") or ""),
            asset_no=str(hit.get("asset_no") or ""),
            status=str(hit.get("status") or ""),
            workspace=hit.get("workspace_name"),
            site=hit.get("site"),
            location=hit.get("location"),
            contact=hit.get("contact_name"),
            test_item=str(hit.get("test_item") or ""),
            method_code=hit.get("method_code"),
            calibration_due_on=hit.get("calibration_due_on"),
            link=f"{conn.web}/equipment/{key}",
        )
    return list(seen.values())


def search(conn: Connection, query: dict[str, Any]) -> dict[str, Any]:
    found = _call(conn, "POST", "/search/test-items", json=query)
    return found if isinstance(found, dict) else {}


def owned(db: Session, property_key: str) -> OwnedOut:
    """물성 키 하나를 잴 우리 장비 — TestScope 에 그때 묻는다."""
    conn = connection(db)
    if conn is None:
        return OwnedOut(
            state="off",
            message="TestScope 연결이 없어 보유 장비를 모릅니다 — 시스템 관리자가 "
            "「관리 > 외부 연동」 에서 넣습니다.",
        )
    try:
        found = properties(conn).get(property_key)
        if found is None:
            return OwnedOut(
                state="unlinked",
                message="TestScope 에 이 물성을 내는 시험 항목 연결이 없어 보유 장비를 "
                "모릅니다 — 「없다」 가 아닙니다.",
                link=conn.web,
            )
        answer = search(conn, {"property_term_id": found.term_id})
    except Unreachable as exc:
        return OwnedOut(state="error", message=str(exc))
    equipment = _equipment(conn, list(answer.get("hits") or []))
    items = list(answer.get("expanded_test_items") or found.test_items)
    diagnosis = answer.get("diagnosis") or {}
    if not equipment:
        series = diagnosis.get("catalog_series_with_item")
        return OwnedOut(
            state="none",
            message="TestScope 에 이 물성을 잴 수 있는 가동 중 보유 장비가 없습니다"
            f"(시험 항목 {' · '.join(items) or '—'})."
            + (f" 장비 카탈로그에는 {series}개 계열이 있습니다." if series else ""),
            test_items=items,
            suggested=found.suggested,
            catalog_series=series if isinstance(series, int) else None,
            link=conn.web,
        )
    return OwnedOut(
        state="found",
        message=f"TestScope 보유 장비 {len(equipment)}대(시험 항목 {' · '.join(items)}).",
        test_items=items,
        suggested=found.suggested,
        equipment=equipment[:EQUIPMENT_SHOWN],
        equipment_total=len(equipment),
        link=conn.web,
    )


# --- 글자 → 우리 장비(측정 의뢰) ------------------------------------------------------


@dataclass
class Resolved:
    """글자 하나를 TestScope 에서 푼 결과 — 정해졌으면 `query`, 아니면 `reason`."""

    query: dict[str, Any] | None = None
    label: str | None = None
    reason: str | None = None
    candidates: list[str] = field(default_factory=list)


def resolve(conn: Connection, axis: str, text: str) -> Resolved:
    """`test_item` · `property` 축에서 하나로 정해지면 검색 질의를 만든다.

    여럿이면 고르지 않는다. 후보가 하나이고 글자 근거(`LITERAL_WHY`)면 받는다."""
    found = _call(conn, "POST", "/resolve", json={"kind": "term", "axis": axis, "text": text})
    match = found.get("match") if isinstance(found, dict) else None
    key = "test_item_term_id" if axis == "test_item" else "property_term_id"
    if match == "exact" and found.get("id"):
        return Resolved(query={key: found["id"]}, label=found.get("label"))
    listed = [one for one in (found or {}).get("candidates") or [] if isinstance(one, dict)]
    if len(listed) == 1 and listed[0].get("why") in LITERAL_WHY and listed[0].get("id"):
        return Resolved(query={key: listed[0]["id"]}, label=listed[0].get("label"))
    names = [str(one.get("label")) for one in listed]
    if match == "candidates" and len(listed) == 1:
        why = listed[0].get("why") or "근거 없음"
        return Resolved(reason=f"TestScope 후보가 확실하지 않음({why})", candidates=names)
    if match == "candidates":
        return Resolved(reason="TestScope 에서 여럿으로 풀림", candidates=names[:5])
    return Resolved(reason="TestScope 에 없음")


def equipment_of(conn: Connection, query: dict[str, Any]) -> list[OwnedEquipmentOut]:
    return _equipment(conn, list(search(conn, query).get("hits") or []))
