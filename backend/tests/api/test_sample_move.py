"""시료째 **사람이 고른 재료**로 옮긴다(2026-11-14, VOC 59).

두께로 받을 재료를 계산하는 길은 같은 부서 · 같은 Grade · Details 안에서만 찾았다. 받을 재료를
직접 고르되 분류(Family · Category · Grade)가 같아야 하고, 받는 재료 · 시료 · 시편을 고칠 수
있어야 한다. 시료를 쪼개지 않는다 — 쪼개면 측정 의뢰 연결이 어긋난다.
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
from app.modules.materials.models import Sample
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun
from app.modules.workspaces.models import Workspace

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

CARD_STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "curve.sort_unique", "options": {"x": "strain_engineering"}},
    {"plugin": "tensile.strength", "options": {}},
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


def _material(
    client: TestClient, headers: dict[str, str], grade: str, details: str, thickness: float
) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": grade,
            "details": details,
            "spec_thickness": thickness,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


@pytest.fixture
def setup(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    """원 재료(시료 하나 · 시편 하나 · 채택된 시험 하나)와 받을 후보 둘."""
    ensure_builtin_test_types(db)
    db.commit()
    source = _material(client, admin_headers, "SECC", "MDOI", 1.0)
    same = _material(client, admin_headers, "SECC", "EG", 1.2)
    other = _material(client, admin_headers, "SPCC", "MDOI", 1.0)
    sample = client.post(
        f"/api/materials/{source['id']}/samples", json={}, headers=admin_headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    run = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
    result = client.post(
        "/api/processing/results",
        json={"test_run_id": run["id"], "steps": CARD_STEPS},
        headers=admin_headers,
    ).json()
    client.post(f"/api/processing/results/{result['id']}/adopt", headers=admin_headers)
    return {
        "source": source,
        "same": same,
        "other": other,
        "sample": sample,
        "run": run,
        "result_id": result["id"],
    }


class Test고른_재료로_시료째:
    def test_옮기고_이름을_다시_계산하며_채택은_따라간다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        setup: dict[str, Any],
    ) -> None:
        body = {
            "sample_ids": [setup["sample"]["id"]],
            "target_material_id": setup["same"]["id"],
        }
        plan = client.post("/api/samples/move-plan", json=body, headers=admin_headers).json()
        assert plan["specimens"] == 1 and plan["test_runs"] == 1 and plan["blocked"] == []
        assert plan["targets"][0]["to_material_name"] == setup["same"]["record_name"]
        # 미리보기는 쓰지 않는다.
        sample = db.get(Sample, uuid.UUID(setup["sample"]["id"]))
        assert sample is not None and str(sample.material_id) == setup["source"]["id"]

        done = client.post("/api/samples/move", json=body, headers=admin_headers)
        assert done.status_code == 200, done.text
        assert done.json()["moved"] == 1 and done.json()["split_samples"] == 0
        db.expire_all()
        sample = db.get(Sample, uuid.UUID(setup["sample"]["id"]))
        assert sample is not None and str(sample.material_id) == setup["same"]["id"]
        run = db.get(TestRun, uuid.UUID(setup["run"]["id"]))
        assert run is not None
        assert run.record_name.startswith(setup["same"]["record_name"])
        assert str(run.adopted_result_id) == setup["result_id"]  # 채택이 따라간다

    def test_분류가_다른_재료로는_안_옮긴다(
        self, client: TestClient, admin_headers: dict[str, str], setup: dict[str, Any]
    ) -> None:
        body = {
            "sample_ids": [setup["sample"]["id"]],
            "target_material_id": setup["other"]["id"],
        }
        refused = client.post("/api/samples/move", json=body, headers=admin_headers)
        assert refused.status_code == 422, refused.text
        assert "분류가 다른" in refused.json()["error"]["message"]

    def test_받는_재료를_고칠_수_없으면_막는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        setup: dict[str, Any],
    ) -> None:
        user = User(
            email="hong",
            password_hash=security.hash_password("member-password-1"),
            display_name="홍길동",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(user)
        db.commit()
        token = client.post(
            "/api/auth/login", json={"email": "hong", "password": "member-password-1"}
        ).json()["access_token"]
        body = {
            "sample_ids": [setup["sample"]["id"]],
            "target_material_id": setup["same"]["id"],
        }
        refused = client.post(
            "/api/samples/move", json=body, headers={"Authorization": f"Bearer {token}"}
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0067"

    def test_근거로_쓴_카드에_다른_재료로_옮겨졌다고_남긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        setup: dict[str, Any],
    ) -> None:
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": setup["source"]["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "옮기기 전 카드",
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        body = {
            "sample_ids": [setup["sample"]["id"]],
            "target_material_id": setup["same"]["id"],
        }
        plan = client.post("/api/samples/move-plan", json=body, headers=admin_headers).json()
        assert [one["id"] for one in plan["cards"]] == [card.json()["id"]]
        client.post("/api/samples/move", json=body, headers=admin_headers)
        remark = db.scalar(
            select(PropertyCardRemark).where(
                PropertyCardRemark.card_id == uuid.UUID(card.json()["id"])
            )
        )
        assert remark is not None and remark.kind == "relocated"
        assert "다른 재료" in remark.message and "두께" not in remark.message
