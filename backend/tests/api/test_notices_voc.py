"""공지와 VOC — 폐쇄망의 유일한 소통 창구 둘.

지키려는 것:
  - 초안은 발행 전까지 남에게 보이지 않는다
  - 팝업은 읽으면 다시 뜨지 않는다
  - VOC 는 남의 제보가 서로 보이지 않는다
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace


def member_headers(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    user = User(
        email="hong",
        password_hash=security.hash_password("member-password-1"),
        display_name="홍길동",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": "hong", "password": "member-password-1"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_draft_notice_is_hidden_until_published(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/notices",
        json={"title": "점검 안내", "body": "토요일 점검", "is_published": False},
        headers=admin_headers,
    )
    assert created.status_code == 201
    notice_id = created.json()["id"]

    headers = member_headers(client, db, workspace)
    assert client.get("/api/notices", headers=headers).json() == []

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin_headers
    )
    assert [n["title"] for n in client.get("/api/notices", headers=headers).json()] == [
        "점검 안내"
    ]


def test_popup_disappears_after_reading(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    notice_id = client.post(
        "/api/notices",
        json={"title": "필독", "body": "중요 변경", "is_popup": True},
        headers=admin_headers,
    ).json()["id"]

    headers = member_headers(client, db, workspace)
    assert len(client.get("/api/notices/popup", headers=headers).json()) == 1

    assert client.post(f"/api/notices/{notice_id}/read", headers=headers).status_code == 204
    assert client.get("/api/notices/popup", headers=headers).json() == []


def test_publish_time_is_stamped_once(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """수정할 때마다 발행 시각을 갱신하면 "언제 알려졌는가"를 잃는다."""
    notice_id = client.post(
        "/api/notices", json={"title": "안내", "body": "내용"}, headers=admin_headers
    ).json()["id"]
    first = client.get("/api/notices", headers=admin_headers).json()[0]["published_at"]

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": False}, headers=admin_headers
    )
    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin_headers
    )

    again = client.get("/api/notices", headers=admin_headers).json()[0]["published_at"]
    assert again == first


def test_voc_is_private_between_users(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    created = client.post(
        "/api/voc",
        json={"title": "곡선이 안 보여요", "body": "인장 화면", "page_path": "/w/metal/tests"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["created_by"] == "홍길동"
    # 접수 당시 화면을 남긴다 — "그 화면에서 안 돼요" 를 재현하는 실마리다.
    assert created.json()["page_path"] == "/w/metal/tests"

    # 본인은 자기 것을 본다
    assert len(client.get("/api/voc", headers=headers).json()) == 1
    # 관리자는 전부 본다
    assert len(client.get("/api/voc", headers=admin_headers).json()) == 1


def test_admin_reply_sets_status(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = client.post(
        "/api/voc", json={"title": "요청", "body": "내용"}, headers=headers
    ).json()["id"]

    replied = client.post(
        f"/api/voc/{item_id}/reply",
        json={"reply": "다음 배포에 반영합니다.", "status": "resolved"},
        headers=admin_headers,
    )
    assert replied.status_code == 200
    assert replied.json()["status"] == "resolved"
    assert replied.json()["reply"] == "다음 배포에 반영합니다."


def test_member_cannot_reply(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = client.post(
        "/api/voc", json={"title": "요청", "body": "내용"}, headers=headers
    ).json()["id"]

    response = client.post(
        f"/api/voc/{item_id}/reply", json={"reply": "내가 답한다"}, headers=headers
    )
    assert response.status_code == 403


# --- 고치기와 지우기 -----------------------------------------------------------
#
# **낸 사람은 답변 전까지, 관리자는 언제나.** 답변이 달린 뒤에 본문이 바뀌면
# 답변이 딴 소리가 된다 — 읽는 사람은 관리자가 엉뚱한 답을 한 것으로 본다.


def _voc(client: TestClient, headers: dict[str, str], title: str = "느려요") -> str:
    made = client.post(
        "/api/voc", json={"title": title, "body": "목록이 느립니다"}, headers=headers
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def test_낸_사람이_자기_것을_고친다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = _voc(client, headers)

    fixed = client.patch(
        f"/api/voc/{item_id}", json={"title": "목록이 느려요"}, headers=headers
    )
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert body["title"] == "목록이 느려요"
    # **안 보낸 칸은 안 건드린다.** 제목만 고치는 요청이 본문을 지우면 안 된다.
    assert body["body"] == "목록이 느립니다"


def test_답변이_달리면_낸_사람은_못_고친다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = _voc(client, headers)
    client.post(
        f"/api/voc/{item_id}/reply",
        json={"reply": "고쳤습니다", "status": "resolved"},
        headers=admin_headers,
    )

    denied = client.patch(f"/api/voc/{item_id}", json={"title": "딴 얘기"}, headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "MNX-VOC-0004"

    # **관리자는 언제나 된다.** 답변을 단 사람이 오타를 고치는 자리다.
    allowed = client.patch(
        f"/api/voc/{item_id}", json={"title": "목록 지연"}, headers=admin_headers
    )
    assert allowed.status_code == 200


def test_남이_낸_것은_못_고치고_못_지운다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """목록에서도 안 보이지만, 거기서만 막으면 주소를 아는 사람이 고칠 수 있다."""
    item_id = _voc(client, admin_headers, title="관리자가 낸 것")
    headers = member_headers(client, db, workspace)

    assert (
        client.patch(f"/api/voc/{item_id}", json={"title": "x"}, headers=headers).json()[
            "error"
        ]["code"]
        == "MNX-VOC-0003"
    )
    assert client.delete(f"/api/voc/{item_id}", headers=headers).status_code == 403


def test_voc_를_지우면_목록에서_사라진다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = _voc(client, headers)

    assert client.delete(f"/api/voc/{item_id}", headers=headers).status_code == 204
    assert client.get("/api/voc", headers=headers).json() == []
    # 두 번 지우면 없는 것이다 — 화면이 새로고침 전에 한 번 더 누를 수 있다.
    assert client.delete(f"/api/voc/{item_id}", headers=headers).status_code == 404


def test_공지를_지우면_읽음_기록도_함께_간다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """`notice_reads` 가 CASCADE 다. 안 지워지면 지운 공지를 가리키는 행이 남는다."""
    from app.modules.notices.models import NoticeRead

    notice_id = client.post(
        "/api/notices",
        json={"title": "점검", "body": "토요일", "is_published": True, "is_popup": True},
        headers=admin_headers,
    ).json()["id"]
    headers = member_headers(client, db, workspace)
    client.post(f"/api/notices/{notice_id}/read", headers=headers)
    assert db.query(NoticeRead).count() == 1

    assert client.delete(f"/api/notices/{notice_id}", headers=admin_headers).status_code == 204
    assert client.get("/api/notices", headers=headers).json() == []
    db.expire_all()
    assert db.query(NoticeRead).count() == 0


def test_공지는_시스템_관리자만_지운다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    notice_id = client.post(
        "/api/notices",
        json={"title": "점검", "body": "토요일", "is_published": True},
        headers=admin_headers,
    ).json()["id"]
    headers = member_headers(client, db, workspace)

    assert client.delete(f"/api/notices/{notice_id}", headers=headers).status_code == 403
    assert client.delete(f"/api/notices/{notice_id}", headers=admin_headers).status_code == 204
