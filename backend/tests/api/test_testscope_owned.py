"""TestScope 에 묻는 우리 장비 — **「없음」 과 「모름」 을 가른다**(2026-10-23, ADR 0069).

측정법(물성 키 → 장비)        off · error · unlinked(모름) · none(없음) · found
측정 의뢰(항목 → 받는 부서)    항목 글자를 TestScope 에서 풀고, 부서는 이름으로 잇는다
여럿으로 풀리면 고르지 않는다   그 항목은 추천에서 빠졌다고 말한다
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition
from app.modules.integrations.models import IntegrationConnection
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.workspaces.models import Workspace
from app.shared import secretbox, testscope

TOKEN = "tsp_test_read_only_0002"
TENSILE = "mechanical.tensile_strength"
YOUNG = "mechanical.youngs_modulus"
TG = "thermal.glass_transition_temperature"
DENSITY = "physical.density"

#: TestScope 장비 셋 — 재료시험팀의 UTM 둘, 분석팀의 DSC 하나.
UTM_1 = {
    "equipment_id": "e1",
    "equipment_name": "만능시험기 1호기",
    "asset_no": "A-1",
    "status": "active",
    "workspace_name": "재료 시험팀",
    "site": "2공장",
    "location": "3층",
    "contact_name": "홍측정",
    "test_item": "인장",
    "method_code": "ISO 6892-1",
    "calibration_due_on": "2027-03-31",
}
UTM_2 = {
    **UTM_1,
    "equipment_id": "e2",
    "equipment_name": "만능시험기 2호기",
    "asset_no": "A-2",
}
DSC = {
    **UTM_1,
    "equipment_id": "e3",
    "equipment_name": "DSC",
    "asset_no": "B-1",
    "workspace_name": "분석팀",
    "test_item": "DSC",
}

PEEL = {
    **UTM_1,
    "equipment_id": "e4",
    "equipment_name": "박리시험기",
    "asset_no": "C-1",
    "test_item": "박리",
}
#: 장비가 많은 물성 — 화면에는 앞의 30대만(실측: 인장강도 하나에 109대).
MANY = [
    {**UTM_1, "equipment_id": f"m{number}", "equipment_name": f"UTM {number}"}
    for number in range(35)
]


@pytest.fixture
def scope() -> Iterator[list[httpx.Request]]:
    """모의 TestScope — 인장강도는 인장으로, Tg 는 DSC 로 이어졌다.

    밀도는 이어졌는데 장비가 없다."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401)
        path = request.url.path
        if path == "/api/properties":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "p-ts",
                        "value": "인장강도",
                        "code": TENSILE,
                        "links": [{"test_item": "인장", "status": "confirmed"}],
                    },
                    {
                        "id": "p-tg",
                        "value": "유리전이온도",
                        "code": TG,
                        "links": [{"test_item": "DSC", "status": "suggested"}],
                    },
                    {
                        "id": "p-e",
                        "value": "영률",
                        "code": YOUNG,
                        "links": [{"test_item": "인장", "status": "confirmed"}],
                    },
                    {
                        "id": "p-rho",
                        "value": "밀도",
                        "code": DENSITY,
                        "links": [{"test_item": "비중", "status": "confirmed"}],
                    },
                ],
            )
        if path == "/api/search/test-items":
            asked = json.loads(request.content)
            found = {
                ("property_term_id", "p-ts"): ([UTM_1, UTM_2], ["인장"]),
                ("test_item_term_id", "ti-tensile"): ([UTM_1, UTM_2], ["인장"]),
                ("property_term_id", "p-tg"): ([DSC], ["DSC"]),
                ("property_term_id", "p-rho"): ([], ["비중"]),
                ("property_term_id", "p-e"): (MANY, ["인장"]),
                ("test_item_term_id", "ti-peel"): ([PEEL], ["박리"]),
            }
            key = next(iter(asked.items()))
            hits, items = found.get(key, ([], []))
            return httpx.Response(
                200,
                json={
                    "hits": hits,
                    "total": len(hits),
                    "expanded_test_items": items,
                    "diagnosis": {"catalog_series_with_item": 4},
                },
            )
        if path == "/api/resolve":
            asked = json.loads(request.content)
            table = {
                ("test_item", "인장"): {"match": "exact", "id": "ti-tensile", "label": "인장"},
                ("property", "유리전이온도"): {"match": "exact", "id": "p-tg", "label": "Tg"},
                ("property", "강도"): {
                    "match": "candidates",
                    "candidates": [{"label": "인장강도"}, {"label": "압축강도"}],
                },
                # 묶은 이름은 의미 검색 후보만 오고, 나눈 「박리」 는 정확히 풀린다(실측).
                ("test_item", "박리 · 이탈력"): {
                    "match": "candidates",
                    "candidates": [
                        {"id": "x1", "label": "마모", "why": "뜻이 가까움"},
                        {"id": "x2", "label": "경도", "why": "뜻이 가까움"},
                    ],
                },
                ("test_item", "박리"): {"match": "exact", "id": "ti-peel", "label": "박리"},
                # 후보가 하나 — 글자 근거면 받고, 뜻만 가까우면 안 받는다.
                ("property", "Tg"): {
                    "match": "candidates",
                    "candidates": [{"id": "p-tg", "label": "유리전이온도", "why": "별칭"}],
                },
                ("property", "고온 탄성계수"): {
                    "match": "candidates",
                    "candidates": [
                        {"id": "p-x", "label": "초탄성 계수", "why": "뜻이 가까움"}
                    ],
                },
            }
            return httpx.Response(
                200,
                json=table.get(
                    (asked["axis"], asked["text"]), {"match": "none", "candidates": []}
                ),
            )
        return httpx.Response(404)

    testscope.TRANSPORT = httpx.MockTransport(answer)
    testscope.forget()
    try:
        yield seen
    finally:
        testscope.TRANSPORT = None
        testscope.forget()


