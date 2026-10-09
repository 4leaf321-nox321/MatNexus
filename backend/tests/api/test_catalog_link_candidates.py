"""사내 재료 ↔ 문헌 재료 **연결 후보** — 눌러도 되는 것만 오른다(`catalog/material_links`).

무는 것:

    같은 것만        코드 · 이름 전체 · 이름의 앞 낱말이 같을 때만. 닮은 것(SGARC340 ↔ 440),
                     낱말 가운데(LEXAN … (PC-GF20)), 블렌드(PC/ABS), 꼬리 붙은 등급(SUS304L)은
                     안 오른다
    분류가 맞는 것   금속 재료에 고분자 문헌 재료를 올리지 않는다
    사라진 것은 뺀다  원본에서 사라진 문헌 재료
    목록             안 이어진 재료만 · 고칠 권한 · 상한이 잘라도 개수는 다 센다
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue

KEY = "mechanical.youngs_modulus"


def _catalog(
    db: Session,
    name: str,
    category: str,
    *,
    values: int = 0,
    code: str | None = None,
    role: str | None = "product",
    missing: bool = False,
) -> CatalogMaterial:
    if db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == KEY)) is None:
        db.add(
            CatalogDefinition(
                key=KEY,
                domain="mechanical",
                name="Young's modulus",
                value_type="numeric",
                si_unit="Pa",
            )
        )
        db.flush()
    one = CatalogMaterial(
        name=name,
        category=category,
        material_code=code,
        role=role,
        source_missing_at=datetime.now(UTC) if missing else None,
    )
    db.add(one)
    db.flush()
    for _ in range(values):
        db.add(
            CatalogValue(
                material_id=one.id, property_key=KEY, value_num=1e9, unit="Pa", quality_tier=2
            )
        )
    db.commit()
    return one


def _material(
    client: TestClient,
    headers: dict[str, str],
    family: str,
    category: str,
    grade: str,
    alias: str | None = None,
) -> str:
    made = client.post(
        "/api/materials",
        json={"family": family, "category": category, "grade": grade, "alias": alias},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _names(client: TestClient, headers: dict[str, str], material_id: str) -> list[Any]:
    got = client.get(f"/api/catalog/links/{material_id}/candidates", headers=headers)
    assert got.status_code == 200, got.text
    return [(one["name"], one["matched_by"], one["matched_on"]) for one in got.json()]


def test_같은_것만_후보로_오른다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    _catalog(db, "SUS304_annealed Bilinear", "metal", values=3)
    _catalog(db, "SUS304 adhesion substrate (Park 2020)", "metal", values=5, role="evidence")
    _catalog(db, "SUS304L Bilinear", "metal", values=9)  # 꼬리 붙은 다른 등급
    _catalog(db, "SUS304 coated film", "polymer", values=9)  # 분류가 다르다
    _catalog(db, "SUS304 old sheet", "metal", values=9, missing=True)  # 원본에서 사라짐
    _catalog(db, "SGARC440 Bilinear", "metal", values=9)  # 닮았을 뿐
    _catalog(db, "PC (Covestro Makrolon 2405)", "polymer", values=2)
    _catalog(db, "PC/ABS Blend (housing)", "polymer", values=9)  # 블렌드
    _catalog(db, "LEXAN 3412R (PC-GF20, SABIC)", "polymer", values=9)  # 낱말 가운데
    _catalog(db, "SAC305 Solder Alloy", "metal", values=4, code="PKG-SAC")

    sus = _material(client, admin_headers, "Metal", "Steel", "SUS304")
    # 근거가 같으면 실제 제품이 근거용보다 먼저다(값이 더 적어도).
    assert _names(client, admin_headers, sus) == [
        ("SUS304_annealed Bilinear", "prefix", "grade"),
        ("SUS304 adhesion substrate (Park 2020)", "prefix", "grade"),
    ]
    assert (
        _names(
            client,
            admin_headers,
            _material(client, admin_headers, "Metal", "Steel", "SGARC340"),
        )
        == []
    )

    pc = _material(client, admin_headers, "Polymer", "PC", "PC")
    assert _names(client, admin_headers, pc) == [
        ("PC (Covestro Makrolon 2405)", "prefix", "grade")
    ]
    # 블렌드는 블렌드로 물으면 오른다 — 기호를 무시하고 견준다.
    blend = _material(client, admin_headers, "Polymer", "PC", "PC-ABS")
    assert _names(client, admin_headers, blend) == [
        ("PC/ABS Blend (housing)", "prefix", "grade")
    ]

    # 등급이 내부 번호여도 별칭이 문헌 이름과 같으면 오르고, 코드가 같으면 그것이 먼저다.
    by_alias = _material(
        client, admin_headers, "Metal", "Solder", "E2EMT0001", alias="SAC305 Solder Alloy"
    )
    assert _names(client, admin_headers, by_alias) == [
        ("SAC305 Solder Alloy", "name", "alias")
    ]
    by_code = _material(client, admin_headers, "Metal", "Solder", "pkg_sac")
    assert _names(client, admin_headers, by_code) == [("SAC305 Solder Alloy", "code", "grade")]


def test_이어진_문헌_재료는_후보에서_빠진다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    first = _catalog(db, "Al6063-T6 Bilinear", "metal", values=3)
    _catalog(db, "Al6063-T5 Bilinear", "metal", values=2)
    material = _material(client, admin_headers, "Metal", "Aluminum", "AL6063")
    assert [one[0] for one in _names(client, admin_headers, material)] == [
        "Al6063-T6 Bilinear",
        "Al6063-T5 Bilinear",
    ]
    linked = client.put(
        f"/api/catalog/links/{material}",
        json={"catalog_material_id": str(first.id)},
        headers=admin_headers,
    )
    assert linked.status_code == 200, linked.text
    assert [one[0] for one in _names(client, admin_headers, material)] == [
        "Al6063-T5 Bilinear"
    ]


def test_목록은_안_이어진_재료만_권한과_함께(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    target = _catalog(db, "Mg_AZ31B_H24 Bilinear", "metal", values=2)
    _catalog(db, "Ti_Grade4 Bilinear", "metal", values=2)
    linked = _material(client, admin_headers, "Metal", "Magnesium", "Mg AZ31B")
    open_one = _material(client, admin_headers, "Metal", "Titanium", "Ti Grade4")
    _material(client, admin_headers, "Metal", "Steel", "NOMATCH01")  # 후보 없음
    assert (
        client.put(
            f"/api/catalog/links/{linked}",
            json={"catalog_material_id": str(target.id)},
            headers=admin_headers,
        ).status_code
        == 200
    )

    page = client.get("/api/catalog/link-candidates", headers=admin_headers)
    assert page.status_code == 200, page.text
    body = page.json()
    assert [one["material_id"] for one in body["items"]] == [open_one]
    assert body["items"][0]["can_edit"] is True
    assert body["items"][0]["candidates"][0]["name"] == "Ti_Grade4 Bilinear"
    assert body["unlinked"] == 2 and body["with_candidates"] == 1

    # 남의 부서 사람은 보이되 잇지 못한다 — 화면이 단추를 잠근다.
    made = client.post(
        "/api/workspaces",
        json={"name": "다른 부서", "slug": "other-dept"},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    account = client.post(
        "/api/accounts",
        json={
            "email": "viewer@example.com",
            "display_name": "보는 사람",
            "workspace_slug": "other-dept",
            "role": "member",
        },
        headers=admin_headers,
    ).json()
    token = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": account["temporary_password"]},
    ).json()["access_token"]
    viewer = {"Authorization": f"Bearer {token}"}
    seen = client.get("/api/catalog/link-candidates", headers=viewer).json()
    assert [one["can_edit"] for one in seen["items"]] == [False]
    refused = client.put(
        f"/api/catalog/links/{open_one}",
        json={"catalog_material_id": str(target.id)},
        headers=viewer,
    )
    assert refused.status_code == 403

    # 상한이 잘라도 개수는 다 센다.
    _catalog(db, "SUS316_annealed Bilinear", "metal", values=1)
    _material(client, admin_headers, "Metal", "Steel", "SUS316")
    capped = client.get(
        "/api/catalog/link-candidates", params={"limit": 1}, headers=admin_headers
    ).json()
    assert len(capped["items"]) == 1 and capped["with_candidates"] == 2


def test_AI_가_이은_연결은_감사에_남고_사람이_이은_것은_안_남는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """MCP 의 `link_catalog_material` 이 잇는 길(2026-10-08). 연결은 BOM 덱이 문헌 값을 그대로
    가져가는 입구라, AI 가 이은 것인지가 남아야 한다 — 등록자 칸은 토큰 주인이다."""
    first = _catalog(db, "Ti_Grade2 Bilinear", "metal", values=1)
    second = _catalog(db, "Ti_Grade2 annealed", "metal", values=1)
    material = _material(client, admin_headers, "Metal", "Titanium", "Ti Grade2")

    def mine() -> list[Any]:
        got = client.get(
            "/api/audit",
            params={"action": "catalog_link.set_by_client", "limit": 200},
            headers=admin_headers,
        ).json()
        return [one for one in got if one["target_id"] == material]

    by_person = client.put(
        f"/api/catalog/links/{material}",
        json={"catalog_material_id": str(first.id)},
        headers=admin_headers,
    )
    assert by_person.status_code == 200, by_person.text
    assert mine() == []

    by_ai = client.put(
        f"/api/catalog/links/{material}",
        json={"catalog_material_id": str(second.id)},
        headers={**admin_headers, "X-Client": "mcp"},
    )
    assert by_ai.status_code == 200, by_ai.text
    logged = mine()
    assert len(logged) == 1 and logged[0]["client"] == "mcp"
    # 무엇에서 무엇으로 바꿨는지 — 앞 연결은 이 기록에만 남는다.
    assert logged[0]["changes"]["catalog_material_id"] == {
        "before": str(first.id),
        "after": str(second.id),
    }
