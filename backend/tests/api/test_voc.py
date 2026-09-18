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

    def test_관리자는_잘못_옮긴_이력을_지우고_상태가_남은_이력에서_되돌아온다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        """「해결」 로 옮겼다가 「처리 중」 으로 되돌리는 실수 — 지울 길이 없었다
        (VOC 2026-09-13). 지우면 상태는 마지막으로 남은 이동이 정한다."""
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        assert (
            _move(client, admin_headers, item_id, "in_progress", "보는 중").status_code == 200
        )
        wrong = _move(client, admin_headers, item_id, "resolved", "실수로 눌렀다")
        assert wrong.status_code == 200
        wrong_event = wrong.json()["events"][-1]
        assert wrong.json()["status"] == "resolved"
        assert wrong.json()["can_delete_events"] is True

        # 낸 사람은 못 지운다. 등록 줄도 못 지운다.
        denied = client.delete(f"/api/voc/{item_id}/events/{wrong_event['id']}", headers=hong)
        assert denied.status_code == 403
        first = wrong.json()["events"][0]
        kept = client.delete(f"/api/voc/{item_id}/events/{first['id']}", headers=admin_headers)
        assert kept.status_code == 422

        gone = client.delete(
            f"/api/voc/{item_id}/events/{wrong_event['id']}", headers=admin_headers
        )
        assert gone.status_code == 200, gone.text
        body = gone.json()
        assert body["status"] == "in_progress", "남은 이력의 마지막 이동이 곧 상태다"
        assert [one["to_status"] for one in body["events"]] == ["open", "in_progress"]
        assert body["status_by"] == "시스템 관리자"

        # 댓글은 상태를 안 바꾸므로, 댓글 뒤의 이동을 지워도 댓글은 남고 상태만 되돌아간다.
        assert _move(client, admin_headers, item_id, None, "메모 하나").status_code == 200
        again = _move(client, admin_headers, item_id, "resolved", "정말 해결")
        last = again.json()["events"][-1]
        back = client.delete(f"/api/voc/{item_id}/events/{last['id']}", headers=admin_headers)
        assert back.json()["status"] == "in_progress"
        assert [one["note"] for one in back.json()["events"]][-1] == "메모 하나"

    def test_관리자는_이력의_말을_고치되_필수인_말은_못_비운다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        """옮기면서 적었어야 할 말을 빠뜨린 경우(VOC 2026-09-13)."""
        hong = member_headers(client, db, workspace)
        item_id = _voc(client, hong)["id"]
        moved = _move(client, admin_headers, item_id, "resolved", "임시")
        event_id = moved.json()["events"][-1]["id"]

        denied = client.patch(
            f"/api/voc/{item_id}/events/{event_id}", json={"note": "몰래"}, headers=hong
        )
        assert denied.status_code == 403

        fixed = client.patch(
            f"/api/voc/{item_id}/events/{event_id}",
            json={"note": "v1.229 에서 고쳤습니다 — 원본 교체 기능"},
            headers=admin_headers,
        )
        assert fixed.status_code == 200, fixed.text
        body = fixed.json()
        assert body["events"][-1]["note"] == "v1.229 에서 고쳤습니다 — 원본 교체 기능"
        assert body["events"][-1]["to_status"] == "resolved", "상태 이동은 그대로다"
        assert body["status"] == "resolved"

        # 「해결」 로 옮긴 줄의 말은 비울 수 없다 — 무엇이 바뀌었는지 남아야 한다.
        emptied = client.patch(
            f"/api/voc/{item_id}/events/{event_id}", json={"note": "  "}, headers=admin_headers
        )
        assert emptied.status_code == 422

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


