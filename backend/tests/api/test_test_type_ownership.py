"""시험 종류의 권한 — **문을 안전하게 열었는가**(ADR 0006 · ADR 0035 3단계).

왜 열었나. 형식 프로파일을 부서 소유로 바꾼 순간 막다른 길이 생겼다. 부서
관리자가 새 장비를 붙이려면 시험 종류가 먼저 있어야 하는데 그것을 만들 권한이
없었다. 그런데 **새 장비란 대개 없는 종류를 재는 장비다.** 화면에서 열 20개를
다 매핑한 뒤 저장 순간 403 을 받는 길이었다.

무엇이 위험한가. 채널 키는 표시용 라벨이 아니라 **Parquet 의 컬럼 이름**이고,
곡선 비교·통계·내보내기가 전부 그 이름으로 열을 찾는다. A부서가 `stress` 를
Pa 로, B부서가 같은 이름을 MPa 로 정의하면 두 부서 곡선을 겹쳐 그린 순간
10⁶ 배 어긋난 그림이 나오는데 **축 이름이 같아서 아무도 이상하다고 느끼지
못한다.** 그래서 이름의 뜻을 강제하는 검사가 이 파일의 절반이다.

**3단계에서 문을 끝까지 열었다**(ADR 0035). 만들기는 누구나, 고치기는 등록자 ·
편집을 받은 부서 · 자료 관리자다 — 부서 관리자라는 자리는 정의를 고치지 않는다. 그래서
위험을 막는 것은 이제 **사람이 아니라 검사**다(채널 이름의 뜻).

정의 편집 자체(무엇을 잠그는가)는 `test_test_types.py` 가 본다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.workspaces.models import Workspace, WorkspaceMember

RIG: dict[str, Any] = {
    "key": "dept_rig",
    "label": "사업부 장비",
    "abbr": "RIG",
    "description": None,
    "parser_key": None,
    "channels": [
        {"key": "displacement", "label": "변위", "dimension": "length", "si_unit": "m"}
    ],
    "conditions": [],
}


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "member-password-1"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _add_user(db: Session, workspace: Workspace, email: str, role: str) -> None:
    user = User(
        email=email,
        password_hash=security.hash_password("member-password-1"),
        display_name=email,
        status="active",
        # 소속 부서 — 가입 승인이 멤버십과 함께 채운다. 정의의 등록 부서가 이것이다.
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    db.commit()


@pytest.fixture
def manager(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    """부서 관리자. **시스템 관리자가 아니다** — 그 구분이 이 파일의 전부다."""
    _add_user(db, workspace, "type-lead", "manager")
    return _login(client, "type-lead")


@pytest.fixture
def plain_member(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    _add_user(db, workspace, "type-worker", "member")
    return _login(client, "type-worker")


def _payload(**overrides: Any) -> dict[str, Any]:
    return {**RIG, **overrides}


class Test누가만드는가:
    def test_평범한_멤버도_만들고_등록자가_된다(
        self, client: TestClient, plain_member: dict[str, str], workspace: Workspace
    ) -> None:
        """**이 하나가 없으면 3단계의 이유가 사라진다.** 전에는 부서 관리자만 만들어서,
        새 장비를 붙이는 사람이 관리자를 기다렸다. 등록 부서는 안 보내면 내 소속이다."""
        response = client.post("/api/test-types", json=_payload(), headers=plain_member)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["owner_workspace_slug"] == workspace.slug
        assert "is_global" not in body
        assert body["access"]["registrant"] == "type-worker"
        assert body["access"]["can_edit"] is True

    def test_부서_관리자도_남의_정의는_못_고친다(
        self,
        client: TestClient,
        manager: dict[str, str],
        plain_member: dict[str, str],
    ) -> None:
        """부서 관리자는 정의를 고치는 자리가 아니다(ADR 0035 D5). 등록자가 부서에 편집을
        주면 그때 고친다 — 막을 때는 누구에게 물을지 이름으로."""
        made = client.post("/api/test-types", json=_payload(), headers=plain_member)
        assert made.status_code == 201, made.text
        body = {k: v for k, v in RIG.items() if k != "key"}
        body["expected_revision"] = made.json()["revision"]
        blocked = client.put("/api/test-types/dept_rig", json=body, headers=manager)
        assert blocked.status_code == 403, blocked.text
        assert "등록자 type-worker" in blocked.json()["error"]["message"]

    def test_부서_없이_올리는_것은_자료_관리자만(
        self,
        client: TestClient,
        manager: dict[str, str],
        admin_headers: dict[str, str],
    ) -> None:
        """칸을 **비워 보낸 것**만 부서 없이다 — 안 보낸 것은 내 소속이다(AGENTS.md)."""
        blocked = client.post(
            "/api/test-types", json=_payload(owner_workspace_slug=None), headers=manager
        )
        assert blocked.status_code == 403, blocked.text
        assert "자료 관리자만" in blocked.json()["error"]["message"]

        allowed = client.post(
            "/api/test-types", json=_payload(owner_workspace_slug=None), headers=admin_headers
        )
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["owner_workspace_slug"] is None

    def test_기본_종류는_부서_관리자가_못_고친다(
        self, client: TestClient, manager: dict[str, str], db: Session
    ) -> None:
        ensure_builtin_test_types(db)
        payload = {k: v for k, v in RIG.items() if k != "key"}
        # **권한 검사가 리비전 검사보다 앞이다.** 못 고치는 사람에게 "먼저
        # 새로고침하세요" 라고 말하면 길을 잘못 알려 주는 것이다.
        payload["expected_revision"] = 1
        response = client.put("/api/test-types/tensile", json=payload, headers=manager)
        assert response.status_code == 403, response.text
        # 이유가 없으면 "권한 없음" 은 벽이다. 누구에게 물을지를 말해야 한다 — 기본
        # 종류는 등록자가 없으니 자료 관리자다.
        assert "자료 관리자" in response.json()["error"]["message"]

    def test_기본_종류를_부서_관리자가_못_지운다(
        self, client: TestClient, manager: dict[str, str], db: Session
    ) -> None:
        ensure_builtin_test_types(db)
        response = client.delete("/api/test-types/tensile", headers=manager)
        assert response.status_code == 403, response.text


class Test채널이름은전사자산:
    """**같은 이름은 같은 것을 뜻해야 한다.** 문을 여는 것을 안전하게 만드는 검사."""

    def test_차원이_다르면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        ensure_builtin_test_types(db)
        response = client.post(
            "/api/test-types",
            json=_payload(
                key="odd_rig",
                channels=[
                    {"key": "force", "label": "하중", "dimension": "length", "si_unit": "m"}
                ],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        message = response.json()["error"]["message"]
        assert "force" in message
        # **어디서 쓰고 있는지**를 말해 줘야 사람이 판단한다. "충돌합니다" 만으로는
        # 자기 정의를 고쳐야 하는지 상대에게 물어야 하는지 알 수 없다.
        assert "인장" in message

    def test_새_이름은_막지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        # 새 물성을 재는 것이 새 장비를 붙이는 일이다. 그것까지 막으면 문을 연
        # 의미가 없다 — 막는 것은 *같은 이름으로 다른 것을 뜻하는* 경우뿐이다.
        ensure_builtin_test_types(db)
        response = client.post(
            "/api/test-types",
            json=_payload(
                key="new_rig",
                channels=[
                    {
                        "key": "storage_modulus",
                        "label": "저장탄성률",
                        "dimension": "stress",
                        "si_unit": "Pa",
                    }
                ],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text

    def test_같은_뜻이면_같은_이름을_쓴다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        # 공유가 정상이다. 인장의 `force`(N) 를 새 종류가 그대로 쓰는 것은
        # **권장되는 일**이고, 그래야 두 종류의 곡선을 겹쳐 볼 수 있다.
        ensure_builtin_test_types(db)
        response = client.post(
            "/api/test-types",
            json=_payload(
                key="shared_rig",
                channels=[
                    {"key": "force", "label": "하중", "dimension": "force", "si_unit": "N"}
                ],
            ),
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text

    def test_자기_채널은_충돌로_안_센다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        # 만들고 나서 라벨만 고쳐 저장하는 것이 막히면 편집이 불가능해진다.
        created = client.post(
            "/api/test-types", json=_payload(key="edit_rig"), headers=admin_headers
        )
        assert created.status_code == 201, created.text
        payload = {k: v for k, v in RIG.items() if k != "key"}
        payload["channels"] = [
            {
                "key": "displacement",
                "label": "변위(수정)",
                "dimension": "length",
                "si_unit": "m",
            }
        ]
        shown = client.get("/api/test-types", headers=admin_headers).json()
        body = dict(payload)
        body["expected_revision"] = next(item for item in shown if item["key"] == "edit_rig")[
            "revision"
        ]
        again = client.put("/api/test-types/edit_rig", json=body, headers=admin_headers)
        assert again.status_code == 200, again.text


class Test가시범위:
    def test_키가_겹치면_누가_갖고_있는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        # 두 부서가 같은 시험을 하면 종류를 둘로 만들 것이 아니라 하나를 같이
        # 써야 한다. "이미 있습니다" 만으로는 그 판단을 할 수 없다.
        ensure_builtin_test_types(db)
        payload = {k: v for k, v in RIG.items() if k != "key"}
        response = client.post(
            "/api/test-types", json={**payload, "key": "tensile"}, headers=admin_headers
        )
        assert response.status_code == 409, response.text
        assert "인장" in response.json()["error"]["message"]

    def test_남의_부서_종류도_보인다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        plain_member: dict[str, str],
        db: Session,
    ) -> None:
        ensure_builtin_test_types(db)
        db.add(Workspace(slug="other-div", name="다른 사업부"))
        db.commit()
        created = client.post(
            "/api/test-types",
            json=_payload(key="other_rig", owner_workspace_slug="other-div"),
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text

        keys = {
            row["key"] for row in client.get("/api/test-types", headers=plain_member).json()
        }
        # **보기는 전원이다**(ADR 0035). 전에는 남의 부서 종류가 안 보여서, 시험은
        # 보이는데 그 시험을 해석할 정의는 없는 비대칭이 생겼다 — 다른 시스템이 물성을
        # 받아 가다 「정의가 없다」 로 막혔다(2026-09-24).
        assert {"other_rig", "tensile"} <= keys
