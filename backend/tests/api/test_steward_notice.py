"""자료 관리자에게 가는 말 — 확정 · 승인 요청과, AI 가 한 확정 · 채택(2026-10-15).

상태만 있던 자리다. 확정 대기 카드는 홈의 숫자로만, 승인 대기 값은 그 화면을 열어야 보였고,
AI 가 확인 없이 확정해도 감사 표를 열기 전에는 드러나지 않았다(ADR 0061 의 남은 위험).

무는 것:

    부탁이 간다         고칠 수 있는 사람이 부탁하면 자료 관리자의 수신함에 들어간다
    부탁은 상태가 아니다  카드는 초안 그대로 · 코멘트 한 줄 · 하루에 한 번
    아무나 못 한다      못 고치는 사람의 부탁은 막는다 — 누구의 뜻인지 모른다
    AI 가 하면 안다     MCP 로 확정 · 채택하면 알림이 간다, 화면에서 한 것은 안 간다
    받을 사람이 맞다     자료 관리자가 있으면 그 사람, 없으면 시스템 관리자
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import handlers, queue, worker
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.materials import declared
from app.modules.materials.models import Material
from app.modules.notifications import services as notification_services
from app.modules.notifications.models import NotificationRule
from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.modules.workspaces.models import Workspace, WorkspaceMember

PASSWORD = "Passw0rd!steward"
TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "tensile.strength", "options": {}},
]


def _user(db: Session, workspace: Workspace, email: str, **roles: bool) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name=email.split("@")[0],
        status="active",
        home_workspace_id=workspace.id,
        **roles,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.commit()
    return user


def _headers(client: TestClient, email: str) -> dict[str, str]:
    got = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


def drain(db: Session, limit: int = 50) -> None:
    handlers.load_all()
    done = 0
    while done < limit and worker.run_once(session=db):
        done += 1


def _rules(db: Session, user: User) -> None:
    """받으려면 규칙이 있어야 한다 — 배포 때 `ensure_rules` 가 하는 일."""
    queue.enqueue(db, kind="notifications.ensure_rules", payload={"user_id": str(user.id)})
    db.commit()
    drain(db)


def _inbox(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    got = client.get("/api/notifications", headers=headers)
    assert got.status_code == 200, got.text
    return list(got.json())


def modulus(**over: Any) -> dict[str, Any]:
    return {
        "item": "탄성계수",
        "points": [{"value": 200}],
        "input_unit": "GPa",
        "source": "literature",
        "reference": "ASM Handbook Vol.1 p.120",
        **over,
    }


@pytest.fixture
def alice(
    client: TestClient, db: Session, workspace: Workspace
) -> tuple[User, dict[str, str]]:
    """평범한 멤버 — 자기 자료를 고친다. 자료 관리자가 아니다."""
    user = _user(db, workspace, "alice@example.com")
    return user, _headers(client, "alice@example.com")


@pytest.fixture
def bob(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    """같은 부서의 다른 멤버 — 앨리스의 자료를 못 고친다(ADR 0035)."""
    _user(db, workspace, "bob@example.com")
    return _headers(client, "bob@example.com")


def _material(db: Session, owner: User, *rows: dict[str, Any]) -> Material:
    ensure_builtin_property_items(db)
    one = Material(
        record_name=f"SN_{uuid.uuid4().hex[:6]}",
        family="Metal",
        category="Steel",
        grade="SN",
        poisson_ratio=0.3,
        density_si=7850.0,
        registered_by_id=owner.id,
    )
    db.add(one)
    db.flush()
    one.declared_properties = declared.check(db, list(rows))
    db.commit()
    return one


def _card(client: TestClient, headers: dict[str, str], material: Material) -> dict[str, Any]:
    made = client.post(
        "/api/fitting/cards/declared",
        json={"material_id": str(material.id), "label": f"카드 {material.record_name}"},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _ask(
    client: TestClient, headers: dict[str, str], card_id: str, note: str | None = None
) -> Any:
    return client.post(
        f"/api/fitting/cards/{card_id}/request-publish", json={"note": note}, headers=headers
    )


class Test카드_확정_요청:
    def test_부탁하면_자료_관리자에게_가고_카드는_초안이다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        """자료 관리자가 없으면 **시스템 관리자**가 받는다 — 빈 목록은 답이 아니다."""
        _rules(db, admin)
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))

        asked = _ask(client, headers, card["id"], "해석에 다음 주 씁니다")
        assert asked.status_code == 200, asked.text
        assert asked.json()["notified"] == 1
        after = asked.json()["card"]
        assert after["status"] == "draft", "부탁은 상태가 아니다"
        (remark,) = after["remarks"]
        assert remark["kind"] == "publish_requested"
        assert remark["comment"] == "해석에 다음 주 씁니다"
        assert remark["created_by_name"] == "alice"

        drain(db)
        mine = [
            one
            for one in _inbox(client, admin_headers)
            if one["title"] == f"카드 확정 요청 — {card['code']} {card['label']}"
        ]
        assert mine, "자료 관리자의 수신함에 부탁이 없다"
        assert mine[0]["link"] == f"/materials/{card['material_id']}?tab=cards"
        assert "alice" in mine[0]["body"] and "다음 주" in mine[0]["body"]

    def test_하루에_한_번이다(
        self, client: TestClient, db: Session, alice: tuple[User, dict[str, str]]
    ) -> None:
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        assert _ask(client, headers, card["id"]).status_code == 200

        again = _ask(client, headers, card["id"])
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "MNX-FITTING-0048"
        got = client.get(f"/api/fitting/cards/{card['id']}", headers=headers).json()
        assert len(got["remarks"]) == 1, "막힌 부탁이 코멘트를 남기면 안 된다"

    def test_못_고치는_사람은_부탁하지_못한다(
        self,
        client: TestClient,
        db: Session,
        alice: tuple[User, dict[str, str]],
        bob: dict[str, str],
    ) -> None:
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))

        denied = _ask(client, bob, card["id"])
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "MNX-FITTING-0039"

    def test_초안만_부탁한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        published = client.post(
            f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers
        )
        assert published.status_code == 200, published.text

        late = _ask(client, headers, card["id"])
        assert late.status_code == 409
        assert late.json()["error"]["code"] == "MNX-FITTING-0047"

    def test_자기에게는_안_보낸다(
        self, client: TestClient, db: Session, admin: User, admin_headers: dict[str, str]
    ) -> None:
        """자료 관리자가 저 혼자면 0명 — 그 사실을 숨기지 않고 돌려준다."""
        card = _card(client, admin_headers, _material(db, admin, modulus()))
        asked = _ask(client, admin_headers, card["id"])
        assert asked.status_code == 200, asked.text
        assert asked.json()["notified"] == 0


class Test선언_값_승인_요청:
    def test_기다리는_값을_세어_알린다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        _rules(db, admin)
        owner, headers = alice
        material = _material(db, owner, modulus())

        asked = client.post(
            f"/api/materials/{material.id}/declared/request-approval",
            json={"note": "원문 p.120"},
            headers=headers,
        )
        assert asked.status_code == 200, asked.text
        assert asked.json() == {"pending": 1, "notified": 1}

        drain(db)
        mine = [
            one
            for one in _inbox(client, admin_headers)
            if one["title"] == f"선언 값 승인 요청 — {material.record_name} 1건"
        ]
        assert mine and mine[0]["link"] == "/materials/declared-review"
        assert "원문 p.120" in mine[0]["body"]

    def test_승인해도_안_오르는_값뿐이면_거절한다(
        self, client: TestClient, db: Session, alice: tuple[User, dict[str, str]]
    ) -> None:
        """규격 값은 승인해도 2 그대로다 — 「승인 대기 값」 화면과 같은 판정이다."""
        owner, headers = alice
        material = _material(db, owner, modulus(source="standard", reference="KS D 3512"))

        none = client.post(
            f"/api/materials/{material.id}/declared/request-approval",
            json={},
            headers=headers,
        )
        assert none.status_code == 422
        assert none.json()["error"]["code"] == "MNX-MATERIALS-0052"

    def test_못_고치는_사람은_부탁하지_못한다(
        self,
        client: TestClient,
        db: Session,
        alice: tuple[User, dict[str, str]],
        bob: dict[str, str],
    ) -> None:
        owner, _ = alice
        material = _material(db, owner, modulus())
        denied = client.post(
            f"/api/materials/{material.id}/declared/request-approval", json={}, headers=bob
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "MNX-MATERIALS-0051"


class Test받는_사람:
    def test_자료_관리자가_있으면_그_사람이_받는다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        workspace: Workspace,
        alice: tuple[User, dict[str, str]],
    ) -> None:
        steward = _user(db, workspace, "steward@example.com", is_data_manager=True)
        _rules(db, steward)
        _rules(db, admin)
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))

        asked = _ask(client, headers, card["id"])
        assert asked.json()["notified"] == 1
        drain(db)
        title = f"카드 확정 요청 — {card['code']} {card['label']}"
        steward_inbox = _inbox(client, _headers(client, "steward@example.com"))
        assert title in {one["title"] for one in steward_inbox}
        assert title not in {one["title"] for one in _inbox(client, admin_headers)}

    def test_규칙은_자료_관리자에게만_선다(
        self, db: Session, admin: User, alice: tuple[User, dict[str, str]]
    ) -> None:
        member, _ = alice
        assert {"review.requested", "ai.confirmed"} <= set(
            notification_services.wanted_kinds(db, admin)
        )
        assert "review.requested" not in notification_services.wanted_kinds(db, member)

    def test_자료_관리자로_세우면_규칙이_따라온다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        """**역할이 바뀌면 규칙을 다시 맞춘다.** 안 하면 새 자료 관리자는 부탁을 못 받는다 —
        배포 때 한 번 도는 `ensure_rules` 를 기다려야 한다."""
        member, _ = alice
        granted = client.post(
            f"/api/accounts/{member.id}/data-manager",
            json={"is_data_manager": True},
            headers=admin_headers,
        )
        assert granted.status_code == 200, granted.text
        drain(db)
        kinds = set(
            db.scalars(
                select(NotificationRule.event_kind).where(
                    NotificationRule.user_id == member.id
                )
            )
        )
        assert {"review.requested", "ai.confirmed"} <= kinds


def _named(card: dict[str, Any]) -> str:
    return f"{card['code']} {card['label']}"


def _remark(client: TestClient, headers: dict[str, str], card_id: str, text: str) -> Any:
    return client.post(
        f"/api/fitting/cards/{card_id}/remarks", json={"comment": text}, headers=headers
    )


class Test답이_간다:
    """부탁은 한 방향이었다 — 부탁한 사람은 확정됐는지 카드를 다시 열어 봐야 알았다
    (2026-10-16)."""

    def test_확정되면_부탁한_사람이_안다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        owner, headers = alice
        _rules(db, owner)
        card = _card(client, headers, _material(db, owner, modulus()))
        assert _ask(client, headers, card["id"]).status_code == 200

        done = client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        assert done.status_code == 200, done.text
        drain(db)
        mine = [
            one
            for one in _inbox(client, headers)
            if one["title"] == f"요청한 카드가 확정됐습니다 — {_named(card)}"
        ]
        assert mine and mine[0]["link"] == f"/materials/{card['material_id']}?tab=cards"

    def test_사용_중지돼도_안다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        owner, headers = alice
        _rules(db, owner)
        card = _card(client, headers, _material(db, owner, modulus()))
        _ask(client, headers, card["id"])

        client.post(f"/api/fitting/cards/{card['id']}/deprecate", headers=admin_headers)
        drain(db)
        titles = {one["title"] for one in _inbox(client, headers)}
        assert f"요청한 카드가 사용 중지됐습니다 — {_named(card)}" in titles

    def test_부탁하지_않았으면_안_간다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        """만든 사람이라도 부탁하지 않았으면 — 확정은 늘 일어나는 일이라 다 알리면 안
        읽힌다."""
        owner, headers = alice
        _rules(db, owner)
        card = _card(client, headers, _material(db, owner, modulus()))
        client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        drain(db)
        assert not [one for one in _inbox(client, headers) if "요청한 카드가" in one["title"]]


class Test코멘트:
    """카드에 「반려」 가 없어(D8) 확정하지 않는 사유를 남길 자리가 없었다(2026-10-16)."""

    def test_남기면_만든_사람과_부탁한_사람이_안다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
        bob: dict[str, str],
    ) -> None:
        owner, headers = alice
        _rules(db, owner)
        _rules(db, admin)
        card = _card(client, headers, _material(db, owner, modulus()))
        assert _ask(client, admin_headers, card["id"]).status_code == 200  # 관리자가 부탁

        said = _remark(client, bob, card["id"], "푸아송비 근거가 없습니다 — 보완 후 다시 요청")
        assert said.status_code == 201, said.text
        assert said.json()["kind"] == "comment"
        assert said.json()["created_by_name"] == "bob"
        got = client.get(f"/api/fitting/cards/{card['id']}", headers=headers).json()
        assert got["status"] == "draft", "코멘트는 카드를 고치지 않는다"
        assert [one["kind"] for one in got["remarks"]] == ["publish_requested", "comment"]

        drain(db)
        title = f"bob 님이 카드에 코멘트를 남겼습니다 — {_named(card)}"
        for inbox in (_inbox(client, headers), _inbox(client, admin_headers)):
            mine = [one for one in inbox if one["title"] == title]
            assert mine and "보완 후 다시 요청" in mine[0]["body"]

    def test_내_것만_지우고_자료_관리자는_누구_것이든(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
        bob: dict[str, str],
    ) -> None:
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        mine = _remark(client, headers, card["id"], "오타").json()
        path = f"/api/fitting/cards/{card['id']}/remarks"

        denied = client.delete(f"{path}/{mine['id']}", headers=bob)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "MNX-FITTING-0052"
        assert client.delete(f"{path}/{mine['id']}", headers=headers).status_code == 204

        theirs = _remark(client, bob, card["id"], "검토 의견").json()
        assert (
            client.delete(f"{path}/{theirs['id']}", headers=admin_headers).status_code == 204
        )
        got = client.get(f"/api/fitting/cards/{card['id']}", headers=headers).json()
        assert got["remarks"] == []

    def test_서버가_남긴_기록은_못_지운다(
        self, client: TestClient, db: Session, alice: tuple[User, dict[str, str]]
    ) -> None:
        """확정 요청은 하루 한 번을 막는 근거다 — 지우면 그 막기가 풀린다."""
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        asked = _ask(client, headers, card["id"]).json()
        (remark,) = asked["card"]["remarks"]
        kept = client.delete(
            f"/api/fitting/cards/{card['id']}/remarks/{remark['id']}", headers=headers
        )
        assert kept.status_code == 409
        assert kept.json()["error"]["code"] == "MNX-FITTING-0051"

    def test_빈_코멘트는_거절한다(
        self, client: TestClient, db: Session, alice: tuple[User, dict[str, str]]
    ) -> None:
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        empty = _remark(client, headers, card["id"], "   ")
        assert empty.status_code == 422
        assert empty.json()["error"]["code"] == "MNX-FITTING-0049"


@pytest.fixture
def run_id(client: TestClient, admin_headers: dict[str, str], db: Session) -> str:
    """파싱까지 끝난 인장 시험 하나."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SNAD", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


