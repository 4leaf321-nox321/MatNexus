"""측정 의뢰 — 게시판이고 절차고, 끝이 데이터다.

지키려는 것:
  - 낸 부서와 받는 부서만 본다. 작성 중은 낸 사람만. 제3부서는 404.
  - 받는 쪽과 낸 사람이 갈 수 있는 곳이 다르다. 접수·보류·반려·결과 전달은 말 없이는 못 간다.
  - 시험은 받는 쪽이 접수한 뒤에만 붙이고, **같은 시료·같은 시험 종류**여야 한다.
  - 진행률은 **채택된 결과**만 센다. 지운 시험은 빠진다.
  - 「결과 전달」 은 항목마다 채택 결과가 있어야 한다.
  - 조건은 시험 등록과 같은 규칙으로 SI 가 된다(25 degC → 298.15 K).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun
from app.modules.workspaces.models import Workspace, WorkspaceMember

PASSWORD = "member-password-1"


def _user(
    db: Session, *, email: str, name: str, workspace: Workspace, role: str = "member"
) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name=name,
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    db.commit()
    return user


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def world(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> dict[str, Any]:
    """부서 셋 — 낸 부서(metal, 기본 fixture), 받는 부서(reliability), 제3부서(other).
    시료 하나는 낸 부서에."""
    ensure_builtin_test_types(db)
    lab = Workspace(slug="reliability", name="신뢰성그룹")
    other = Workspace(slug="other", name="다른팀")
    db.add_all([lab, other])
    db.commit()
    kim = _user(db, email="kim", name="김해석", workspace=workspace)
    lee = _user(db, email="lee", name="이측정", workspace=lab, role="manager")
    park = _user(db, email="park", name="박측정", workspace=lab)
    oh = _user(db, email="ohh", name="오제삼", workspace=other)

    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SECC", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    return {
        "lab": lab,
        "other": other,
        "kim": _login(client, "kim"),
        "lee": _login(client, "lee"),
        "park": _login(client, "park"),
        "oh": _login(client, "ohh"),
        "users": {"kim": kim, "lee": lee, "park": park, "oh": oh},
        "material": material,
        "sample": sample,
    }


def _payload(sample_id: str | None, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "SECC 인장 물성",
        "purpose": "성형 해석용 탄소성 카드",
        "sample_id": sample_id,
        "lab_workspace_slug": "reliability",
        "sample_plan": "시편 원판 3장, 9/20 전달",
        "due_on": "2026-10-15",
        "items": [
            {
                "test_type_key": "tensile",
                "conditions": {"temperature": 25, "speed_elastic": 10},
                "condition_units": {"temperature": "degC", "speed_elastic": "mm/min"},
                "orientations": ["MD", "TD"],
                "count": 3,
                "deliverable": "hardening",
            }
        ],
        "submit": True,
    }
    body.update(over)
    return body


def _create(
    client: TestClient, headers: dict[str, str], sample_id: str | None, **over: Any
) -> dict[str, Any]:
    made = client.post("/api/commissions", json=_payload(sample_id, **over), headers=headers)
    assert made.status_code == 201, made.text
    return dict(made.json())


def _move(
    client: TestClient,
    headers: dict[str, str],
    commission_id: str,
    status: str | None,
    note: str | None,
) -> Any:
    return client.post(
        f"/api/commissions/{commission_id}/events",
        json={"status": status, "note": note},
        headers=headers,
    )


def _run(
    client: TestClient, headers: dict[str, str], sample_id: str, *, orientation: str = "MD"
) -> dict[str, Any]:
    """받는 쪽이 낸 부서의 시료에 시편을 만들고 시험을 등록한다 — 표로 입력."""
    specimen = client.post(
        f"/api/samples/{sample_id}/specimens",
        json={"orientation": orientation},
        headers=headers,
    )
    assert specimen.status_code == 201, specimen.text
    created = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen.json()["id"],
            "test_type": "tensile",
            "conditions": '{"temperature": 25, "speed_elastic": 10}',
            "condition_units": '{"temperature": "degC", "speed_elastic": "mm/min"}',
        },
        files={"file": ("empty.csv", b"strain,stress\n0,0\n0.1,100\n")},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    return dict(created.json())


def _adopt(db: Session, run_id: str) -> None:
    """채택된 결과가 있는 것으로 — 진행률은 이것만 센다. 처리 파이프라인을 다 돌리지 않고
    열만 채운다(가리키는 행은 없어도 FK 가 없는 열이라 시험에는 충분하다)."""
    run = db.get(TestRun, run_id)
    assert run is not None
    from app.modules.processing.models import ProcessingResult

    result = ProcessingResult(
        test_run_id=run.id,
        source_curve_key="raw",
        storage_path="test/none.parquet",
        row_count=0,
        sha256="0" * 64,
        byte_size=0,
    )
    db.add(result)
    db.flush()
    run.adopted_result_id = result.id
    db.commit()


class Test흐름:
    def test_의뢰에서_완료까지(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        made = _create(client, kim, world["sample"]["id"])
        assert made["status"] == "submitted" and made["status_label"] == "접수 대기"
        assert made["seq"] >= 1
        assert made["side"] == "requester" and made["is_mine"]
        assert made["requester_workspace"]["slug"] == "metal"
        assert made["lab_workspace"]["slug"] == "reliability"
        assert made["sample"]["material_name"]
        assert made["progress"] == {"total": 3, "linked": 0, "done": 0}
        # 등록이 첫 이벤트다.
        assert [one["to_status"] for one in made["events"]] == ["submitted"]
        # 낸 사람은 되돌리기만, 받는 쪽 단추는 없다.
        assert made["allowed"] == ["draft"]
        assert made["can_edit"] and not made["can_link"]

        # 받는 쪽이 본다 — 단추가 다르다.
        seen = client.get(f"/api/commissions/{made['id']}", headers=lee).json()
        assert seen["side"] == "lab"
        assert seen["allowed"] == ["accepted", "rejected"]
        assert seen["note_required"] == ["accepted", "rejected"]
        assert seen["can_assign"] and {one["name"] for one in seen["assignees"]} == {
            "이측정",
            "박측정",
        }

        # 접수는 말 없이 못 간다.
        assert _move(client, lee, made["id"], "accepted", None).status_code == 422
        accepted = _move(client, lee, made["id"], "accepted", "10월 첫 주 예정").json()
        assert accepted["status"] == "accepted"
        assert accepted["can_link"]

        # 담당자 지정 — 받는 부서 멤버만.
        park_id = str(world["users"]["park"].id)
        assigned = client.post(
            f"/api/commissions/{made['id']}/assignee",
            json={"assignee_id": park_id},
            headers=lee,
        ).json()
        assert assigned["assignee"]["name"] == "박측정"
        kim_id = str(world["users"]["kim"].id)
        assert (
            client.post(
                f"/api/commissions/{made['id']}/assignee",
                json={"assignee_id": kim_id},
                headers=lee,
            ).status_code
            == 422
        )

        # 받는 쪽이 낸 부서 시료에 시험을 등록하고 항목에 붙인다 → 저절로 시험 중.
        run = _run(client, lee, world["sample"]["id"])
        item_id = accepted["items"][0]["id"]
        linked = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        assert linked.status_code == 200, linked.text
        body = linked.json()
        assert body["status"] == "in_progress"
        assert body["progress"] == {"total": 3, "linked": 1, "done": 0}
        assert [one["record_name"] for one in body["items"][0]["runs"]] == [run["record_name"]]
        assert any("시험 연결" in (one["note"] or "") for one in body["events"])
        # 붙은 시험은 후보에서 빠진다.
        assert body["items"][0]["candidates"] == []

        # 채택 결과가 없으면 「결과 전달」 못 간다.
        blocked = _move(client, lee, made["id"], "delivered", "카드 탭에서 보세요")
        assert blocked.status_code == 422
        assert "채택된 결과가 없는 항목" in blocked.json()["error"]["message"]

        _adopt(db, run["id"])
        body = client.get(f"/api/commissions/{made['id']}", headers=lee).json()
        assert body["progress"] == {"total": 3, "linked": 1, "done": 1}
        assert body["items"][0]["done"] == 1

        delivered = _move(client, lee, made["id"], "delivered", "재료 상세 > CAE 카드").json()
        assert delivered["status"] == "delivered"

        # 낸 사람이 확인하고 완료. 받는 쪽은 완료로 못 옮긴다.
        assert _move(client, lee, made["id"], "closed", None).status_code == 403
        closed = _move(client, kim, made["id"], "closed", None).json()
        assert closed["status"] == "closed"
        assert [
            one["to_status"]
            for one in closed["events"]
            if one["from_status"] != one["to_status"]
        ] == [
            "submitted",
            "accepted",
            "in_progress",
            "delivered",
            "closed",
        ]

    def test_조건은_시험_등록과_같은_규칙으로_SI_가_된다(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        made = _create(client, world["kim"], world["sample"]["id"])
        item = made["items"][0]
        assert item["conditions"]["temperature"] == pytest.approx(298.15)
        assert item["conditions"]["speed_elastic"] == pytest.approx(10 / 60000)
        assert item["input_units"] == {"temperature": "degC", "speed_elastic": "mm/min"}
        assert item["test_type_label"] == "인장시험"
        assert item["orientations"] == ["MD", "TD"] and item["count"] == 3

        # 정의에 없는 조건·모르는 받을 것은 거절.
        bad = client.post(
            "/api/commissions",
            json=_payload(
                world["sample"]["id"],
                items=[{"test_type_key": "tensile", "conditions": {"humidity": 50}}],
            ),
            headers=world["kim"],
        )
        assert bad.status_code == 422
        bad = client.post(
            "/api/commissions",
            json=_payload(
                world["sample"]["id"],
                items=[{"test_type_key": "tensile", "deliverable": "nope"}],
            ),
            headers=world["kim"],
        )
        assert bad.status_code == 422
        ok = client.post(
            "/api/commissions",
            json=_payload(
                world["sample"]["id"],
                items=[{"test_type_key": "tensile", "deliverable": "curves"}],
            ),
            headers=world["kim"],
        )
        assert ok.status_code == 201

    def test_작성_중은_낸_사람만_보고_고치고_지운다(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        draft = _create(client, kim, world["sample"]["id"], submit=False)
        assert draft["status"] == "draft"
        assert client.get(f"/api/commissions/{draft['id']}", headers=lee).status_code == 404
        assert client.get("/api/commissions", headers=lee).json()["total"] == 0

        # 고치기 — 안 보낸 칸은 그대로, 항목은 통째로 갈아 넣는다.
        patched = client.patch(
            f"/api/commissions/{draft['id']}",
            json={
                "title": "SECC 인장·굽힘",
                "items": [
                    {"test_type_key": "tensile", "count": 2},
                    {"test_type_key": "tensile", "count": 1, "orientations": ["DD"]},
                ],
            },
            headers=kim,
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert body["title"] == "SECC 인장·굽힘"
        assert body["purpose"] == "성형 해석용 탄소성 카드"
        assert body["due_on"] == "2026-10-15"
        assert [one["count"] for one in body["items"]] == [2, 1]
        assert body["progress"]["total"] == 3

        # 기한 비우기 — 「안 보냄」 과 다르다.
        cleared = client.patch(
            f"/api/commissions/{draft['id']}", json={"due_on": None}, headers=kim
        ).json()
        assert cleared["due_on"] is None

        # 낸다 → 받는 쪽이 보인다. 낸 뒤에는 못 지운다.
        submitted = _move(client, kim, draft["id"], "submitted", None).json()
        assert submitted["status"] == "submitted"
        assert client.get(f"/api/commissions/{draft['id']}", headers=lee).status_code == 200
        assert client.delete(f"/api/commissions/{draft['id']}", headers=kim).status_code == 403

        # 접수되면 낸 사람도 못 고친다.
        _move(client, lee, draft["id"], "accepted", "다음 주")
        assert (
            client.patch(
                f"/api/commissions/{draft['id']}", json={"title": "바꿈"}, headers=kim
            ).status_code
            == 403
        )

        # 작성 중으로 되돌린 것은 지운다.
        another = _create(client, kim, world["sample"]["id"], submit=False)
        assert (
            client.delete(f"/api/commissions/{another['id']}", headers=kim).status_code == 204
        )
        assert client.get(f"/api/commissions/{another['id']}", headers=kim).status_code == 404


class Test권한:
    def test_제3부서는_못_보고_낸_쪽은_시험을_못_붙인다(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        kim, lee, oh = world["kim"], world["lee"], world["oh"]
        made = _create(client, kim, world["sample"]["id"])
        assert client.get(f"/api/commissions/{made['id']}", headers=oh).status_code == 404
        assert client.get("/api/commissions", headers=oh).json()["total"] == 0
        assert _move(client, oh, made["id"], None, "끼어들기").status_code == 404

        # 낸 사람은 접수를 못 한다. 받는 쪽은 작성 중으로 못 되돌린다.
        assert _move(client, kim, made["id"], "accepted", "내가 접수").status_code == 403
        assert _move(client, lee, made["id"], "draft", None).status_code == 403

        # 접수 전에는 받는 쪽도 시험을 못 붙인다.
        run = _run(client, lee, world["sample"]["id"])
        item_id = made["items"][0]["id"]
        early = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        assert early.status_code == 422
        _move(client, lee, made["id"], "accepted", "다음 주")
        # 낸 사람은 접수 뒤에도 못 붙인다.
        mine = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": run["id"]},
            headers=kim,
        )
        assert mine.status_code == 403
        # 받는 부서 멤버(관리자 아님)도 붙인다 — 측정은 팀이 한다.
        ok = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": run["id"]},
            headers=world["park"],
        )
        assert ok.status_code == 200, ok.text

    def test_목록은_범위로_가른다(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        _create(client, kim, world["sample"]["id"], title="첫 의뢰")
        _create(client, kim, world["sample"]["id"], title="둘째 의뢰", submit=False)
        assert client.get("/api/commissions?scope=mine", headers=kim).json()["total"] == 2
        assert client.get("/api/commissions?scope=received", headers=kim).json()["total"] == 0
        received = client.get("/api/commissions?scope=received", headers=lee).json()
        assert received["total"] == 1 and received["items"][0]["side"] == "lab"
        assert client.get("/api/commissions?status=draft", headers=lee).json()["total"] == 0
        assert client.get("/api/commissions?q=둘째", headers=kim).json()["total"] == 1
        assert client.get("/api/commissions?scope=nope", headers=kim).status_code == 422


class Test시험연결:
    def test_같은_시료_같은_종류만_붙고_한_시험은_한_항목에만(
        self,
        client: TestClient,
        db: Session,
        world: dict[str, Any],
        admin_headers: dict[str, str],
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        made = _create(client, kim, world["sample"]["id"])
        _move(client, lee, made["id"], "accepted", "다음 주")
        item_id = made["items"][0]["id"]

        # 다른 시료의 시험.
        other_sample = client.post(
            f"/api/materials/{world['material']['id']}/samples", json={}, headers=admin_headers
        ).json()
        stranger = _run(client, lee, other_sample["id"])
        rejected = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": stranger["id"]},
            headers=lee,
        )
        assert rejected.status_code == 422
        assert "이 의뢰의 시료" in rejected.json()["error"]["message"]

        # 후보는 같은 시료·같은 종류·안 붙은 것.
        run = _run(client, lee, world["sample"]["id"])
        detail = client.get(f"/api/commissions/{made['id']}", headers=lee).json()
        assert [one["id"] for one in detail["items"][0]["candidates"]] == [run["id"]]
        # 낸 쪽은 후보를 못 본다 — 붙일 수 없는 사람에게 목록은 소음이다.
        assert (
            client.get(f"/api/commissions/{made['id']}", headers=kim).json()["items"][0][
                "candidates"
            ]
            == []
        )

        client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        # 같은 시험을 다른 의뢰에 붙이면 거절.
        second = _create(client, kim, world["sample"]["id"], title="둘째")
        _move(client, lee, second["id"], "accepted", "다음 주")
        dup = client.post(
            f"/api/commissions/{second['id']}/items/{second['items'][0]['id']}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        assert dup.status_code == 422
        assert "이미 다른 의뢰 항목" in dup.json()["error"]["message"]

        # 연결을 풀면 후보로 돌아온다. 시험은 남는다.
        unlinked = client.delete(
            f"/api/commissions/{made['id']}/items/{item_id}/runs/{run['id']}", headers=lee
        )
        assert unlinked.status_code == 200, unlinked.text
        assert unlinked.json()["progress"]["linked"] == 0
        assert db.get(TestRun, run["id"]) is not None
        assert client.get(f"/api/test-runs/{run['id']}", headers=lee).status_code == 200

    def test_진행률은_채택된_것만_세고_지운_시험은_빠진다(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        made = _create(client, kim, world["sample"]["id"])
        _move(client, lee, made["id"], "accepted", "다음 주")
        item_id = made["items"][0]["id"]
        first = _run(client, lee, world["sample"]["id"], orientation="MD")
        second = _run(client, lee, world["sample"]["id"], orientation="TD")
        for run in (first, second):
            client.post(
                f"/api/commissions/{made['id']}/items/{item_id}/runs",
                json={"run_id": run["id"]},
                headers=lee,
            )
        _adopt(db, first["id"])
        row = client.get("/api/commissions?scope=mine", headers=kim).json()["items"][0]
        assert row["progress"] == {"total": 3, "linked": 2, "done": 1}

        # 채택된 시험을 지우면(소프트) 진행률이 함께 준다 — 저장해 두면 틀린 채 남는다.
        gone = db.get(TestRun, first["id"])
        assert gone is not None
        gone.deleted_at = datetime.now(UTC)
        db.commit()
        row = client.get("/api/commissions?scope=mine", headers=kim).json()["items"][0]
        assert row["progress"] == {"total": 3, "linked": 1, "done": 0}


class Test알림:
    def _inbox(self, client: TestClient, headers: dict[str, str]) -> list[str]:
        return [
            one["title"] for one in client.get("/api/notifications", headers=headers).json()
        ]

    def test_새_의뢰는_받는_부서_관리자에게_움직임은_상대에게(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        from app.jobs import handlers, queue, worker

        def drain() -> None:
            handlers.load_all()
            while worker.run_once(session=db):
                pass

        for user in db.query(User).all():
            queue.enqueue(
                db, kind="notifications.ensure_rules", payload={"user_id": str(user.id)}
            )
        db.commit()
        drain()

        kim, lee, park = world["kim"], world["lee"], world["park"]
        made = _create(client, kim, world["sample"]["id"], title="SECC 물성")
        drain()
        # 받는 부서 **관리자**에게. 멤버(박)와 낸 사람에게는 안 간다.
        assert any(
            "새 측정 의뢰" in one and "SECC 물성" in one for one in self._inbox(client, lee)
        )
        assert self._inbox(client, park) == []
        assert self._inbox(client, kim) == []

        _move(client, lee, made["id"], "accepted", "10월 첫 주")
        drain()
        mine = self._inbox(client, kim)
        assert any("접수 대기 → 접수" in one for one in mine), mine
        # 옮긴 사람 자신에게는 안 간다.
        assert not any("→" in one for one in self._inbox(client, lee))

        # 낸 사람이 말을 보태면 — 마지막으로 다룬 사람(이측정)에게.
        _move(client, kim, made["id"], None, "시료는 9/20 보냅니다")
        drain()
        assert any("말을 보탰습니다" in one for one in self._inbox(client, lee))
        detail = client.get("/api/notifications", headers=lee).json()[0]
        assert detail["link"] == f"/commissions/{made['id']}"


class Test새재료와종류미정:
    def test_시료_없이_새_재료를_적어_의뢰하고_받는_쪽이_시료를_잇는다(
        self,
        client: TestClient,
        db: Session,
        world: dict[str, Any],
        admin_headers: dict[str, str],
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        # 둘 다 없으면 거절.
        bare = client.post(
            "/api/commissions",
            json=_payload(None, material_hint=None),
            headers=kim,
        )
        assert bare.status_code == 422
        made = _create(client, kim, None, material_hint="SGARC440 1.2t, 포스코, 새 강종")
        assert made["sample"] is None
        assert made["material_hint"] == "SGARC440 1.2t, 포스코, 새 강종"
        _move(client, lee, made["id"], "accepted", "재료 등록 후 진행")
        item_id = made["items"][0]["id"]

        # 시료가 없으면 시험을 못 붙인다.
        run = _run(client, lee, world["sample"]["id"])
        early = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        assert early.status_code == 422
        assert "시료가 아직 없습니다" in early.json()["error"]["message"]

        # 받는 쪽이 재료·시료를 등록하고 잇는다. 낸 쪽은 접수 뒤라 못 잇는다.
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SGARC440",
                "spec_thickness": 1.2,
            },
            headers=admin_headers,
        ).json()
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=lee
        ).json()
        assert (
            client.post(
                f"/api/commissions/{made['id']}/sample",
                json={"sample_id": sample["id"]},
                headers=kim,
            ).status_code
            == 403
        )
        attached = client.post(
            f"/api/commissions/{made['id']}/sample",
            json={"sample_id": sample["id"]},
            headers=lee,
        )
        assert attached.status_code == 200, attached.text
        body = attached.json()
        assert body["sample"]["record_name"] == sample["record_name"]
        assert body["material_hint"] == "SGARC440 1.2t, 포스코, 새 강종"
        assert any("시료 연결" in (one["note"] or "") for one in body["events"])

        # 이제 그 시료의 시험만 붙는다.
        new_run = _run(client, lee, sample["id"])
        linked = client.post(
            f"/api/commissions/{made['id']}/items/{item_id}/runs",
            json={"run_id": new_run["id"]},
            headers=lee,
        )
        assert linked.status_code == 200, linked.text
        # 시험이 붙은 뒤에는 시료를 못 바꾼다.
        swap = client.post(
            f"/api/commissions/{made['id']}/sample",
            json={"sample_id": world["sample"]["id"]},
            headers=lee,
        )
        assert swap.status_code == 422

    def test_종류_미정_항목은_물성_이름으로_적고_받는_쪽이_종류를_정한다(
        self, client: TestClient, db: Session, world: dict[str, Any]
    ) -> None:
        kim, lee = world["kim"], world["lee"]
        # 종류도 물성 이름도 없으면 거절.
        bare = client.post(
            "/api/commissions",
            json=_payload(world["sample"]["id"], items=[{"count": 2}]),
            headers=kim,
        )
        assert bare.status_code == 422
        made = _create(
            client,
            kim,
            world["sample"]["id"],
            items=[{"property_hint": "80 °C 탄성계수", "count": 2, "deliverable": "curves"}],
        )
        item = made["items"][0]
        assert item["test_type_key"] is None and item["test_type_label"] is None
        assert item["property_hint"] == "80 °C 탄성계수"
        assert item["conditions"] == {}
        _move(client, lee, made["id"], "accepted", "고온 인장으로")

        # 종류 미정이면 시험을 못 붙인다. 후보도 없다.
        run = _run(client, lee, world["sample"]["id"])
        detail = client.get(f"/api/commissions/{made['id']}", headers=lee).json()
        assert detail["items"][0]["candidates"] == []
        assert detail["can_resolve"]
        early = client.post(
            f"/api/commissions/{made['id']}/items/{item['id']}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        assert early.status_code == 422
        assert "종류가 미정" in early.json()["error"]["message"]

        # 낸 쪽은 못 정한다(접수 뒤). 받는 쪽이 종류와 조건을 정한다 — 조건은 SI 로.
        assert (
            client.post(
                f"/api/commissions/{made['id']}/items/{item['id']}/test-type",
                json={"test_type_key": "tensile"},
                headers=kim,
            ).status_code
            == 403
        )
        resolved = client.post(
            f"/api/commissions/{made['id']}/items/{item['id']}/test-type",
            json={
                "test_type_key": "tensile",
                "conditions": {"temperature": 80},
                "condition_units": {"temperature": "degC"},
            },
            headers=lee,
        )
        assert resolved.status_code == 200, resolved.text
        body = resolved.json()
        assert body["items"][0]["test_type_key"] == "tensile"
        assert body["items"][0]["conditions"]["temperature"] == pytest.approx(353.15)
        assert body["items"][0]["property_hint"] == "80 °C 탄성계수"
        assert [one["id"] for one in body["items"][0]["candidates"]] == [run["id"]]
        assert any("시험 종류 결정" in (one["note"] or "") for one in body["events"])

        # 붙은 뒤에는 종류를 못 바꾼다.
        client.post(
            f"/api/commissions/{made['id']}/items/{item['id']}/runs",
            json={"run_id": run["id"]},
            headers=lee,
        )
        again = client.post(
            f"/api/commissions/{made['id']}/items/{item['id']}/test-type",
            json={"test_type_key": "tensile"},
            headers=lee,
        )
        assert again.status_code == 422
