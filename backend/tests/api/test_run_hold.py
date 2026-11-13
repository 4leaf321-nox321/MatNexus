"""시험의 **물성 사용 보류**(2026-11-14, VOC 60).

문제가 의심되는 시험을 「쓰지 말라」 고 표시할 자리가 없었다. 메모에 적어도 채택 · 카드 ·
통계는 몰랐고, 시험 메모는 MCP 응답에 실리지 않아 AI 도 몰랐다. 자료 관리자가 사유와 함께 걸고
푼다. 걸리면 채택 · 카드에 못 쓰고 통계에서 빠지며, 이 시험을 근거로 쓴 카드에는 비고가 붙는다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.fitting.models import PropertyCardRemark
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun
from app.modules.workspaces.models import Workspace

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "curve.sort_unique", "options": {"x": "strain_engineering"}},
    {"plugin": "tensile.strength", "options": {}},
]


@pytest.fixture
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


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    made: dict[str, Any] = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "HOLD", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    return made


def _run(client: TestClient, headers: dict[str, str], db: Session, material_id: str) -> str:
    sample = client.post(f"/api/materials/{material_id}/samples", json={}, headers=headers)
    specimen = client.post(
        f"/api/samples/{sample.json()['id']}/specimens",
        json={"orientation": "MD"},
        headers=headers,
    ).json()
    made = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(made["id"])) == "parsed"
    return str(made["id"])


#: 카드까지 가는 레시피 — 진응력 · 진소성변형률을 낸다(`test_fitting.STEPS` 와 같다).
CARD_STEPS: list[dict[str, Any]] = [
    *STEPS,
    {
        "plugin": "tensile.elastic_modulus",
        "options": {"method": "manual", "manual_modulus": 200e9},
    },
    {"plugin": "tensile.proof_stress", "options": {"youngs_modulus": "@youngs_modulus"}},
    {
        "plugin": "tensile.true_plastic",
        "options": {"youngs_modulus": "@youngs_modulus", "proof_stress": "@proof_stress"},
    },
]


def _result(
    client: TestClient,
    headers: dict[str, str],
    run_id: str,
    steps: list[dict[str, Any]] = STEPS,
) -> str:
    saved = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": steps},
        headers=headers,
    )
    assert saved.status_code == 201, saved.text
    return str(saved.json()["id"])


def _hold(client: TestClient, headers: dict[str, str], run_id: str) -> Any:
    return client.post(
        f"/api/test-runs/{run_id}/hold", json={"reason": "그립 미끄럼 의심"}, headers=headers
    )


class Test걸고_풀기:
    def test_자료_관리자가_사유와_함께_건다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, material["id"])
        held = _hold(client, admin_headers, run_id)
        assert held.status_code == 200, held.text
        assert held.json()["hold_reason"] == "그립 미끄럼 의심"
        assert held.json()["held_by"] == "시스템 관리자"
        released = client.delete(f"/api/test-runs/{run_id}/hold", headers=admin_headers)
        assert released.status_code == 200 and released.json()["hold_reason"] is None

    def test_자료_관리자가_아니면_못_건다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        member_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        # 등록자가 스스로 풀 수 있으면 보류가 뜻이 없다 — 걸기 · 풀기 모두 자료 관리자다.
        run_id = _run(client, admin_headers, db, material["id"])
        refused = _hold(client, member_headers, run_id)
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-TESTS-0045"

    def test_사유_없는_보류는_없다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, material["id"])
        empty = client.post(
            f"/api/test-runs/{run_id}/hold", json={"reason": "   "}, headers=admin_headers
        )
        assert empty.status_code == 422


class Test걸리면:
    def test_채택을_막는다_확인으로도_못_넘는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, material["id"])
        result_id = _result(client, admin_headers, run_id)
        _hold(client, admin_headers, run_id)
        refused = client.post(
            f"/api/processing/results/{result_id}/adopt",
            params={"confirm_warnings": True},
            headers=admin_headers,
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "MNX-PROCESSING-0021"
        assert "그립 미끄럼 의심" in refused.json()["error"]["message"]
        many = client.post(
            "/api/processing/adopt-many",
            json={
                "items": [{"test_run_id": run_id, "result_id": result_id}],
                "confirm_warnings": True,
            },
            headers=admin_headers,
        ).json()
        assert many["items"][0]["status"] == "failed"
        batch = client.post(
            "/api/processing/batch",
            json={"test_run_ids": [run_id], "steps": STEPS, "adopt": True},
            headers=admin_headers,
        ).json()
        assert batch["items"][0]["adopted"] is False
        assert "보류" in batch["items"][0]["warning"]

    def test_통계에서_빠지고_몇_건_뺐는지_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        runs = [_run(client, admin_headers, db, material["id"]) for _ in range(2)]
        for run_id in runs:
            client.post(
                f"/api/processing/results/{_result(client, admin_headers, run_id)}/adopt",
                headers=admin_headers,
            )
        _hold(client, admin_headers, runs[0])
        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        assert group["sample_count"] == 1
        assert any("보류 중인 시험 1건" in note for note in group["notes"])

    def test_근거로_쓴_카드에_비고가_붙는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, material["id"])
        result_id = _result(client, admin_headers, run_id, CARD_STEPS)
        client.post(f"/api/processing/results/{result_id}/adopt", headers=admin_headers)
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "보류 전 카드",
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        _hold(client, admin_headers, run_id)
        client.delete(f"/api/test-runs/{run_id}/hold", headers=admin_headers)
        kinds = [
            one.kind
            for one in db.scalars(
                select(PropertyCardRemark)
                .where(PropertyCardRemark.card_id == uuid.UUID(card.json()["id"]))
                .order_by(PropertyCardRemark.created_at)
            )
        ]
        assert kinds == ["held", "hold_released"]

    def test_감사_기록에_남는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, material["id"])
        _hold(client, admin_headers, run_id)
        run = db.get(TestRun, uuid.UUID(run_id))
        assert run is not None
        db.refresh(run)
        assert run.held_at is not None
        logs = client.get("/api/audit", params={"target_id": run_id}, headers=admin_headers)
        assert logs.status_code == 200, logs.text
        assert "test_run.held" in logs.text