class TestAI_가_하면_안다:
    """ADR 0061 의 남은 위험 — 서버는 AI 의 확정을 못 막는다. 막지 못하면 **바로 안다**.

    토큰 주인에게도 간다(제 AI 가 한 일이다). 화면에서 한 것은 안 간다 — 늘 오는 알림은
    안 읽힌다.
    """

    def test_AI_가_확정하면_알린다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        _rules(db, admin)
        owner, headers = alice
        by_ai = _card(client, headers, _material(db, owner, modulus()))
        by_hand = _card(client, headers, _material(db, owner, modulus()))

        done = client.post(
            f"/api/fitting/cards/{by_ai['id']}/publish",
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert done.status_code == 200, done.text
        client.post(f"/api/fitting/cards/{by_hand['id']}/publish", headers=admin_headers)
        drain(db)

        titles = {one["title"] for one in _inbox(client, admin_headers)}
        assert f"AI(MCP) 가 카드를 확정했습니다 — {by_ai['code']} {by_ai['label']}" in titles
        assert not [title for title in titles if by_hand["label"] in title]

    def test_AI_가_채택하면_한_번_알린다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        run_id: str,
    ) -> None:
        _rules(db, admin)
        result = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        )
        assert result.status_code == 201, result.text
        took = client.post(
            "/api/processing/adopt-many",
            json={"items": [{"test_run_id": run_id, "result_id": result.json()["id"]}]},
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert took.json()["changed"] == 1
        drain(db)

        mine = [
            one
            for one in _inbox(client, admin_headers)
            if one["title"] == "AI(MCP) 가 처리 결과 채택을 1건 바꿨습니다"
        ]
        assert len(mine) == 1
        assert mine[0]["link"] == f"/test-runs/{run_id}"

    def test_화면에서_한_채택은_알리지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        run_id: str,
    ) -> None:
        _rules(db, admin)
        result = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        ).json()
        took = client.post(
            "/api/processing/adopt-many",
            json={"items": [{"test_run_id": run_id, "result_id": result["id"]}]},
            headers=admin_headers,
        )
        assert took.json()["changed"] == 1
        drain(db)
        assert not [one for one in _inbox(client, admin_headers) if "채택을" in one["title"]]


