"""시료 · 시편 · 시험 고유 번호(ADR 0043) — **이름은 바뀌어도 번호는 안 바뀐다.**

이름(`SECC_MDOI_1.0__01__MD_01__TEN_01`)은 밑줄로 엮여 길고, 다른 두께로 옮기면 바뀐다. 말 ·
문서 · 라벨이 가리킬 손잡이는 번호다. 무는 것:

    넷 다 번호를 받는다                 시료 S- · 시편 P- · 시험 T- (재료 M- 는 전부터)
    옮겨도 번호는 그대로다              번호가 따라 바뀌면 옛 라벨이 다른 것을 가리킨다
    목록 찾기는 어느 번호로든           손에 든 라벨이 시편 번호여도 시험 목록에서 찾힌다
    전체 검색은 번호로 곧장             번호를 아는 사람은 그것 하나를 원한다
    물성 카드도 번호를 받는다(C-)       같은 재료에 「인장 MD」 가 여러 장이다(2026-10-16)
    카드는 사슬 밖이다                  시험 목록에 카드 번호를 치면 아무것도 안 나온다
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from app.modules.workspaces.models import Workspace

SECC = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "CODE",
    "spec_thickness": 1.0,
    "spec_thickness_unit": "mm",
}


def _chain(
    client: TestClient, headers: dict[str, str], db: Session, workspace: Workspace
) -> dict[str, Any]:
    """재료 → 시료 → 시편 둘 → 첫 시편에 시험 하나."""
    material = client.post("/api/materials", json=SECC, headers=headers)
    assert material.status_code == 201, material.text
    sample = client.post(
        f"/api/materials/{material.json()['id']}/samples",
        json={"lot_no": "L1"},
        headers=headers,
    )
    assert sample.status_code == 201, sample.text
    specimens = []
    for _ in range(2):
        made = client.post(
            f"/api/samples/{sample.json()['id']}/specimens",
            json={"orientation": "MD"},
            headers=headers,
        )
        assert made.status_code == 201, made.text
        specimens.append(made.json())
    ensure_builtin_test_types(db)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    run = TestRun(
        workspace_id=workspace.id,
        specimen_id=uuid.UUID(specimens[0]["id"]),
        test_type_id=tensile.id,
        seq_no=1,
        record_name=f"{specimens[0]['record_name']}__TEN_01",
        status="parsed",
    )
    db.add(run)
    db.commit()
    got = client.get(f"/api/test-runs/{run.id}", headers=headers)
    assert got.status_code == 200, got.text
    return {
        "material": material.json(),
        "sample": sample.json(),
        "specimens": specimens,
        "run": got.json(),
    }


def _short(code: str) -> str:
    """사람이 치는 꼴 — `T-000203` → `t203`."""
    prefix, number = code.split("-")
    return f"{prefix.lower()}{int(number)}"


def test_시료_시편_시험이_번호를_받고_옮겨도_번호는_그대로다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    made = _chain(client, admin_headers, db, workspace)
    assert re.fullmatch(r"S-\d{6}", made["sample"]["code"])
    assert re.fullmatch(r"P-\d{6}", made["specimens"][0]["code"])
    assert re.fullmatch(r"T-\d{6}", made["run"]["code"])
    # 종류마다 따로 매긴다 — 같은 시료의 두 시편은 번호가 다르다.
    assert made["specimens"][0]["code"] != made["specimens"][1]["code"]

    # **다른 두께로 옮기면 이름은 바뀌고 번호는 그대로다.**
    done = client.post(
        "/api/specimens/relocate",
        json={
            "specimen_ids": [one["id"] for one in made["specimens"]],
            "spec_thickness": 1.2,
            "spec_thickness_unit": "mm",
        },
        headers=admin_headers,
    )
    assert done.status_code == 200, done.text
    specimen = client.get(
        f"/api/specimens/{made['specimens'][0]['id']}", headers=admin_headers
    ).json()
    assert specimen["record_name"].startswith("SECC_CODE_1.2")
    assert specimen["code"] == made["specimens"][0]["code"]
    run = client.get(f"/api/test-runs/{made['run']['id']}", headers=admin_headers).json()
    assert run["record_name"].startswith("SECC_CODE_1.2")
    assert run["code"] == made["run"]["code"]
    samples = client.get(
        f"/api/materials/{specimen['material_id']}/samples", headers=admin_headers
    ).json()
    assert [one["code"] for one in samples] == [made["sample"]["code"]]


def test_목록_찾기는_어느_번호로든_찾는다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    made = _chain(client, admin_headers, db, workspace)
    first, second = made["specimens"]
    run = made["run"]

    def specimens(q: str) -> set[str]:
        got = client.get("/api/specimens", params={"q": q}, headers=admin_headers)
        assert got.status_code == 200, got.text
        return {one["id"] for one in got.json()["items"]}

    def runs(q: str, **extra: str) -> set[str]:
        got = client.get("/api/test-runs", params={"q": q, **extra}, headers=admin_headers)
        assert got.status_code == 200, got.text
        return {one["id"] for one in got.json()["items"]}

    # 시편 목록 — 시편 번호는 그 시편, 시험 번호는 그 시험의 시편, 시료 번호는 그 아래 전부.
    assert specimens(_short(second["code"])) == {second["id"]}
    assert specimens(run["code"]) == {first["id"]}
    assert specimens(made["sample"]["code"]) == {first["id"], second["id"]}
    # 시험 목록 — 패딩 없이 친 시험 번호, 손에 든 시편 번호, 재료 번호.
    assert runs(_short(run["code"])) == {run["id"]}
    assert runs(first["code"]) == {run["id"]}
    assert runs(second["code"]) == set()  # 시험이 없는 시편
    assert runs(made["material"]["code"]) == {run["id"]}
    assert runs(run["code"], mode="exact") == {run["id"]}
    # 재료 목록 — 시험 번호로 그 재료.
    materials = client.get(
        "/api/materials", params={"q": _short(run["code"])}, headers=admin_headers
    ).json()["items"]
    assert [one["id"] for one in materials] == [made["material"]["id"]]


def test_전체_검색은_번호로_곧장_찾고_결과마다_번호를_싣는다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    made = _chain(client, admin_headers, db, workspace)
    run = made["run"]

    body = client.get(
        "/api/search", params={"q": _short(run["code"])}, headers=admin_headers
    ).json()
    [group] = [one for one in body["groups"] if one["kind"] == "test_run"]
    top = group["hits"][0]
    assert top["id"] == run["id"]
    assert (top["matched"], top["via"], top["code"]) == (
        "exact",
        f"번호 {run['code']}",
        run["code"],
    )

    # 이름으로 찾아도 번호가 실린다.
    body = client.get("/api/search", params={"q": "SECC_CODE"}, headers=admin_headers).json()
    material = next(one for one in body["groups"] if one["kind"] == "material")
    assert material["hits"][0]["code"] == made["material"]["code"]
    specimen = next(one for one in body["groups"] if one["kind"] == "specimen")
    assert {hit["code"] for hit in specimen["hits"]} == {
        one["code"] for one in made["specimens"]
    }


def test_물성_카드도_번호를_받고_어느_목록에서든_그_번호로_찾는다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    """같은 재료에 같은 이름의 카드가 여러 장이라 이름으로는 한 장을 못 가리킨다
    (2026-10-16)."""
    made = _chain(client, admin_headers, db, workspace)
    material_id = uuid.UUID(made["material"]["id"])
    twins = [PropertyCard(material_id=material_id, label="인장 MD") for _ in range(2)]
    db.add_all(twins)
    db.commit()
    first, second = (
        client.get(f"/api/fitting/cards/{one.id}", headers=admin_headers).json()
        for one in twins
    )
    assert re.fullmatch(r"C-\d{6}", first["code"])
    assert first["code"] != second["code"]

    def cards(q: str) -> set[str]:
        got = client.get("/api/fitting/cards", params={"q": q}, headers=admin_headers)
        assert got.status_code == 200, got.text
        return {one["id"] for one in got.json()["items"]}

    # 카드 목록 — 패딩 없이 친 카드 번호는 그 한 장, 재료 번호는 그 재료의 카드.
    assert cards(_short(second["code"])) == {second["id"]}
    assert cards(made["material"]["code"]) == {first["id"], second["id"]}
    # 재료 목록 — 카드 번호로 그 카드의 재료.
    materials = client.get(
        "/api/materials", params={"q": first["code"]}, headers=admin_headers
    ).json()["items"]
    assert [one["id"] for one in materials] == [made["material"]["id"]]
    # **카드는 사슬 밖이다** — 시험 목록이 그 재료의 시험을 전부 내면 「근거 시험」 으로
    # 읽힌다.
    runs = client.get(
        "/api/test-runs", params={"q": first["code"]}, headers=admin_headers
    ).json()["items"]
    assert runs == []

    # 전체 검색은 번호로 곧장.
    body = client.get(
        "/api/search", params={"q": _short(first["code"])}, headers=admin_headers
    ).json()
    [group] = [one for one in body["groups"] if one["kind"] == "property_card"]
    top = group["hits"][0]
    assert (top["id"], top["code"], top["via"]) == (
        first["id"],
        first["code"],
        f"번호 {first['code']}",
    )


def test_휴지통에_든_재료의_카드는_번호로도_안_뜬다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    """**시스템 관리자에게도.** 카드에는 지움 칸이 없어 재료의 휴지통을 따른다 — 검색에 뜨고
    열면 「재료를 찾을 수 없습니다」 였다(2026-10-16 AI 평가)."""
    made = _chain(client, admin_headers, db, workspace)
    material_id = uuid.UUID(made["material"]["id"])
    card = PropertyCard(material_id=material_id, label="휴지통 카드")
    db.add(card)
    db.commit()
    db.refresh(card)

    def found() -> list[str]:
        body = client.get("/api/search", params={"q": card.code}, headers=admin_headers).json()
        return [
            hit["id"]
            for group in body["groups"]
            if group["kind"] == "property_card"
            for hit in group["hits"]
        ]

    assert found() == [str(card.id)]
    material = db.get(Material, material_id)
    assert material is not None
    material.deleted_at = datetime.now(UTC)
    db.commit()
    assert found() == []
