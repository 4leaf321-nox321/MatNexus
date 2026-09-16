"""별칭 후보 큐 — **못 푼 이름이 사전이 된다.**

빈손 검색이 후보로 남는다          같은 말은 횟수만 오른다
받아들이면 다음부터 찾힌다          별칭이 생기고 후보는 닫힌다 — 되돌릴 수 없어 시험이 문다
무시하면 목록에서 내려간다          지우지는 않는다
시스템 관리자만 판정한다            사전은 전사 자산이다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_workspaces import headers_for, make_active_user

from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import AliasCandidate, PropertyAlias

KEY = "mechanical.tensile_strength"


def _definition(db: Session) -> None:
    db.add(
        CatalogDefinition(
            mt_id=880_003,
            key=KEY,
            name="인장강도",
            domain="mechanical",
            si_unit="Pa",
            value_type="number",
        )
    )
    db.commit()


def _candidates(
    client: TestClient, headers: dict[str, str], **params: Any
) -> list[dict[str, Any]]:
    got = client.get(
        "/api/catalog/properties/alias-candidates", params=params, headers=headers
    )
    assert got.status_code == 200, got.text
    rows: list[dict[str, Any]] = got.json()
    return rows


def test_빈손_검색이_후보로_남고_같은_말은_횟수만_오른다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    _definition(db)
    for _ in range(2):
        got = client.get(
            "/api/catalog/properties/search",
            params={"q": "UTS", "unit": "MPa", "min": 100, "max": 900},
            headers=admin_headers,
        )
        assert got.status_code == 200 and got.json()["hits"] == []
        assert "별칭 후보" in got.json()["notes"][0]
    client.get("/api/catalog/properties/resolve", params={"q": "uts"}, headers=admin_headers)

    rows = _candidates(client, admin_headers)
    assert len(rows) == 1, rows
    (row,) = rows
    # 대소문자·공백이 달라도 한 말이다 — 처음 본 모양이 남는다.
    assert row["text"] == "UTS" and row["count"] == 3 and row["status"] == "open"
    # 오타 한 글자는 후보가 아니다.
    client.get("/api/catalog/properties/resolve", params={"q": "x"}, headers=admin_headers)
    assert len(_candidates(client, admin_headers)) == 1


def test_받아들이면_별칭이_생기고_다음부터_찾힌다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    _definition(db)
    client.get("/api/catalog/properties/resolve", params={"q": "UTS"}, headers=admin_headers)
    (row,) = _candidates(client, admin_headers)

    accepted = client.post(
        f"/api/catalog/properties/alias-candidates/{row['id']}/accept",
        json={"property_key": KEY},
        headers=admin_headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted" and accepted.json()["resolved_to"] == KEY

    alias = db.scalar(select(PropertyAlias).where(PropertyAlias.property_key == KEY))
    assert alias is not None and alias.alias == "UTS"
    # **다음부터 찾힌다** — 이것이 큐의 목적이다.
    found = client.get(
        "/api/catalog/properties/resolve", params={"q": "uts"}, headers=admin_headers
    ).json()
    assert [one["key"] for one in found["candidates"]] == [KEY]
    # 열린 목록에서는 사라지고, 전체에는 남는다.
    assert _candidates(client, admin_headers) == []
    assert len(_candidates(client, admin_headers, status="all")) == 1
    # 두 번 받아들여도 별칭이 둘이 되지 않는다.
    again = client.post(
        f"/api/catalog/properties/alias-candidates/{row['id']}/accept",
        json={"property_key": KEY},
        headers=admin_headers,
    )
    assert again.status_code == 200
    assert db.scalar(select(PropertyAlias).where(PropertyAlias.property_key == KEY)) is alias

    # 모르는 물성 키는 거절 — 별칭이 허공을 가리키면 안 된다.
    bad = client.post(
        f"/api/catalog/properties/alias-candidates/{row['id']}/accept",
        json={"property_key": "mechanical.nope"},
        headers=admin_headers,
    )
    assert bad.status_code == 404


def test_무시는_내리되_지우지_않는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    client.get(
        "/api/catalog/properties/resolve", params={"q": "asdfgh"}, headers=admin_headers
    )
    (row,) = _candidates(client, admin_headers)
    ignored = client.post(
        f"/api/catalog/properties/alias-candidates/{row['id']}/ignore", headers=admin_headers
    )
    assert ignored.status_code == 200 and ignored.json()["status"] == "ignored"
    assert _candidates(client, admin_headers) == []
    kept = db.scalar(select(AliasCandidate).where(AliasCandidate.text == "asdfgh"))
    assert kept is not None and kept.status == "ignored"


def test_시스템_관리자만_판정한다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    make_active_user(db, "member")
    headers = headers_for(client, "member")
    # 후보는 누구의 검색에서든 남는다.
    client.get("/api/catalog/properties/resolve", params={"q": "UTS"}, headers=headers)
    (row,) = _candidates(client, admin_headers)
    assert (
        client.get("/api/catalog/properties/alias-candidates", headers=headers).status_code
        == 403
    )
    refused = client.post(
        f"/api/catalog/properties/alias-candidates/{row['id']}/ignore", headers=headers
    )
    assert refused.status_code == 403


def test_홈_운영_경고에_해소_못_한_이름_수가_선다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    client.get("/api/catalog/properties/resolve", params={"q": "UTS"}, headers=admin_headers)
    got = client.get("/api/statistics/overview", headers=admin_headers)
    assert got.status_code == 200, got.text
    assert got.json()["ops"]["unresolved_names"] == 1
