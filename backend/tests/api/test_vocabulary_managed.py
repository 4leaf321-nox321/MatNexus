"""새 기준정보 값을 **누가 세우나** — `managed` 축(ADR 0032).

## 왜 층이 아니라 용어인가

「재료는 관리자만」 으로 층을 자르면 새 로트 하나 받을 때마다 관리자를 부른다. 위험한
것은 층이 아니라 **기준정보가 새로 생기는 것**이다 — `SECC` 를 `secc`·`SECC강판` 으로
적으면 재료가 셋으로 갈리고 그 뒤의 검색·통계·카드가 따라 갈린다. 되돌리려면 사람이
병합해야 한다.

그래서 문은 **새 값에만** 단다:

    기존 등급으로 재료 만들기     누구나 (같은 등급 다른 두께는 흔한 일이다)
    새 등급을 세우기              자료 관리자 (ADR 0035 3단계 — 전에는 부서 관리자)
    로트·별칭·메모                누구나 (용어가 아니다 — 그냥 글자 칸)
    씨앗·이관·커넥터              안 막는다 (사람이 아닌 경로)
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.materials.models import Material
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.models import Vocabulary
from app.modules.workspaces.models import Workspace, WorkspaceMember

PASSWORD = "Passw0rd!vocab"


def _member(db: Session, workspace: Workspace, *, email: str, role: str) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name=email,
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    db.commit()
    return user


def _headers(client: TestClient, email: str) -> dict[str, str]:
    got = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


def _create(client: TestClient, headers: dict[str, str], **over: Any) -> Any:
    body = {"family": "Metal", "category": "Steel", "grade": "SECC", **over}
    return client.post("/api/materials", json=body, headers=headers)


@pytest.fixture
def seeded(client: TestClient, db: Session, admin_headers: dict[str, str]) -> None:
    """`Metal/Steel/SECC` 를 한 번 만들어 그 용어들을 존재하게 한다(관리자로)."""
    made = _create(client, admin_headers, details="SEED")
    assert made.status_code == 201, made.text


class Test새_값은_자료_관리자만:
    def test_이미_있는_등급이면_누구나_만든다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
        seeded: None,
    ) -> None:
        """**같은 등급 다른 두께는 흔한 일이다.** 여기를 막으면 현장이 선다."""
        _member(db, workspace, email="member-a", role="member")
        got = _create(client, _headers(client, "member-a"), spec_thickness=0.8)
        assert got.status_code == 201, got.text

    def test_새_등급은_막고_비슷한_값을_준다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
        seeded: None,
    ) -> None:
        """갈림은 대개 오타에서 난다 — 비슷한 것을 보여 주면 그 자리에서 끝난다."""
        _member(db, workspace, email="member-b", role="member")
        got = _create(client, _headers(client, "member-b"), grade="SECC강판")
        assert got.status_code == 403, got.text
        body = got.json()["error"]
        assert body["code"] == "MNX-VOCABULARY-0011"
        assert "자료 관리자" in body["message"]
        assert "SECC" in body["details"]["similar"]
        # **누구에게 부탁할지 이름으로** — 자료 관리자가 없으면 시스템 관리자를 댄다.
        assert body["details"]["data_managers"]
        # 막혔으면 **아무것도 안 생긴다** — 반쯤 만든 재료가 남으면 더 나쁘다.
        assert db.scalar(select(Material).where(Material.grade == "SECC강판")) is None

    def test_자료_관리자는_새_등급을_세우고_부서_관리자는_못_세운다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
        seeded: None,
    ) -> None:
        """부서 관리자라는 자리는 고칠 권한을 갖지 않는다(ADR 0035 D5). 새 용어는 검토의
        뜻이 있는 일이라 카드 확정과 같은 자리 — 자료 관리자다."""
        _member(db, workspace, email="manager-a", role="manager")
        blocked = _create(client, _headers(client, "manager-a"), grade="DP980")
        assert blocked.status_code == 403, blocked.text

        steward = _member(db, workspace, email="steward-a", role="member")
        steward.is_data_manager = True
        db.commit()
        got = _create(client, _headers(client, "steward-a"), grade="DP980")
        assert got.status_code == 201, got.text
        assert got.json()["grade"] == "DP980"

    def test_로트는_용어가_아니라_아무나_적는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
        seeded: None,
    ) -> None:
        """시료의 로트는 매번 새것이다 — 막으면 아무 일도 못 한다. 업체는 용어다."""
        material = _create(client, admin_headers, details="LOT").json()
        headers = _headers(
            client, _member(db, workspace, email="member-c", role="member").email
        )
        made = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "LOT-2026-09-21"},
            headers=headers,
        )
        assert made.status_code == 201, made.text
        blocked = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "LOT-2", "manufacturer": "새로운제철"},
            headers=headers,
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["details"]["axis"] == "manufacturer"

    def test_사람이_아닌_경로는_안_막는다(self, db: Session) -> None:
        """씨앗·이관·커넥터 자동 등록은 `created_by_id` 가 없다. 거기서 막으면 배포가
        멈추거나 장비 파일이 조용히 쌓인다 — 이 문이 막으려던 것이 아니다."""
        grade = db.scalar(select(Vocabulary).where(Vocabulary.slug == "grade"))
        assert grade is not None and grade.entry_policy == "managed"
        term = vocabulary_services.resolve_or_create(
            db, grade, "이관해온등급", created_by_id=None
        )
        assert term is not None and term.value == "이관해온등급"


def test_정책은_코드가_정본이다(db: Session) -> None:
    """이미 깔린 서버는 옛 정책(`open`)을 들고 있다 — 씨앗 맞추기가 코드 쪽으로 돌려놔야
    운영에서도 문이 선다."""
    from app.modules.vocabulary.definitions import ensure_builtin_vocabularies

    grade = db.scalar(select(Vocabulary).where(Vocabulary.slug == "grade"))
    assert grade is not None
    grade.entry_policy = "open"
    db.flush()
    ensure_builtin_vocabularies(db)
    db.flush()
    assert grade.entry_policy == "managed"
