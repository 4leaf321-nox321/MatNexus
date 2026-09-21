"""카드 항목란을 **화면에서** 만든다 (ADR 0033).

새 물성 갈래를 카드에 싣고 덱까지 보내려면 조각이 셋인데(항목란 · 채우는 계산 ·
덱에 쓰는 규칙), 둘은 이미 화면에서 됐고 **가운데만 코드**였다. 그래서 r값 하나
싣자는 요구에도 배포가 돌았다.

여기서 지키는 것:

    만든 즉시 레지스트리에 얹힌다      재시작을 기다리면 「배포 없이」 가 반만 참이다
    내장은 못 덮는다                   덮으면 계산이 조용히 다른 칸을 본다
    시스템 관리자만                    덱 구조까지 흘러가고 전 부서가 공유한다
    카드가 담고 있으면 못 지운다        지우면 그 값이 덱에서 조용히 빠진다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace, WorkspaceMember
from matcore import cards

PASSWORD = "Passw0rd!block"


def _body(**over: Any) -> dict[str, Any]:
    return {
        "key": "anisotropy",
        "label": "이방성",
        "help": "세 방향 인장에서 나오는 r값들.",
        "produces": [
            {"key": "r_bar", "label": "평균 이방성", "si_unit": "1"},
            {"key": "delta_r", "label": "면내 이방성", "si_unit": "1"},
        ],
        "measured": True,
        **over,
    }


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    """시험이 얹은 항목란을 남기지 않는다 — 레지스트리는 프로세스에 하나뿐이라
    다음 시험이 그것을 물려받으면 「내 것이 아닌 블록」 이 목록에 낀다."""
    yield
    cards.load_builtin()
    for key in cards.installed():
        cards.uninstall(key)


def _member(db: Session, workspace: Workspace, *, email: str) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name=email,
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
    db.commit()
    return user


def _headers(client: TestClient, email: str) -> dict[str, str]:
    got = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


class Test만들기:
    def test_만들면_카드_화면이_바로_안다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**재시작을 기다리지 않는다.** 저장과 얹기가 같은 요청 안에서 끝나야
        「배포 없이」 가 참이 된다."""
        made = client.post(
            "/api/fitting/block-definitions", json=_body(), headers=admin_headers
        )
        assert made.status_code == 201, made.text
        assert made.json()["installed"] is True

        listed = client.get("/api/fitting/blocks", headers=admin_headers)
        assert listed.status_code == 200
        shown = {one["key"]: one for one in listed.json()}
        assert "anisotropy" in shown
        assert [one["key"] for one in shown["anisotropy"]["produces"]] == ["r_bar", "delta_r"]
        # 내장은 그대로 있다 — 표는 **추가만** 한다.
        assert "elastic" in shown

    def test_내장_키는_못_덮는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """덮게 두면 그 물성을 내는 계산이 조용히 다른 칸을 보고, 그 사실은 덱을
        열어 보기 전까지 안 드러난다."""
        got = client.post(
            "/api/fitting/block-definitions", json=_body(key="elastic"), headers=admin_headers
        )
        assert got.status_code == 409, got.text
        assert got.json()["error"]["code"] == "MNX-CARDBLOCK-0005"

    def test_점이_든_키는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """덱 정의가 값을 `블록.슬롯` 으로 가리키고 그 해석이 **첫 점 기준**이다 —
        점이 든 키는 가리킬 수가 없다."""
        got = client.post(
            "/api/fitting/block-definitions",
            json=_body(key="my.block"),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text

    def test_단위표에_없는_단위는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.post(
            "/api/fitting/block-definitions",
            json=_body(produces=[{"key": "r_bar", "label": "평균", "si_unit": "개"}]),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-CARDBLOCK-0003"

    def test_담을_것이_없으면_안_만든다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.post(
            "/api/fitting/block-definitions",
            json=_body(produces=[], rows=[]),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-CARDBLOCK-0006"

    def test_없는_시험_종류를_가리키면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """준비도가 「이 시험을 하면 생긴다」 로 없는 시험을 가리키게 두지 않는다."""
        got = client.post(
            "/api/fitting/block-definitions",
            json=_body(from_tests=["없는시험"]),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-CARDBLOCK-0007"

    def test_부서_관리자는_못_만든다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        """기준정보 새 값은 부서 관리자지만(ADR 0032) 항목란은 다르다 — 덱 구조까지
        흘러가고 전 부서가 공유한다."""
        _member(db, workspace, email="manager-block")
        got = client.post(
            "/api/fitting/block-definitions",
            json=_body(),
            headers=_headers(client, "manager-block"),
        )
        assert got.status_code == 403, got.text


class Test고치기와_지우기:
    def test_담기는_모양이_바뀌면_판이_오른다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = client.post(
            "/api/fitting/block-definitions", json=_body(), headers=admin_headers
        ).json()
        assert made["version"] == 1

        renamed = client.patch(
            f"/api/fitting/block-definitions/{made['id']}",
            json={"label": "이방성(판재)"},
            headers=admin_headers,
        )
        # 이름은 판이 아니다 — 라벨 하나 바꿨다고 리비전이 찍히면 안 된다.
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["version"] == 1

        changed = client.patch(
            f"/api/fitting/block-definitions/{made['id']}",
            json={"produces": [{"key": "r_bar", "label": "평균 이방성", "si_unit": "1"}]},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["version"] == 2

    def test_끄면_목록에서_빠진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**옛 카드의 값은 그대로 남는다** — 선언만 빠진다."""
        made = client.post(
            "/api/fitting/block-definitions", json=_body(), headers=admin_headers
        ).json()
        off = client.patch(
            f"/api/fitting/block-definitions/{made['id']}",
            json={"enabled": False},
            headers=admin_headers,
        )
        assert off.status_code == 200, off.text
        assert off.json()["installed"] is False
        shown = {
            one["key"]
            for one in client.get("/api/fitting/blocks", headers=admin_headers).json()
        }
        assert "anisotropy" not in shown

    def test_카드가_담고_있으면_못_지운다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """지우면 그 카드의 값이 「모르는 블록」 이 되어 덱에서 조용히 빠진다."""
        from sqlalchemy import select

        from app.modules.fitting.models import PropertyCard
        from app.modules.materials.models import Material
        from app.modules.workspaces.models import Workspace as Ws

        made = client.post(
            "/api/fitting/block-definitions", json=_body(), headers=admin_headers
        ).json()

        space = db.scalars(select(Ws)).first()
        assert space is not None
        material = Material(
            owner_workspace_id=space.id,
            family="Metal",
            category="Steel",
            grade="SECC",
            record_name="SECC-이방성",
        )
        db.add(material)
        db.flush()
        db.add(
            PropertyCard(
                material_id=material.id,
                label="이방성 카드",
                status="draft",
                blocks={"anisotropy": {"values": {"r_bar": 1.675}}},
            )
        )
        db.commit()

        blocked = client.delete(
            f"/api/fitting/block-definitions/{made['id']}", headers=admin_headers
        )
        assert blocked.status_code == 409, blocked.text
        assert "끄세요" in blocked.json()["error"]["message"]

    def test_아무도_안_쓰면_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = client.post(
            "/api/fitting/block-definitions", json=_body(), headers=admin_headers
        ).json()
        gone = client.delete(
            f"/api/fitting/block-definitions/{made['id']}", headers=admin_headers
        )
        assert gone.status_code == 204, gone.text
        assert cards.installed() == []