class Test알림:
    """게시판을 들여다보지 않아도 **내 건이 움직이면 안다.**

    새 건은 관리자에게, 남이 옮기거나 말을 보태면 낸 사람에게, 낸 사람이 다시
    열면 마지막으로 다룬 관리자에게. 자기가 한 일은 자기에게 안 간다.
    """

    def _inbox(self, client: TestClient, headers: dict[str, str]) -> list[str]:
        return [
            one["title"] for one in client.get("/api/notifications", headers=headers).json()
        ]

    def test_새_건은_관리자에게_움직임은_낸_사람에게(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin: User,
        admin_headers: dict[str, str],
    ) -> None:
        from app.jobs import handlers, queue, worker

        def drain(db: Session) -> None:
            """큐가 빌 때까지 워커를 돌린다(test_notifications 와 같은 것)."""
            handlers.load_all()
            while worker.run_once(session=db):
                pass

        hong = member_headers(client, db, workspace)
        # 기본 규칙(관리자: voc.registered, 모두: voc.changed)은 큐를 거쳐 붙는다.
        for user in db.query(User).all():
            queue.enqueue(
                db, kind="notifications.ensure_rules", payload={"user_id": str(user.id)}
            )
        db.commit()
        drain(db)

        item = _voc(client, hong, title="검색이 느려요")
        drain(db)
        assert any(
            "새 VOC" in one and "검색이 느려요" in one
            for one in self._inbox(client, admin_headers)
        )
        # 낸 사람은 자기 등록으로 알림을 받지 않는다.
        assert self._inbox(client, hong) == []

        _move(client, admin_headers, item["id"], "accepted", None)
        _move(client, admin_headers, item["id"], "resolved", note="색인을 붙였습니다")
        drain(db)
        mine = self._inbox(client, hong)
        assert any("등록 → 접수" in one for one in mine), mine
        assert any("접수 → 해결" in one for one in mine), mine
        # 관리자는 자기가 옮긴 것으로 알림을 받지 않는다.
        assert not any("→" in one for one in self._inbox(client, admin_headers))

        # 낸 사람이 다시 열면 — 마지막으로 다룬 관리자에게 간다.
        _move(client, hong, item["id"], "open", note="아직 느립니다")
        drain(db)
        assert any("해결 → 등록" in one for one in self._inbox(client, admin_headers))

        # 말만 보태도 상대에게 간다.
        _move(client, admin_headers, item["id"], None, note="다시 보겠습니다")
        drain(db)
        assert any("말을 보탰습니다" in one for one in self._inbox(client, hong))
        detail = client.get("/api/notifications", headers=hong).json()[0]
        assert detail["link"] == f"/voc/{item['id']}"


class Test첨부:
    """**캡처 한 장이 글보다 빠르다**(2026-09-18). 붙이고·내려받고·떼고 — 낸 사람·관리자."""

    def _attach(
        self, client: TestClient, headers: dict[str, str], item_id: str, name: str, data: bytes
    ) -> Any:
        return client.post(
            f"/api/voc/{item_id}/attachments",
            files={"file": (name, data, "image/png")},
            headers=headers,
        )

    def test_붙이고_내려받고_뗀다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        mine = member_headers(client, db, workspace)
        item = _voc(client, mine)
        made = self._attach(client, mine, item["id"], "캡처.png", b"\x89PNG fake")
        assert made.status_code == 201, made.text
        body = made.json()
        assert [one["filename"] for one in body["attachments"]] == ["캡처.png"]
        assert body["attachments"][0]["size"] == len(b"\x89PNG fake")
        assert body["attachment_count"] == 1
        assert body["can_attach"] is True

        # 목록도 첨부 수를 안다 — 건마다 세지 않고 한 번에.
        listed = client.get("/api/voc", headers=admin_headers).json()["items"]
        assert next(one for one in listed if one["id"] == item["id"])["attachment_count"] == 1

        # **첨부로만 내린다** — 올린 파일이 HTML 이어도 문서로 열리지 않게.
        got = client.get(body["attachments"][0]["url"], headers=mine)
        assert got.status_code == 200
        assert got.content == b"\x89PNG fake"
        assert "attachment" in got.headers["content-disposition"]
        assert got.headers["x-content-type-options"] == "nosniff"

        gone = client.delete(
            f"/api/voc/{item['id']}/attachments/{body['attachments'][0]['id']}", headers=mine
        )
        assert gone.status_code == 200
        assert gone.json()["attachments"] == []

    def test_남의_건에는_못_붙이고_관리자는_붙인다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        mine = member_headers(client, db, workspace)
        other = login_as(client, db, workspace, email="park", name="박연구")
        item = _voc(client, mine)
        assert self._attach(client, other, item["id"], "a.txt", b"x").status_code == 403
        assert (
            self._attach(client, admin_headers, item["id"], "a.txt", b"x").status_code == 201
        )
        # 남이 말을 남긴 뒤에도 낸 사람은 붙인다 — 글 고치기와 다른 규칙이다.
        _move(client, other, item["id"], None, "저도 그래요")
        assert self._attach(client, mine, item["id"], "b.txt", b"y").status_code == 201
        assert (
            client.get(f"/api/voc/{item['id']}", headers=other).json()["can_attach"] is False
        )

    def test_너무_크면_받다가_멈춘다(
        self, client: TestClient, db: Session, workspace: Workspace, monkeypatch: Any
    ) -> None:
        from app.modules.voc import routes

        monkeypatch.setattr(routes, "MAX_ATTACHMENT_BYTES", 16)
        mine = member_headers(client, db, workspace)
        item = _voc(client, mine)
        too_big = self._attach(client, mine, item["id"], "big.bin", b"0" * 17)
        assert too_big.status_code == 413
        assert client.get(f"/api/voc/{item['id']}", headers=mine).json()["attachments"] == []