def _connect(db: Session) -> None:
    db.add(
        IntegrationConnection(
            system="testscope",
            base_url="http://testscope-host:8020/api",
            web_url="http://ts.example:8020",
            token_sealed=secretbox.seal(TOKEN),
        )
    )
    for key, name in (
        (TENSILE, "인장강도"),
        (YOUNG, "영률"),
        (TG, "유리전이온도"),
        (DENSITY, "밀도"),
    ):
        db.add(
            CatalogDefinition(
                key=key, name=name, domain=key.split(".")[0], value_type="numeric"
            )
        )
    db.commit()


def _owned(client: TestClient, headers: dict[str, str], key: str) -> Any:
    got = client.get(f"/api/metrology/by-property/{key}/owned", headers=headers)
    assert got.status_code == 200, got.text
    return got.json()


class Test측정법:
    def test_장비가_있으면_TestScope_화면_링크와_함께_준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        scope: list[httpx.Request],
    ) -> None:
        _connect(db)
        body = _owned(client, admin_headers, TENSILE)
        assert body["state"] == "found" and body["test_items"] == ["인장"]
        assert [one["name"] for one in body["equipment"]] == [
            "만능시험기 1호기",
            "만능시험기 2호기",
        ]
        assert body["equipment"][0]["link"] == "http://ts.example:8020/equipment/e1"
        assert body["equipment"][0]["calibration_due_on"] == "2027-03-31"
        # 물성 표는 한 번 받아 든다 — 두 번째 물음은 검색만 한다.
        _owned(client, admin_headers, TG)
        assert [one.url.path for one in scope].count("/api/properties") == 1

    def test_장비가_많으면_앞의_30대만_싣고_전체_대수를_준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        scope: list[httpx.Request],
    ) -> None:
        _connect(db)
        body = _owned(client, admin_headers, YOUNG)
        assert body["equipment_total"] == 35 and len(body["equipment"]) == 30
        assert "35대" in body["message"]

    def test_연결이_없으면_모름_장비가_0이면_없음(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        scope: list[httpx.Request],
    ) -> None:
        _connect(db)
        db.add(
            CatalogDefinition(
                key="mechanical.hardness_shore_a",
                name="쇼어 A",
                domain="mechanical",
                value_type="numeric",
            )
        )
        db.commit()
        unknown = _owned(client, admin_headers, "mechanical.hardness_shore_a")
        assert unknown["state"] == "unlinked" and "「없다」 가 아닙니다" in unknown["message"]
        nothing = _owned(client, admin_headers, DENSITY)
        assert nothing["state"] == "none" and nothing["equipment"] == []
        assert nothing["catalog_series"] == 4 and "카탈로그에는 4개 계열" in nothing["message"]
        assert _owned(client, admin_headers, TG)["suggested"] is True

    def test_설정이_없거나_거절되면_모른다고_말한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        scope: list[httpx.Request],
    ) -> None:
        db.add(
            CatalogDefinition(
                key=TENSILE, name="인장강도", domain="mechanical", value_type="numeric"
            )
        )
        db.commit()
        assert _owned(client, admin_headers, TENSILE)["state"] == "off"
        assert scope == []
        db.add(
            IntegrationConnection(
                system="testscope",
                base_url="http://testscope-host:8020/api",
                token_sealed=secretbox.seal("tsp_expired"),
            )
        )
        db.commit()
        refused = _owned(client, admin_headers, TENSILE)
        assert refused["state"] == "error" and "거절" in refused["message"]
        missing = client.get(
            "/api/metrology/by-property/no.such_key/owned", headers=admin_headers
        )
        assert missing.status_code == 404


