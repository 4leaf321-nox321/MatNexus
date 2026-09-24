"""공지 — 폐쇄망의 소통 창구 하나(다른 하나 VOC 는 `test_voc.py`).

지키려는 것:
  - 초안은 발행 전까지 남에게 보이지 않는다 — 목록에도, 한 건 주소로도
  - 팝업은 읽으면 다시 뜨지 않는다
  - 게시판이다 — 쪽으로 나가고, 제목·내용으로 찾고, 안 읽은 것만 고른다(2026-09-24)
  - 안 읽은 수는 발행된 것만 세고, 「모두 읽음」 이 그 수를 0 으로 만든다
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
    assert client.get("/api/notices", headers=headers).json()["items"] == []
    # 주소를 알아도 못 연다 — 남에게는 없는 것과 같다.
    assert client.get(f"/api/notices/{notice_id}", headers=headers).status_code == 404
    assert client.get(f"/api/notices/{notice_id}", headers=admin_headers).status_code == 200

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin_headers
    )
    listed = client.get("/api/notices", headers=headers).json()["items"]
    assert [n["title"] for n in listed] == ["점검 안내"]


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
    first = client.get(f"/api/notices/{notice_id}", headers=admin_headers).json()[
        "published_at"
    ]

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": False}, headers=admin_headers
    )
    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin_headers
    )

    again = client.get(f"/api/notices/{notice_id}", headers=admin_headers).json()[
        "published_at"
    ]
    assert again == first


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
    assert client.get("/api/notices", headers=headers).json()["items"] == []
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


def test_게시판은_쪽으로_나가고_제목_내용으로_찾는다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """공지가 늘면 카드 더미에서는 찾을 길이 없었다. **최근에 알린 것이 위다.**"""
    for title, body in (
        ("1월 점검", "토요일 점검"),
        ("새 기능", "내보내기"),
        ("2월 점검", "일요일"),
    ):
        made = client.post(
            "/api/notices", json={"title": title, "body": body}, headers=admin_headers
        )
        assert made.status_code == 201, made.text

    page = client.get("/api/notices", params={"limit": 2}, headers=admin_headers).json()
    assert page["total"] == 3 and page["limit"] == 2 and len(page["items"]) == 2
    assert page["items"][0]["title"] == "2월 점검"  # 마지막에 알린 것이 위다
    rest = client.get(
        "/api/notices", params={"limit": 2, "offset": 2}, headers=admin_headers
    ).json()
    assert [one["title"] for one in rest["items"]] == ["1월 점검"]

    # 제목으로도, 내용으로도 찾는다.
    found = client.get("/api/notices", params={"q": "점검"}, headers=admin_headers).json()
    assert {one["title"] for one in found["items"]} == {"1월 점검", "2월 점검"}
    found = client.get("/api/notices", params={"q": "내보내기"}, headers=admin_headers).json()
    assert [one["title"] for one in found["items"]] == ["새 기능"]


def test_안_읽은_것만_고른다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    ids = [
        client.post(
            "/api/notices", json={"title": title, "body": "본문"}, headers=admin_headers
        ).json()["id"]
        for title in ("가", "나")
    ]
    headers = member_headers(client, db, workspace)
    client.post(f"/api/notices/{ids[0]}/read", headers=headers)

    unread = client.get("/api/notices", params={"unread": True}, headers=headers).json()
    assert [one["title"] for one in unread["items"]] == ["나"]
    listed = {
        one["title"]: one["is_read"]
        for one in client.get("/api/notices", headers=headers).json()["items"]
    }
    assert listed == {"가": True, "나": False}


def test_쓴_사람과_배포에_실려_온_안내를_가른다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """배포가 넣은 글(`seeds/notices`)은 쓴 사람이 없다 — 「알 수 없음」 이 아니라
    배포 안내다."""
    from app.modules.notices.models import Notice

    written = client.post(
        "/api/notices", json={"title": "직접 쓴 공지", "body": "본문"}, headers=admin_headers
    ).json()
    assert written["created_by"] == "시스템 관리자"
    assert written["from_release"] is False

    seeded = Notice(
        title="새로 생긴 것", body="- 물성", is_published=True, seed_key="2026-09-24-시험"
    )
    db.add(seeded)
    db.commit()
    one = client.get(f"/api/notices/{seeded.id}", headers=admin_headers).json()
    assert one["created_by"] is None and one["from_release"] is True


def test_안_읽은_수는_발행된_것만_센다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """사이드바의 수. **초안은 안 센다** — 관리자에게도 초안은 아직 아무에게도 안 알린 글이라
    「새 글」 이 아니다(목록의 「새 글」 표와 같다)."""
    ids = [
        client.post(
            "/api/notices", json={"title": title, "body": "본문"}, headers=admin_headers
        ).json()["id"]
        for title in ("가", "나", "다")
    ]
    client.post(
        "/api/notices",
        json={"title": "초안", "body": "본문", "is_published": False},
        headers=admin_headers,
    )
    headers = member_headers(client, db, workspace)
    count = client.get("/api/notices/unread-count", headers=headers)
    assert count.status_code == 200, count.text
    assert count.json() == {"unread": 3}

    client.post(f"/api/notices/{ids[0]}/read", headers=headers)
    assert client.get("/api/notices/unread-count", headers=headers).json() == {"unread": 2}
    # 관리자도 초안은 안 센다.
    assert client.get("/api/notices/unread-count", headers=admin_headers).json() == {
        "unread": 3
    }


def test_모두_읽음은_수를_0_으로_만들고_이미_읽은_것은_건너뛴다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """처음 들어온 사람에게는 쌓인 공지가 전부 새 글이다. 하나를 이미 읽었어도(다른 탭에서)
    겹친 짝 때문에 전부가 되돌려지면 안 된다."""
    from sqlalchemy import func, select

    from app.modules.notices.models import NoticeRead

    ids = [
        client.post(
            "/api/notices", json={"title": title, "body": "본문"}, headers=admin_headers
        ).json()["id"]
        for title in ("가", "나")
    ]
    headers = member_headers(client, db, workspace)
    client.post(f"/api/notices/{ids[0]}/read", headers=headers)

    done = client.post("/api/notices/read-all", headers=headers)
    assert done.status_code == 200, done.text
    assert done.json() == {"unread": 0}
    assert client.get("/api/notices/unread-count", headers=headers).json() == {"unread": 0}
    listed = client.get("/api/notices", headers=headers).json()["items"]
    assert all(one["is_read"] for one in listed)
    # 짝마다 한 줄 — 이미 읽은 것을 두 번 적지 않았다.
    rows = db.scalar(select(func.count()).select_from(NoticeRead))
    assert rows == 2

    # 남의 읽음은 건드리지 않는다.
    assert client.get("/api/notices/unread-count", headers=admin_headers).json() == {
        "unread": 2
    }
