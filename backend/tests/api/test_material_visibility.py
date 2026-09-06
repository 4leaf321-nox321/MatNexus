"""누가 어느 부서의 물성을 보는가 — **기본은 전원, 가리는 쪽이 예외다.**

전에는 「전역 + 내 부서」 만 보였다. 시스템 관리자가 아닌 계정으로 들어가면 다른
사업부의 재료가 통째로 없었고, 데이터가 없는 것과 구별이 안 됐다(2026-09-05
실사용 보고). 물성은 사업부 간 공유가 목적인 데이터다.

그래서 부서에 `restricted` 손잡이를 두고 **켠 부서만** 멤버로 좁힌다. 여기서
보는 것은 그 두 방향 다다 — 열린 부서는 남에게 보이고, 잠근 부서는 안 보이고,
잠가도 **고칠 권한은 안 생긴다**(보는 것과 고치는 것은 다른 축).

시험은 재료를 따라간다(`visible_runs`). 그래서 재료가 보이면 그 시험도 보이고,
안 보이면 그 시험도 안 보여야 한다 — 한쪽만 보이면 「재료는 있는데 시험이 없다」
가 된다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.materials.models import Material
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


def _login_member_of(
    client: TestClient, admin_headers: dict[str, str], *, slug: str, email: str
) -> dict[str, str]:
    """`slug` 부서의 평범한 멤버로 로그인한 헤더."""
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


def _material_with_run(
    client: TestClient, db: Session, admin_headers: dict[str, str], *, owner_slug: str
) -> tuple[str, str]:
    """`owner_slug` 부서 소유의 재료 하나와 그 아래 시험 하나. (재료 id, 시험 id)"""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"VIS-{uuid.uuid4().hex[:6]}",
            "workspace_slug": owner_slug,
        },
        headers=admin_headers,
    )
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
    # 시험은 올리는 길로 만든다 — 화면과 같은 길이어야 가시성 판정도 같은 길을 탄다.
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
    return material_id, run.json()["id"]


class TestVisibility:
    def test_기본은_다른_부서의_재료와_시험도_보인다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            made = client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
            assert made.status_code == 201, made.text
        material_id, run_id = _material_with_run(
            client, db, admin_headers, owner_slug="dept-a"
        )
        b_member = _login_member_of(
            client, admin_headers, slug="dept-b", email="b-member@example.com"
        )

        seen = client.get(f"/api/materials/{material_id}", headers=b_member)
        assert seen.status_code == 200, seen.text
        listed = client.get("/api/materials?limit=200", headers=b_member)
        assert material_id in {row["id"] for row in listed.json()["items"]}
        run = client.get(f"/api/test-runs/{run_id}", headers=b_member)
        assert run.status_code == 200, run.text

    def test_잠근_부서의_것은_멤버가_아니면_안_보인다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        material_id, run_id = _material_with_run(
            client, db, admin_headers, owner_slug="dept-a"
        )
        b_member = _login_member_of(
            client, admin_headers, slug="dept-b", email="b-member@example.com"
        )
        a_member = _login_member_of(
            client, admin_headers, slug="dept-a", email="a-member@example.com"
        )

        locked = client.patch(
            "/api/workspaces/dept-a", json={"restricted": True}, headers=admin_headers
        )
        assert locked.status_code == 200, locked.text
        assert locked.json()["restricted"] is True

        # 남에게는 없는 것이 된다 — 상세·목록·시험 셋 다.
        assert client.get(f"/api/materials/{material_id}", headers=b_member).status_code == 404
        listed = client.get("/api/materials?limit=200", headers=b_member)
        assert material_id not in {row["id"] for row in listed.json()["items"]}
        assert client.get(f"/api/test-runs/{run_id}", headers=b_member).status_code == 404

        # 멤버에게는 그대로 보인다.
        assert client.get(f"/api/materials/{material_id}", headers=a_member).status_code == 200
        assert client.get(f"/api/test-runs/{run_id}", headers=a_member).status_code == 200

        # 다시 열면 돌아온다 — 「안 보낸 것」 은 그대로 둔다(이름만 바꿔도 잠금이
        # 풀리면 안 된다).
        renamed = client.patch(
            "/api/workspaces/dept-a", json={"name": "A"}, headers=admin_headers
        )
        assert renamed.json()["restricted"] is True
        client.patch(
            "/api/workspaces/dept-a", json={"restricted": False}, headers=admin_headers
        )
        assert client.get(f"/api/materials/{material_id}", headers=b_member).status_code == 200

    def test_보인다고_고칠_수_있는_것은_아니다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """보는 것과 고치는 것은 다른 축이다. 전원에게 열었다고 남의 부서 재료를
        고칠 수 있게 되면 그건 공유가 아니라 사고다."""
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        material_id, _ = _material_with_run(client, db, admin_headers, owner_slug="dept-a")
        b_member = _login_member_of(
            client, admin_headers, slug="dept-b", email="b-member@example.com"
        )

        assert client.get(f"/api/materials/{material_id}", headers=b_member).status_code == 200
        changed = client.patch(
            f"/api/materials/{material_id}", json={"details": "남이 고침"}, headers=b_member
        )
        assert changed.status_code == 403, changed.text
        stored = db.get(Material, uuid.UUID(material_id))
        assert stored is not None and stored.details != "남이 고침"
