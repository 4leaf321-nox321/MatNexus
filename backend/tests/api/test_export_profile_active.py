"""해석용 물성 정의 **켜기 · 끄기**(2026-10-02).

정의판(기본 형식의 비상용 사본, ADR 0038 · 0047)은 「코드판을 사용 중단하고 정의판을 켜서 고쳐
쓴다」 가 설계였는데, **화면에 켜는 단추가 없었다** — 저장(PUT)이 켜짐을 통째로 받을 뿐이었고,
그나마 안 보내면 켜짐으로 덮어써서 꺼 둔 정의판이 다른 길(MCP)의 저장 한 번에 조용히 켜졌다.

    켜기 · 끄기   고칠 수 있는 사람이 전용 길로 — 정의는 안 건드리고, 감사에 남는다
    짝 알기       정의판이면 어느 코드판의 짝인지 · 그 코드판이 사용 중단됐는지
                  (화면이 켜기 전에 경고하는 근거)
    안 보낸 것    저장이 켜짐을 안 보내면 그대로 둔다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.auth import security
from app.modules.fitting.models import ExportProfile
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit

PASSWORD = "Passw0rd!toggle"

DEFINITION: dict[str, Any] = {
    "label": "LS-DYNA (탄소성) · 정의",
    "extension": "k",
    "describe": "정의판.",
    "needs": [{"block": "elastic", "values": ["density"]}],
    "lines": [{"text": "$ {name}"}],
}


def _twin(db: Session, *, active: bool = False) -> ExportProfile:
    """기본 형식 `dyna` 의 정의판 — 배포가 넣는 모양(꺼짐 · 등록자 없음)."""
    row = ExportProfile(
        key="dyna_def",
        label=str(DEFINITION["label"]),
        definition=DEFINITION,
        is_active=active,
    )
    db.add(row)
    db.commit()
    return row


def _member(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    user = User(
        email="member@example.com",
        password_hash=security.hash_password(PASSWORD),
        display_name="member",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.commit()
    got = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


def _row(client: TestClient, headers: dict[str, str], key: str) -> dict[str, Any]:
    listed = client.get("/api/fitting/export-profiles", headers=headers)
    assert listed.status_code == 200, listed.text
    rows: dict[str, dict[str, Any]] = {one["key"]: one for one in listed.json()}
    return rows[key]


def test_정의판은_짝인_코드판과_그_사용_중단_여부를_안다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    _twin(db)

    before = _row(client, admin_headers, "dyna_def")
    assert before["twin_of"] == "dyna"
    assert before["twin_held"] is False

    held = client.put(
        "/api/fitting/builtin-formats/dyna/hold",
        json={"reason": "MAT_024 칸이 밀렸다"},
        headers=admin_headers,
    )
    assert held.status_code == 200, held.text

    assert _row(client, admin_headers, "dyna_def")["twin_held"] is True


def test_켜고_끄면_메뉴에_서고_빠지며_감사에_남는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    row = _twin(db)

    on = client.post(
        "/api/fitting/export-profiles/dyna_def/active",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert on.status_code == 200, on.text
    assert on.json()["is_active"] is True
    assert on.json()["definition"] == DEFINITION  # 정의는 안 건드린다

    off = client.post(
        "/api/fitting/export-profiles/dyna_def/active",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert off.json()["is_active"] is False

    db.expire_all()
    actions = list(
        db.scalars(
            select(AuditEntry.action)
            .where(AuditEntry.target_id == row.id)
            .order_by(AuditEntry.created_at)
        )
    )
    assert actions == [audit.EXPORT_PROFILE_ACTIVATED, audit.EXPORT_PROFILE_DEACTIVATED]


def test_정의판은_자료_관리자만_켠다_등록자가_없다(
    client: TestClient, db: Session, workspace: Workspace
) -> None:
    _twin(db)

    refused = client.post(
        "/api/fitting/export-profiles/dyna_def/active",
        json={"is_active": True},
        headers=_member(client, db, workspace),
    )

    assert refused.status_code == 403, refused.text


def test_저장이_켜짐을_안_보내면_그대로_둔다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """전에는 안 보내면 켜짐으로 덮어썼다 — 꺼 둔 정의판이 고치러 온 저장에 조용히 켜졌다."""
    _twin(db, active=False)

    saved = client.put(
        "/api/fitting/export-profiles/dyna_def",
        json={"label": "LS-DYNA (탄소성) · 정의 · 고침", "definition": DEFINITION},
        headers=admin_headers,
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["is_active"] is False
    assert saved.json()["label"].endswith("고침")


def test_없는_정의는_404(client: TestClient, admin_headers: dict[str, str]) -> None:
    got = client.post(
        "/api/fitting/export-profiles/nope/active",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert got.status_code == 404
