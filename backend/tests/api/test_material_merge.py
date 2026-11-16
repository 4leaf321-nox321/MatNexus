"""재료 합치기 — 같은 재료를 두 번 등록한 것을 하나로(2026-11-17, VOC 59 · ADR 0092).

시료 이동으로는 시료만 옮겨지고 재료에 직접 붙은 것(선언 물성 · 밀도 · 카드 · 묶음 기록 …)은
남아, 빈 재료를 휴지통에 넣으면 그것도 함께 사라졌다. 합치기는 받는 재료로 모은다 — **값이
다르면 받는 재료 우선**(사용자 결정)이고, 미리보기가 두 값을 함께 보인다.
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
from app.modules.audit.models import AuditEntry
from app.modules.auth import security
from app.modules.fitting.models import PropertyCard, PropertyCardRemark
from app.modules.materials.models import Material, Sample
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun
from app.modules.workspaces.models import Workspace

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

#: 카드를 만들 수 있는 결과(진응력까지) — `test_sample_move.py` 와 같다.
STEPS: list[dict[str, Any]] = [
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


def _material(client: TestClient, headers: dict[str, str], grade: str, details: str) -> Any:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": grade,
            "details": details,
            "spec_thickness": 1.0,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return made.json()


def _row(item: str, value: float) -> dict[str, Any]:
    return {
        "item": item,
        "points": [{"value_si": value, "temperature_k": 293.15}],
        "source": "literature",
        "si_unit": "1",
        "reference": "시험용",
        "input_unit": "1",
    }


@pytest.fixture
def setup(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    """보낼 재료(시료 둘 — 하나는 빈 시료 · 채택된 시험 하나 · 카드 하나)와 받을 재료 · 분류가
    다른 재료."""
    ensure_builtin_test_types(db)
    db.commit()
    source = _material(client, admin_headers, "SECC", "MDOI")
    target = _material(client, admin_headers, "secc", "EG")  # Grade 는 대소문자를 안 가린다
    other = _material(client, admin_headers, "SPCC", "MDOI")
    sample = client.post(
        f"/api/materials/{source['id']}/samples", json={}, headers=admin_headers
    ).json()
    empty = client.post(
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
        json={"test_run_id": run["id"], "steps": STEPS},
        headers=admin_headers,
    ).json()
    client.post(f"/api/processing/results/{result['id']}/adopt", headers=admin_headers)
    card = client.post(
        "/api/fitting/cards",
        json={
            "material_id": source["id"],
            "test_type_key": "tensile",
            "orientation": "MD",
            "label": "합치기 전 카드",
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text

    # 값 — 받는 재료에 없는 것(밀도 · 「비열」)과 둘 다 있고 다른 것(푸아송비 · 「탄성계수」).
    mine = db.get(Material, uuid.UUID(source["id"]))
    theirs = db.get(Material, uuid.UUID(target["id"]))
    assert mine is not None and theirs is not None
    mine.density_si = 7850.0
    mine.poisson_ratio = 0.29
    mine.declared_properties = [_row("비열", 470.0), _row("탄성계수", 2.0e11)]
    theirs.poisson_ratio = 0.3
    theirs.declared_properties = [_row("탄성계수", 2.1e11)]
    db.commit()
    return {
        "source": source,
        "target": target,
        "other": other,
        "samples": [sample["id"], empty["id"]],
        "run": run,
        "result_id": result["id"],
        "card_id": card.json()["id"],
    }


def _ask(
    client: TestClient, headers: dict[str, str], source: str, target: str, path: str
) -> Any:
    return client.post(
        f"/api/materials/{source}/{path}",
        json={"target_material_id": target, "comment": "같은 재료를 두 번 등록함"},
        headers=headers,
    )


class Test합치기:
    def test_미리보기는_무엇이_어디로_가는지_세고_쓰지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        setup: dict[str, Any],
    ) -> None:
        got = _ask(
            client, admin_headers, setup["source"]["id"], setup["target"]["id"], "merge-plan"
        )
        assert got.status_code == 200, got.text
        plan = got.json()
        assert plan["blocked"] == []
        assert (plan["samples"], plan["specimens"], plan["test_runs"], plan["cards"]) == (
            2,
            1,
            1,
            1,
        )
        assert any(one.startswith("밀도 7850") for one in plan["taken"])
        assert "선언 물성 「비열」" in plan["taken"]
        assert any(
            "푸아송비: 받는 재료 0.3 유지(합칠 재료 0.29)" in one for one in plan["kept"]
        )
        assert any("「탄성계수」" in one for one in plan["kept"])
        assert any(one.startswith("Details: 받는 재료 EG 유지") for one in plan["kept"])
        db.expire_all()
        mine = db.get(Material, uuid.UUID(setup["source"]["id"]))
        assert mine is not None and mine.deleted_at is None, "미리보기가 썼다"

    def test_합치면_받는_재료로_모이고_보낸_재료는_휴지통으로(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        setup: dict[str, Any],
    ) -> None:
        source_id, target_id = setup["source"]["id"], setup["target"]["id"]
        done = _ask(client, admin_headers, source_id, target_id, "merge")
        assert done.status_code == 200, done.text
        assert done.json()["merged"] is True
        db.expire_all()

        for sample_id in setup["samples"]:  # 빈 시료도 함께 간다
            sample = db.get(Sample, uuid.UUID(sample_id))
            assert sample is not None and str(sample.material_id) == target_id
        run = db.get(TestRun, uuid.UUID(setup["run"]["id"]))
        target = db.get(Material, uuid.UUID(target_id))
        assert run is not None and target is not None
        assert run.record_name.startswith(target.record_name)
        assert str(run.adopted_result_id) == setup["result_id"]  # 채택이 따라간다

        card = db.get(PropertyCard, uuid.UUID(setup["card_id"]))
        assert card is not None and str(card.material_id) == target_id
        remark = db.scalar(
            select(PropertyCardRemark).where(PropertyCardRemark.card_id == card.id)
        )
        assert remark is not None and "재료 합치기" in remark.message
        assert remark.comment == "같은 재료를 두 번 등록함"

        # 값 — 비었던 칸은 가져오고, 다른 값은 받는 재료의 것.
        assert target.density_si == 7850.0
        assert target.poisson_ratio == 0.3
        items = {row["item"]: row for row in target.declared_properties}
        assert set(items) == {"탄성계수", "비열"}
        assert items["탄성계수"]["points"][0]["value_si"] == 2.1e11

        source = db.get(Material, uuid.UUID(source_id))
        assert source is not None and source.deleted_at is not None  # 휴지통(되살릴 수 있다)
        actions = set(
            db.scalars(
                select(AuditEntry.action).where(
                    AuditEntry.target_id.in_([uuid.UUID(source_id), uuid.UUID(target_id)])
                )
            )
        )
        assert {"materials.merged", "material.deleted"} <= actions

    def test_분류가_다르면_합치지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], setup: dict[str, Any]
    ) -> None:
        source_id, other_id = setup["source"]["id"], setup["other"]["id"]
        plan = _ask(client, admin_headers, source_id, other_id, "merge-plan").json()
        assert any("분류가 다른" in one for one in plan["blocked"])
        refused = _ask(client, admin_headers, source_id, other_id, "merge")
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0073"

    def test_같은_재료끼리는_합치지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], setup: dict[str, Any]
    ) -> None:
        source_id = setup["source"]["id"]
        refused = _ask(client, admin_headers, source_id, source_id, "merge")
        assert (
            refused.status_code == 422
            and "같은 재료끼리" in refused.json()["error"]["message"]
        )

    def test_고칠_수_없으면_막는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        setup: dict[str, Any],
    ) -> None:
        user = User(
            email="merge-member",
            password_hash=security.hash_password("member-password-1"),
            display_name="합치려는 사람",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(user)
        db.commit()
        token = client.post(
            "/api/auth/login", json={"email": "merge-member", "password": "member-password-1"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        plan = _ask(
            client, headers, setup["source"]["id"], setup["target"]["id"], "merge-plan"
        ).json()
        assert any("고칠 수 없습니다" in one for one in plan["blocked"])
        refused = _ask(client, headers, setup["source"]["id"], setup["target"]["id"], "merge")
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0072"