def _audits(client: TestClient, headers: dict[str, str], action: str) -> list[dict[str, Any]]:
    got = client.get("/api/audit", params={"action": action, "limit": 200}, headers=headers)
    assert got.status_code == 200, got.text
    return list(got.json())


class TestAI_가_부탁하고_말을_남기면:
    """AI(MCP)도 코멘트 · 확정 요청 · 승인 요청을 한다(2026-10-16). 값은 안 바뀌어도 사람에게
    알림이 간다 — **토큰 주인의 이름만 보이면 그 사람이 직접 쓴 말로 읽힌다.** 경유를 카드와
    감사에 남기고, 화면에서 한 것은 전처럼 아무것도 더하지 않는다."""

    def test_코멘트에_경유가_붙고_감사에_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        by_ai = _remark(client, {**headers, "X-Client": "mcp"}, card["id"], "AI 의 검토 의견")
        by_hand = _remark(client, headers, card["id"], "사람의 검토 의견")
        assert by_ai.json()["via"] == "AI(MCP)"
        assert by_hand.json()["via"] is None

        got = client.get(f"/api/fitting/cards/{card['id']}", headers=headers).json()
        assert [one["via"] for one in got["remarks"]] == ["AI(MCP)", None]
        mine = [
            one
            for one in _audits(client, admin_headers, "card.remarked_by_client")
            if one["target_id"] == card["id"]
        ]
        assert len(mine) == 1, "화면에서 남긴 코멘트는 감사에 안 남는다"
        assert mine[0]["changes"]["comment"] == "AI 의 검토 의견"

    def test_확정_요청에_경유가_붙고_감사에_남는다(
        self,
        client: TestClient,
        db: Session,
        admin: User,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        _rules(db, admin)
        owner, headers = alice
        card = _card(client, headers, _material(db, owner, modulus()))
        asked = _ask(client, {**headers, "X-Client": "mcp"}, card["id"], "해석 일정")
        assert asked.status_code == 200, asked.text
        (remark,) = asked.json()["card"]["remarks"]
        assert remark["via"] == "AI(MCP)"
        mine = [
            one
            for one in _audits(client, admin_headers, "card.publish_requested_by_client")
            if one["target_id"] == card["id"]
        ]
        assert mine and mine[0]["changes"]["note"] == "해석 일정"

        drain(db)
        title = f"카드 확정 요청 — {_named(card)}"
        found = [one for one in _inbox(client, admin_headers) if one["title"] == title]
        assert found and "AI(MCP) 경유" in found[0]["body"]

    def test_승인_요청이_감사에_남는다_화면은_안_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        alice: tuple[User, dict[str, str]],
    ) -> None:
        owner, headers = alice
        by_ai = _material(db, owner, modulus())
        by_hand = _material(db, owner, modulus())
        for material, extra in ((by_ai, {"X-Client": "mcp"}), (by_hand, {})):
            sent = client.post(
                f"/api/materials/{material.id}/declared/request-approval",
                json={},
                headers={**headers, **extra},
            )
            assert sent.status_code == 200, sent.text
        targets = {
            one["target_id"]
            for one in _audits(client, admin_headers, "declared.approval_requested_by_client")
        }
        assert str(by_ai.id) in targets
        assert str(by_hand.id) not in targets
