"""부서 합치기 — **자료를 옮기고 원본을 보관한다.**

조직 개편은 실제로 일어난다: 두 팀이 한 팀이 되고, 잘못 만든 부서에 자료가 먼저
쌓인다. 그때 부서를 지울 수 없는 것이 맞고(삭제 검사), 그래서 이관이 있어야 한다.

무는 것이 다섯이다.

    자료가 따라간다          재료·시험이 대상 부서 소속이 된다
    멤버는 병합이다           양쪽에 다 있어도 안 터지고, 관리자는 강등되지 않는다
    하위 부서가 따라간다       원본의 자식이 대상 아래로 선다
    순환은 거절한다           하위 부서로 합치면 트리가 돈다
    합친 뒤에는 지워진다       이관의 목적 — 막던 참조가 사라진다
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.materials.models import Material
from app.modules.workspaces.models import Workspace, WorkspaceMember


def make(client: TestClient, headers: dict[str, str], slug: str, name: str) -> None:
    made = client.post("/api/workspaces", json={"slug": slug, "name": name}, headers=headers)
    assert made.status_code == 201, made.text


def merge(client: TestClient, headers: dict[str, str], source: str, target: str) -> Any:
    return client.post(
        f"/api/workspaces/{source}/merge",
        json={"target_slug": target},
        headers=headers,
    )


class Test자료가_따라간다:
    def test_재료가_대상_부서_소속이_된다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        make(client, admin_headers, "old-team", "옛 팀")
        make(client, admin_headers, "new-team", "새 팀")
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "MG01",
                "spec_thickness": 1.0,
                "workspace_slug": "old-team",
            },
            headers=admin_headers,
        ).json()

        done = merge(client, admin_headers, "old-team", "new-team")
        assert done.status_code == 200, done.text
        # 응답이 무엇을 옮겼는지 말한다 — 재료 한 건이 그 안에 있다.
        assert any(one["table"] == "materials" for one in done.json())

        target = db.scalar(select(Workspace).where(Workspace.slug == "new-team"))
        row = db.get(Material, uuid.UUID(material["id"]))
        assert row is not None and target is not None
        assert row.owner_workspace_id == target.id
        # 원본은 지워지지 않고 **보관**된다 — 실수를 되돌릴 수 있어야 한다.
        source = db.scalar(select(Workspace).where(Workspace.slug == "old-team"))
        assert source is not None and source.is_active is False

    def test_합친_뒤에는_지워진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**이것이 이관의 목적이다** — 자료 때문에 못 지우던 부서가 지워진다."""
        make(client, admin_headers, "doomed", "없앨 팀")
        make(client, admin_headers, "keeper", "남을 팀")
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DM01",
                "spec_thickness": 1.0,
                "workspace_slug": "doomed",
            },
            headers=admin_headers,
        )
        # 자료가 있어서 못 지운다.
        refused = client.delete("/api/workspaces/doomed", headers=admin_headers)
        assert refused.status_code in (409, 422), refused.text

        assert merge(client, admin_headers, "doomed", "keeper").status_code == 200
        gone = client.delete("/api/workspaces/doomed", headers=admin_headers)
        assert gone.status_code == 204, gone.text


class Test멤버는_병합이다:
    def test_겹쳐도_안_터지고_관리자는_강등되지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """(부서, 사람) 유일 제약이 있다 — 붙여넣기면 여기서 터진다. 그리고 원본의
        관리자가 대상에서 평멤버가 되면, 합치자마자 그 부서를 아무도 관리 못 한다."""
        make(client, admin_headers, "a-team", "A팀")
        make(client, admin_headers, "b-team", "B팀")
        person = User(
            email="both@example.com",
            display_name="양쪽사람",
            password_hash=security.hash_password("pw12345678"),
        )
        db.add(person)
        db.flush()
        a_team = db.scalar(select(Workspace).where(Workspace.slug == "a-team"))
        b_team = db.scalar(select(Workspace).where(Workspace.slug == "b-team"))
        assert a_team is not None and b_team is not None
        # A팀에서는 관리자, B팀에서는 평멤버 — 겹치는 사람이다.
        db.add(WorkspaceMember(workspace_id=a_team.id, user_id=person.id, role="manager"))
        db.add(WorkspaceMember(workspace_id=b_team.id, user_id=person.id, role="member"))
        db.commit()

        assert merge(client, admin_headers, "a-team", "b-team").status_code == 200
        rows = list(
            db.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == person.id))
        )
        mine = [one for one in rows if one.workspace_id == b_team.id]
        assert len(mine) == 1, "한 줄만 남아야 한다"
        assert mine[0].role == "manager", "합쳤다고 강등되면 안 된다"


class Test트리:
    def test_하위_부서가_대상_아래로_선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        make(client, admin_headers, "lab", "연구소")
        make(client, admin_headers, "lab-child", "산하팀")
        client.post(
            "/api/workspaces/lab-child/move",
            json={"parent_slug": "lab"},
            headers=admin_headers,
        )
        make(client, admin_headers, "hq", "본부")

        assert merge(client, admin_headers, "lab", "hq").status_code == 200
        child = db.scalar(select(Workspace).where(Workspace.slug == "lab-child"))
        target = db.scalar(select(Workspace).where(Workspace.slug == "hq"))
        assert child is not None and target is not None
        assert child.parent_id == target.id

    def test_하위_부서로는_못_합친다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """자식을 대상 아래로 옮기는 순간 트리가 돈다."""
        make(client, admin_headers, "root-x", "뿌리")
        make(client, admin_headers, "leaf-x", "잎")
        client.post(
            "/api/workspaces/leaf-x/move",
            json={"parent_slug": "root-x"},
            headers=admin_headers,
        )
        refused = merge(client, admin_headers, "root-x", "leaf-x")
        assert refused.status_code == 422, refused.text
        assert "순환" in refused.json()["error"]["message"]

    def test_자기_자신과는_못_합친다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        make(client, admin_headers, "solo", "혼자")
        assert merge(client, admin_headers, "solo", "solo").status_code == 422