class Test내보내기:
    """고른 건들을 zip 하나로 — 건마다 폴더, `item.json` + `attachments/`(2026-09-18)."""

    def test_zip_안에_건마다_폴더와_json_그리고_첨부가_있다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        import io
        import json
        import zipfile

        mine = member_headers(client, db, workspace)
        first = _voc(client, mine, title="목록이 느려요: 재료/시험")
        second = _voc(client, mine, title="두 번째")
        client.post(
            f"/api/voc/{first['id']}/attachments",
            files={"file": ("캡처.png", b"\x89PNG", "image/png")},
            headers=mine,
        )
        client.post(
            f"/api/voc/{first['id']}/attachments",
            files={"file": ("캡처.png", b"\x89PNG2", "image/png")},
            headers=mine,
        )
        _move(client, admin_headers, first["id"], "accepted", "보겠습니다")

        response = client.post(
            "/api/voc/export", json={"ids": [second["id"], first["id"]]}, headers=admin_headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/zip")
        bundle = zipfile.ZipFile(io.BytesIO(response.content))
        names = bundle.namelist()

        folder = f"voc-{first['seq']:04d}-목록이-느려요-재료-시험"
        assert f"{folder}/item.json" in names
        # 같은 이름의 첨부 둘 — 덮어쓰지 않고 뒤엣것에 id 앞자리를 붙인다.
        files = sorted(one for one in names if one.startswith(f"{folder}/attachments/"))
        assert len(files) == 2 and f"{folder}/attachments/캡처.png" in files

        item = json.loads(bundle.read(f"{folder}/item.json"))
        assert item["title"] == first["title"]
        assert item["body"] == "목록이 느립니다"
        assert item["status"] == "accepted"
        assert [one["to_status"] for one in item["events"]] == ["open", "accepted"]
        # json 이 첨부를 상대경로로 가리키고, 그 경로가 zip 안에 실제로 있다.
        for one in item["attachments"]:
            assert f"{folder}/{one['path']}" in names
            assert bundle.read(f"{folder}/{one['path']}").startswith(b"\x89PNG")

        index = json.loads(bundle.read("index.json"))
        assert index["count"] == 2
        assert [one["seq"] for one in index["items"]] == [first["seq"], second["seq"]]
        assert index["items"][0]["attachments"] == 2

    def test_없는_건이_섞이면_막는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        import uuid

        mine = member_headers(client, db, workspace)
        item = _voc(client, mine)
        response = client.post(
            "/api/voc/export", json={"ids": [item["id"], str(uuid.uuid4())]}, headers=mine
        )
        assert response.status_code == 404