class Test의뢰_받는_부서:
    def test_항목을_할_장비가_있는_부서를_항목이_많은_차례로(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        scope: list[httpx.Request],
    ) -> None:
        _connect(db)
        ensure_builtin_test_types(db)
        db.add(Workspace(slug="mat-lab", name="재료시험팀"))
        # 같은 이름(띄어쓰기만 다른)의 부서가 둘이면 고르지 않는다 — 엉뚱한 부서로 보내게 된다.
        db.add(Workspace(slug="ana-1", name="분석팀"))
        db.add(Workspace(slug="ana-2", name="분석 팀"))
        db.commit()
        got = client.post(
            "/api/commissions/lab-suggestions",
            json={
                "items": [
                    {"test_type_key": "tensile"},
                    {"property_hint": "유리전이온도"},
                    {"property_hint": "강도"},
                    {"property_hint": "없는 물성"},
                    {"test_type_key": "adhesion"},
                    {"property_hint": "Tg"},
                    {"property_hint": "고온 탄성계수"},
                ]
            },
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["state"] == "ok"
        assert [(one["workspace_name"], one["items"]) for one in body["labs"]] == [
            ("재료 시험팀", [0, 4]),
            ("분석팀", [1, 5]),
        ]
        # 이름은 띄어쓰기 · 대소문자를 보지 않고 잇는다. 하나로 안 정해지면 고를 수 없다.
        assert [one["workspace_slug"] for one in body["labs"]] == ["mat-lab", None]
        assert len(body["labs"][0]["equipment"]) == 3
        assert [(one["item"], one["reason"]) for one in body["unresolved"]] == [
            (2, "TestScope 에서 여럿으로 풀림"),
            (3, "TestScope 에 없음"),
            (6, "TestScope 후보가 확실하지 않음(뜻이 가까움)"),
        ]
        assert body["unresolved"][0]["candidates"] == ["인장강도", "압축강도"]

    def test_연결이_없으면_모른다고만(
        self, client: TestClient, admin_headers: dict[str, str], scope: list[httpx.Request]
    ) -> None:
        got = client.post(
            "/api/commissions/lab-suggestions",
            json={"items": [{"property_hint": "유리전이온도"}]},
            headers=admin_headers,
        ).json()
        assert got["state"] == "off" and got["labs"] == []
