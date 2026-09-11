"""VOC — 게시판이고 절차다.

지키려는 것:
  - 로그인한 사람은 다 본다(게시판). 번호가 붙고 최신이 위다.
  - 한 건은 등록 → 접수 → 처리 중 → 해결 → 종료 를 거치고, 옮길 때마다 누가·언제·
    무슨 말로 옮겼는지 남는다.
  - 「해결」·「반려」·「다시 열기」 는 말 없이는 못 옮긴다.
  - 관리자와 낸 사람이 갈 수 있는 곳이 다르다. 낸 사람 아닌 사람은 말만 보탠다.
  - 낸 사람은 남이 말을 남기기 전까지만 고치고 지운다.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace


def login_as(
    client: TestClient, db: Session, workspace: Workspace, *, email: str, name: str
) -> dict[str, str]:
    user = User(
        email=email,
        password_hash=security.hash_password("member-password-1"),
        display_name=name,
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "member-password-1"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def member_headers(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    return login_as(client, db, workspace, email="hong", name="홍길동")


def _voc(client: TestClient, headers: dict[str, str], title: str = "느려요") -> dict[str, Any]:
    made = client.post(
        "/api/voc",
        json={"title": title, "body": "목록이 느립니다", "page_path": "/w/metal/tests"},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _move(
    client: TestClient,
    headers: dict[str, str],
    item_id: str,
    status: str | None,
    note: str | None,
) -> Any:
    return client.post(
        f"/api/voc/{item_id}/events", json={"status": status, "note": note}, headers=headers
    )


class Test게시판:
    def test_누구나_전부_보고_번호가_붙는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        kim = login_as(client, db, workspace, email="kim", name="김철수")
        first = _voc(client, hong, title="곡선이 안 보여요")
        second = _voc(client, kim, title="내보내기가 느려요")

        assert first["created_by"] == "홍길동"
        assert first["page_path"] == "/w/metal/tests"
        assert first["status"] == "open" and first["status_label"] == "등록"
        assert second["seq"] == first["seq"] + 1

        # **남의 것도 본다** — 같은 문제를 따로 내지 않게. 최신이 위다.
        page = client.get("/api/voc", headers=hong).json()
        assert page["total"] == 2
        assert [one["title"] for one in page["items"]] == [
            "내보내기가 느려요",
            "곡선이 안 보여요",
        ]
        assert [one["is_mine"] for one in page["items"]] == [False, True]

    def test_상태와_글자와_내_것으로_거른다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        mine = _voc(client, hong, title="느려요")
        _voc(client, admin_headers, title="관리자 메모")
        _move(client, admin_headers, mine["id"], "accepted", None)

        assert client.get("/api/voc?status=accepted", headers=hong).json()["total"] == 1
        assert client.get("/api/voc?q=메모", headers=hong).json()["total"] == 1
        assert client.get("/api/voc?mine=true", headers=hong).json()["total"] == 1
        assert client.get("/api/voc?status=nope", headers=hong).status_code == 422

    def test_등록이_첫_이벤트다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        made = _voc(client, hong)
        assert [one["to_status"] for one in made["events"]] == ["open"]
        assert made["events"][0]["from_status"] is None
        assert made["events"][0]["by"] == "홍길동"
        assert made["event_count"] == 0


class Test절차:
    def test_등록에서_종료까지_이력이_남는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]

        assert _move(client, admin_headers, item_id, "accepted", None).status_code == 200
        assert (
            _move(client, admin_headers, item_id, "in_progress", "보고 있습니다").status_code
            == 200
        )
        done = _move(client, admin_headers, item_id, "resolved", "다음 배포에 반영")
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "resolved"
        # 낸 사람이 확인하고 닫는다.
        closed = _move(client, hong, item_id, "closed", None)
        assert closed.status_code == 200, closed.text

        body = closed.json()
        assert [one["to_status"] for one in body["events"]] == [
            "open",
            "accepted",
            "in_progress",
            "resolved",
            "closed",
        ]
        assert body["events"][3]["note"] == "다음 배포에 반영"
        assert body["events"][4]["by"] == "홍길동"
        assert body["status_by"] == "홍길동"
        assert body["event_count"] == 4

    def test_해결과_반려는_말_없이는_못_옮긴다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        """「해결」 만 찍힌 건은 무엇이 바뀌었는지 아무도 모른다."""
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        for target in ("resolved", "rejected"):
            denied = _move(client, admin_headers, item_id, target, "   ")
            assert denied.status_code == 422, denied.text
            assert denied.json()["error"]["code"] == "MNX-VOC-0007"

    def test_낸_사람은_해결에_동의하지_않으면_이유를_적고_다시_연다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        _move(client, admin_headers, item_id, "resolved", "고쳤습니다")

        assert _move(client, hong, item_id, "open", None).status_code == 422
        reopened = _move(client, hong, item_id, "open", "아직 같은 화면에서 납니다")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["status"] == "open"

    def test_갈_수_있는_곳만_간다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        kim = login_as(client, db, workspace, email="kim", name="김철수")
        item_id = _voc(client, hong)["id"]

        # 낸 사람은 등록 상태에서 옮길 데가 없다 — 해결됐다는 말은 관리자가 한다.
        denied = _move(client, hong, item_id, "resolved", "제가 고쳤어요")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "MNX-VOC-0006"
        # 남은 말만 보탠다.
        assert _move(client, kim, item_id, "accepted", None).status_code == 403
        spoke = _move(client, kim, item_id, None, "저도 같은 증상입니다")
        assert spoke.status_code == 200, spoke.text
        assert spoke.json()["status"] == "open"
        assert spoke.json()["events"][-1]["from_status"] == "open"
        assert spoke.json()["events"][-1]["to_status"] == "open"
        # 등록에서 곧장 종료는 관리자도 못 간다.
        assert _move(client, admin_headers, item_id, "closed", None).status_code == 403

    def test_같은_상태로는_못_옮기고_빈_요청은_거절한다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        assert _move(client, admin_headers, item_id, "open", "x").status_code == 422
        assert _move(client, admin_headers, item_id, None, "  ").status_code == 422

    def test_상세가_이_사람이_갈_수_있는_곳을_말한다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        """**화면이 규칙을 외우지 않는다.** 서버가 말한 단추만 그린다."""
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]

        assert client.get(f"/api/voc/{item_id}", headers=hong).json()["allowed"] == []
        admin_view = client.get(f"/api/voc/{item_id}", headers=admin_headers).json()
        assert admin_view["allowed"] == ["accepted", "in_progress", "resolved", "rejected"]
        assert admin_view["allowed_labels"]["resolved"] == "해결로 옮김"
        assert set(admin_view["note_required"]) == {"resolved", "rejected"}

        _move(client, admin_headers, item_id, "resolved", "고쳤습니다")
        assert client.get(f"/api/voc/{item_id}", headers=hong).json()["allowed"] == [
            "closed",
            "open",
        ]


class Test고치기와_지우기:
    """**낸 사람은 남이 말을 남기기 전까지, 관리자는 언제나.** 남의 말이 달린 뒤에
    본문이 바뀌면 그 말이 딴 소리가 된다."""

    def test_낸_사람이_자기_것을_고친다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]

        fixed = client.patch(
            f"/api/voc/{item_id}", json={"title": "목록이 느려요"}, headers=hong
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["title"] == "목록이 느려요"
        # **안 보낸 칸은 안 건드린다.**
        assert fixed.json()["body"] == "목록이 느립니다"
        assert fixed.json()["can_edit"] is True

    def test_남이_말을_남기면_낸_사람은_못_고친다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        # 자기 댓글로는 안 잠긴다.
        _move(client, hong, item_id, None, "덧붙입니다")
        assert client.get(f"/api/voc/{item_id}", headers=hong).json()["can_edit"] is True

        _move(client, admin_headers, item_id, "accepted", None)
        assert client.get(f"/api/voc/{item_id}", headers=hong).json()["can_edit"] is False
        denied = client.patch(f"/api/voc/{item_id}", json={"title": "딴 얘기"}, headers=hong)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "MNX-VOC-0004"
        # **관리자는 언제나 된다.**
        assert (
            client.patch(
                f"/api/voc/{item_id}", json={"title": "목록 지연"}, headers=admin_headers
            ).status_code
            == 200
        )
        # 목록도 같은 판단을 한다.
        listed = client.get("/api/voc", headers=hong).json()["items"][0]
        assert listed["can_edit"] is False and listed["event_count"] == 2

    def test_남이_낸_것은_못_고치고_못_지운다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        """보이기는 해도 손은 못 댄다."""
        item_id = _voc(client, admin_headers, title="관리자가 낸 것")["id"]
        hong = member_headers(client, db, workspace)

        denied = client.patch(f"/api/voc/{item_id}", json={"title": "x"}, headers=hong)
        assert denied.json()["error"]["code"] == "MNX-VOC-0003"
        assert client.delete(f"/api/voc/{item_id}", headers=hong).status_code == 403

    def test_지우면_이력까지_사라진다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        from sqlalchemy import func, select

        from app.modules.voc.models import VocEvent

        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        _move(client, hong, item_id, None, "덧붙입니다")

        assert client.delete(f"/api/voc/{item_id}", headers=hong).status_code == 204
        assert client.get("/api/voc", headers=hong).json()["total"] == 0
        assert client.get(f"/api/voc/{item_id}", headers=hong).status_code == 404
        assert (
            db.scalar(
                select(func.count()).select_from(VocEvent).where(VocEvent.item_id == item_id)
            )
            == 0
        )
        # 두 번 지우면 없는 것이다 — 화면이 새로고침 전에 한 번 더 누를 수 있다.
        assert client.delete(f"/api/voc/{item_id}", headers=hong).status_code == 404
