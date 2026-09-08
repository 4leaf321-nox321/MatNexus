"""전체 검색 — **한 칸에 치면 무엇이든 찾는다.**

무는 것이 다섯이다.

    종류를 가로지른다           재료·시험·장비가 한 번에 나온다
    모드 셋이 다르게 문다        일치 / 포함 / 비슷(오타 허용)
    정확 일치가 언제나 위다      「비슷」 이 「그 말이 든 것」보다 위에 서면 안 된다
    **안 보이는 것은 결과에도 없다**  검색에 뜨는데 열면 404 면 사람은 고장으로 읽는다
    화면 없는 종류는 갈 곳을 준다  시료·시편은 품은 재료를 함께 준다
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentUnit, asset_key
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
SEARCH = "/api/search"

#: 부서를 잠그면 남에게 사라져야 하는 종류. 기준정보(`term`)는 여기 없다 —
#: 전 부서가 같은 낱말을 보는 것이 그 표의 목적이다(아래 시험이 그것을 적어 둔다).
GATED = {"material", "sample", "specimen", "test_run"}


def _login_member_of(
    client: TestClient, admin_headers: dict[str, str], *, slug: str, email: str
) -> dict[str, str]:
    made = client.post(
        "/api/accounts",
        json={"email": email, "display_name": email, "workspace_slug": slug, "role": "member"},
        headers=admin_headers,
    )
    assert made.status_code in (200, 201), made.text
    token = client.post(
        "/api/auth/login",
        json={"email": email, "password": made.json()["temporary_password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _chain(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    *,
    grade: str,
    owner_slug: str | None = None,
) -> dict[str, str]:
    """재료 → 시료 → 시편 → 시험. **화면과 같은 길로 만든다.**"""
    ensure_builtin_test_types(db)
    db.commit()
    body: dict[str, str] = {"family": "Metal", "category": "Steel", "grade": grade}
    if owner_slug:
        body["workspace_slug"] = owner_slug
    material = client.post("/api/materials", json=body, headers=admin_headers)
    assert material.status_code == 201, material.text
    material_id = material.json()["id"]

    sample = client.post(
        f"/api/materials/{material_id}/samples", json={}, headers=admin_headers
    )
    assert sample.status_code == 201, sample.text
    specimen = client.post(
        f"/api/samples/{sample.json()['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    )
    assert specimen.status_code == 201, specimen.text
    run = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen.json()["id"],
            "test_type": "tensile",
            "conditions": "{}",
        },
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    )
    assert run.status_code == 202, run.text
    return {
        "material": material_id,
        "sample": sample.json()["id"],
        "specimen": specimen.json()["id"],
        "test_run": run.json()["id"],
    }


def _kinds(body: dict[str, Any]) -> set[str]:
    return {str(one["kind"]) for one in body["groups"]}


def _hits(body: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    for one in body["groups"]:
        if one["kind"] == kind:
            return list(one["hits"])
    return []


class TestAcrossKinds:
    def test_한_번에_여러_종류를_찾는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """사람은 「SECC180」 이 재료인지 시험인지 모른 채 친다."""
        _chain(client, db, admin_headers, grade="SRCH180")
        db.add(
            EquipmentUnit(
                asset_no="SRCH-1",
                asset_key=asset_key("SRCH-1"),
                name="SRCH180 만능시험기",
                status="in_service",
                ownership="owned",
            )
        )
        db.commit()

        answer = client.get(SEARCH, params={"q": "SRCH180"}, headers=admin_headers)
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert {"material", "sample", "specimen", "test_run", "equipment_unit"} <= _kinds(body)

    def test_종류를_고르면_그것만_더_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _chain(client, db, admin_headers, grade="SRCHONE")
        answer = client.get(
            SEARCH, params={"q": "SRCHONE", "kind": ["material"]}, headers=admin_headers
        )
        assert answer.status_code == 200, answer.text
        assert _kinds(answer.json()) == {"material"}

    def test_모르는_종류는_되묻게_한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        answer = client.get(
            SEARCH, params={"q": "x", "kind": ["얼렁뚱땅"]}, headers=admin_headers
        )
        assert answer.status_code == 422
        assert answer.json()["error"]["code"] == "MNX-SEARCH-0002"


class TestModes:
    def test_일치는_그_이름만_문다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """번호·코드를 아는 사람이 쓰는 모드다 — 넓게 물면 쓸모가 없다."""
        made = _chain(client, db, admin_headers, grade="SRCHEXACT")
        material = client.get(f"/api/materials/{made['material']}", headers=admin_headers)
        full = material.json()["record_name"]

        loose = client.get(SEARCH, params={"q": "SRCHEXACT"}, headers=admin_headers)
        assert _hits(loose.json(), "material")

        exact = client.get(
            SEARCH, params={"q": "SRCHEXACT", "mode": "exact"}, headers=admin_headers
        )
        assert _hits(exact.json(), "material") == []

        whole = client.get(SEARCH, params={"q": full, "mode": "exact"}, headers=admin_headers)
        assert [one["name"] for one in _hits(whole.json(), "material")] == [full]

    def test_비슷은_오타를_넘어간다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """「SRCHFUZZ」 를 「SRCHFUZ」 로 쳐도 찾아야 한다 — 사람은 늘 한 글자를 흘린다."""
        _chain(client, db, admin_headers, grade="SRCHFUZZY")

        missed = client.get(SEARCH, params={"q": "SRCHFUZY"}, headers=admin_headers)
        assert _hits(missed.json(), "material") == []

        similar = client.get(
            SEARCH, params={"q": "SRCHFUZY", "mode": "similar"}, headers=admin_headers
        )
        found = _hits(similar.json(), "material")
        assert found, "오타를 넘어가지 못했다"
        assert found[0]["matched"] == "similar"

    def test_정확히_맞은_것이_비슷한_것보다_위다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """순위가 뒤집히면 「비슷」 모드는 못 쓰게 된다 — 늘 엉뚱한 게 1등이 된다."""
        _chain(client, db, admin_headers, grade="SRCHRANK")
        _chain(client, db, admin_headers, grade="SRCHRANKED2")

        answer = client.get(
            SEARCH,
            params={"q": "SRCHRANK", "mode": "similar", "kind": ["material"]},
            headers=admin_headers,
        )
        names = [one["name"] for one in _hits(answer.json(), "material")]
        assert names, answer.text
        assert names[0].startswith("SRCHRANK_"), f"1등이 {names[0]}"

    def test_모르는_방식은_되묻게_한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        answer = client.get(SEARCH, params={"q": "x", "mode": "마법"}, headers=admin_headers)
        assert answer.status_code == 422
        assert answer.json()["error"]["code"] == "MNX-SEARCH-0001"


class TestDestination:
    def test_화면_없는_종류는_품은_것을_함께_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """시료·시편은 제 화면이 없다 — 갈 곳이 없으면 「찾았는데 못 연다」 가 된다."""
        made = _chain(client, db, admin_headers, grade="SRCHDEST")
        body = client.get(SEARCH, params={"q": "SRCHDEST"}, headers=admin_headers).json()

        for kind in ("sample", "specimen"):
            hits = _hits(body, kind)
            assert hits, f"{kind} 를 못 찾았다"
            assert hits[0]["parent_kind"] == "material"
            assert hits[0]["parent_id"] == made["material"]


class TestVisibility:
    def test_안_보이는_것은_결과에도_없다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**이 파일에서 가장 값진 시험이다.**

        이름만 보여 주고 못 열게 하면 사람은 고장으로 읽고, 이름 자체가 이미
        유출이다(재료명에 과제명이 들어간다).
        """
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        _chain(client, db, admin_headers, grade="SRCHSECRET", owner_slug="dept-a")
        locked = client.patch(
            "/api/workspaces/dept-a", json={"restricted": True}, headers=admin_headers
        )
        assert locked.status_code == 200, locked.text

        outsider = _login_member_of(
            client, admin_headers, slug="dept-b", email=f"srch-{uuid.uuid4().hex[:6]}@x.com"
        )
        body = client.get(SEARCH, params={"q": "SRCHSECRET"}, headers=outsider).json()
        assert not (GATED & _kinds(body)), body

        # 주인에게는 그대로 보인다 — 가리는 쪽이 예외다.
        mine = client.get(SEARCH, params={"q": "SRCHSECRET"}, headers=admin_headers).json()
        assert _kinds(mine) >= GATED

    def test_기준정보_값은_전사_공용이라_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**경계를 시험이 적어 둔다.**

        재료를 만들면 등급이 기준정보에 자동 등록되고, 기준정보는 원래 전 부서가
        같은 것을 본다(그것이 어휘를 하나로 두는 목적이다). 그래서 부서를 잠가도
        그 **낱말**은 남는다 — 검색이 만든 구멍이 아니라 기준정보 화면에서 이미
        보이던 것이다.

        이 시험이 있는 이유는 나중에 「검색이 샌다」 로 읽히지 않게 하려는 것이다.
        낱말까지 가려야 한다면 그때 고칠 자리는 기준정보의 자동 등록이지 검색이
        아니다.
        """
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        _chain(client, db, admin_headers, grade="SRCHTERM", owner_slug="dept-a")
        client.patch(
            "/api/workspaces/dept-a", json={"restricted": True}, headers=admin_headers
        )

        outsider = _login_member_of(
            client, admin_headers, slug="dept-b", email=f"srch-{uuid.uuid4().hex[:6]}@x.com"
        )
        body = client.get(SEARCH, params={"q": "SRCHTERM"}, headers=outsider).json()
        assert _kinds(body) == {"term"}, body
