"""화면에서 적은 계산식이 **API 를 거쳐** 적합식·처리 단계가 되는가 (ADR 0030).

단위 시험(`tests/unit/test_formulas.py`)은 커널만 본다. 여기서는 관리자가 식을
저장하면 `/processing/steps`·`/fitting/families` 에 뜨고, 레시피가 그 단계를 돌려
값을 남기고, 고치면 판이 오르고, 쓰이는 식은 못 지우고, 끄면 목록에서 빠지는
데까지 간다. **저장된 결과는 식을 고쳐도 그대로다.**
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.workspaces.models import Workspace
from matcore import formulas as kit

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

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

RATIO = {
    "key": "yield_ratio_api",
    "kind": "scalar_step",
    "label": "항복비(식)",
    "expression": "proof_stress / tensile_strength",
    "variables": [
        {"name": "proof_stress", "unit": "Pa"},
        {"name": "tensile_strength", "unit": "Pa"},
    ],
    "result": {"key": "yield_ratio_api", "label": "항복비", "si_unit": "1"},
    "applies_to": ["tensile"],
}

SWIFT = {
    "key": "swift_api",
    "kind": "family",
    "label": "Swift(식)",
    "expression": "K * pow(e0 + x, n)",
    "variables": [{"name": "x", "unit": "1"}],
    "parameters": [
        {"name": "K", "unit": "Pa", "initial": 5e8, "lower": 0, "upper": 5e9},
        {"name": "e0", "unit": "1", "initial": 0.01, "lower": 1e-6, "upper": 1},
        {"name": "n", "unit": "1", "initial": 0.2, "lower": 0, "upper": 1},
    ],
    "x_column": "strain_true_plastic",
    "y_column": "stress_true",
    "block": "hardening",
    "applies_to": ["Metal"],
}

DOUBLED = {
    "key": "stress_doubled_api",
    "kind": "column_step",
    "label": "응력 두 배(식)",
    "expression": "2 * stress_true",
    "variables": [{"name": "stress_true", "unit": "Pa"}],
    "result": {"key": "stress_doubled", "label": "응력 두 배", "si_unit": "Pa"},
}


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """시험이 남긴 `formula.*` 를 뺀다 — 레지스트리는 프로세스 전역이고 DB 는 시험마다
    비워지므로, 안 빼면 다음 시험의 목록에 유령 단계가 남는다."""
    yield
    for key in kit.installed():
        kit.uninstall(key)


def _member_headers(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
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
def sample(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"FML-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "poisson_ratio": 0.3,
            "density": 7850,
        },
        headers=admin_headers,
    )
    assert material.status_code == 201, material.text
    made = client.post(
        f"/api/materials/{material.json()['id']}/samples", json={}, headers=admin_headers
    )
    assert made.status_code == 201, made.text
    return {"material_id": material.json()["id"], "id": made.json()["id"]}


def _run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    sample_id: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    specimen = client.post(
        f"/api/samples/{sample_id}/specimens",
        json={"orientation": "MD", "gauge_length": 50.0, "length_unit": "mm"},
        headers=headers,
    )
    assert specimen.status_code == 201, specimen.text
    created = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen.json()["id"],
            "test_type": "tensile",
            "conditions": json.dumps({"temperature": 296.15}),
            "condition_units": json.dumps({"temperature": "K"}),
        },
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": steps},
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
    )
    assert adopted.status_code in (200, 204), adopted.text
    body: dict[str, Any] = stored.json()
    return body


def _reload(
    client: TestClient, headers: dict[str, str], result: dict[str, Any]
) -> dict[str, Any]:
    listed = client.get(
        "/api/processing/results",
        params={"test_run_id": result["test_run_id"]},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    return next(one for one in listed.json() if one["id"] == result["id"])


def _scalar(result: dict[str, Any], key: str) -> float:
    for one in result["scalars"]:
        if one["key"] == key:
            return float(one["value"])
    raise AssertionError(f"{key} 가 없습니다: {[s['key'] for s in result['scalars']]}")


def _step_ids(client: TestClient, headers: dict[str, str]) -> set[str]:
    listed = client.get("/api/processing/steps", headers=headers)
    assert listed.status_code == 200, listed.text
    return {one["id"] for one in listed.json()}


def test_값_단계_식이_레시피에서_돌고_고치면_판이_오르고_쓰이면_못_지운다(
    client: TestClient, db: Session, admin_headers: dict[str, str], sample: dict[str, Any]
) -> None:
    before = _step_ids(client, admin_headers)
    assert "formula.yield_ratio_api" not in before

    created = client.post("/api/formulas", json=RATIO, headers=admin_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["registry_key"] == "formula.yield_ratio_api"
    assert body["kind_label"] == "값 단계"
    assert body["version"] == 1
    assert body["references"] == {"recipes": 0, "results": 0, "cards": 0}

    # 저장하자마자 단계 목록에 있다 — 재시작 없이.
    after = _step_ids(client, admin_headers)
    assert after - before == {"formula.yield_ratio_api"}
    listed = client.get("/api/processing/steps", headers=admin_headers).json()
    step = next(one for one in listed if one["id"] == "formula.yield_ratio_api")
    assert [p["name"] for p in step["params"]] == ["proof_stress", "tensile_strength"]

    # 레시피에서 돈다 — `@` 참조로 앞 단계 값을 받는다.
    steps = [
        *STEPS,
        {
            "plugin": "formula.yield_ratio_api",
            "options": {
                "proof_stress": "@proof_stress",
                "tensile_strength": "@tensile_strength",
            },
        },
    ]
    result = _run(client, db, admin_headers, sample["id"], steps)
    expected = _scalar(result, "proof_stress") / _scalar(result, "tensile_strength")
    assert _scalar(result, "yield_ratio_api") == pytest.approx(expected, rel=1e-9)
    assert 0 < expected < 1

    # 고치면 판이 오른다. 저장된 결과는 그대로다.
    patched = client.patch(
        f"/api/formulas/{body['id']}",
        json={"expression": "tensile_strength / proof_stress"},
        headers=admin_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2
    assert patched.json()["references"]["results"] == 1
    kept = _reload(client, admin_headers, result)
    assert _scalar(kept, "yield_ratio_api") == pytest.approx(expected, rel=1e-9)

    # 라벨만 고치면 판은 그대로다.
    relabel = client.patch(
        f"/api/formulas/{body['id']}",
        json={"label": "항복비(식, 새 이름)"},
        headers=admin_headers,
    )
    assert relabel.json()["version"] == 2

    # 쓰이는 식은 못 지운다 → 끈다 → 목록에서 빠진다 → 옛 결과는 읽힌다.
    refused = client.delete(f"/api/formulas/{body['id']}", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MNX-FORMULAS-0006"
    off = client.patch(
        f"/api/formulas/{body['id']}", json={"enabled": False}, headers=admin_headers
    )
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert off.json()["version"] == 2, "끄는 것은 식이 바뀐 게 아니다"
    assert "formula.yield_ratio_api" not in _step_ids(client, admin_headers)
    still = _reload(client, admin_headers, result)
    assert _scalar(still, "yield_ratio_api") == pytest.approx(expected, rel=1e-9)


def test_적합식이_목록에_뜨고_미리보기가_실제_곡선에_맞춘다(
    client: TestClient, db: Session, admin_headers: dict[str, str], sample: dict[str, Any]
) -> None:
    result = _run(client, db, admin_headers, sample["id"], STEPS)

    # 저장 전 미리보기 — 아무것도 남기지 않는다.
    preview = client.post(
        "/api/formulas/preview",
        json={"spec": SWIFT, "result_id": result["id"]},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    got = preview.json()
    assert got["ok"] is True, got["message"]
    assert got["r_squared"] is not None and got["r_squared"] > 0.9
    names = [p["name"] for p in got["parameters"]]
    assert names == ["K", "e0", "n"]
    assert client.get("/api/formulas", headers=admin_headers).json() == []
    families = client.get("/api/fitting/families", headers=admin_headers).json()
    assert "formula.swift_api" not in {f["key"] for f in families}

    # 축 이름을 틀리게 적으면 문법이 맞아도 여기서 걸린다.
    wrong = client.post(
        "/api/formulas/preview",
        json={"spec": {**SWIFT, "y_column": "stress_nope"}, "result_id": result["id"]},
        headers=admin_headers,
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "MNX-FORMULAS-0009"

    created = client.post("/api/formulas", json=SWIFT, headers=admin_headers)
    assert created.status_code == 201, created.text
    families = client.get("/api/fitting/families", headers=admin_headers).json()
    mine = next(f for f in families if f["key"] == "formula.swift_api")
    assert mine["label"] == "Swift(식)"
    assert [p for p in mine["parameter_names"]] == ["K", "e0", "n"]

    # **내장 Swift 와 같은 답** — 식 본문이 같으니까. 내장 적합은 그대로 돈다.
    compared = client.post(
        "/api/fitting/preview",
        json={
            "material_id": sample["material_id"],
            "test_type_key": "tensile",
            "orientation": "MD",
            "families": ["swift", "formula.swift_api"],
        },
        headers=admin_headers,
    )
    assert compared.status_code == 200, compared.text
    fits = {one["family"]: one for one in compared.json()["fits"]}
    assert set(fits) == {"swift", "formula.swift_api"}
    builtin = {p["name"]: p["value"] for p in fits["swift"]["parameters"]}
    mine = {p["name"]: p["value"] for p in fits["formula.swift_api"]["parameters"]}
    assert mine["n"] == pytest.approx(builtin["n"], rel=0.05)
    assert fits["formula.swift_api"]["r_squared"] == pytest.approx(
        fits["swift"]["r_squared"], abs=0.01
    )


def test_열_단계와_값_단계_미리보기(
    client: TestClient, db: Session, admin_headers: dict[str, str], sample: dict[str, Any]
) -> None:
    result = _run(client, db, admin_headers, sample["id"], STEPS)

    columns = client.post(
        "/api/formulas/preview",
        json={"spec": DOUBLED, "result_id": result["id"]},
        headers=admin_headers,
    )
    assert columns.status_code == 200, columns.text
    got = columns.json()
    assert got["ok"] is True, got["message"]
    assert got["sample"], "앞 몇 점을 보여 준다"
    first = got["sample"][0]
    assert first["stress_doubled"] == pytest.approx(2 * first["stress_true"])

    scalar = client.post(
        "/api/formulas/preview",
        json={"spec": RATIO, "result_id": result["id"]},
        headers=admin_headers,
    )
    assert scalar.status_code == 200, scalar.text
    got = scalar.json()
    assert got["ok"] is True, got["message"]
    assert got["value"] == pytest.approx(
        _scalar(result, "proof_stress") / _scalar(result, "tensile_strength")
    )

    # 앞 단계가 안 만든 값을 받으면 — 실패가 아니라 「없다」 고 말한다.
    missing = client.post(
        "/api/formulas/preview",
        json={
            "spec": {
                **RATIO,
                "expression": "proof_stress / nope",
                "variables": [
                    {"name": "proof_stress", "unit": "Pa"},
                    {"name": "nope", "unit": "1"},
                ],
            },
            "result_id": result["id"],
        },
        headers=admin_headers,
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["ok"] is False
    assert "nope" in missing.json()["message"]


def test_검사_어휘_권한(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    # 관리자만 만든다. 보는 것은 누구나.
    member = _member_headers(client, db, workspace)
    denied = client.post("/api/formulas", json=RATIO, headers=member)
    assert denied.status_code == 403
    assert client.get("/api/formulas", headers=member).status_code == 200

    # 어휘 — 화면이 드롭다운을 그리는 재료.
    vocab = client.get("/api/formulas/vocabulary", headers=member).json()
    assert {"key": "stress_true", "label": "진응력 (Pa)"} in vocab["columns"]
    assert any(one["key"] == "proof_stress" for one in vocab["scalars"])
    assert any(one["key"] == "hardening" for one in vocab["blocks"])
    assert "pow" in vocab["functions"] and "pi" in vocab["constants"]
    assert not any("{" in one["key"] for one in vocab["columns"]), (
        "옵션에 따라 이름이 정해지는 열은 뺀다"
    )

    # 문법·자리·단위를 저장 전에 거른다.
    bad_syntax = client.post(
        "/api/formulas", json={**RATIO, "expression": "import os"}, headers=admin_headers
    )
    assert bad_syntax.status_code == 422
    assert bad_syntax.json()["error"]["code"] == "MNX-FORMULAS-0002"
    bad_kind = client.post(
        "/api/formulas", json={**RATIO, "kind": "magic"}, headers=admin_headers
    )
    assert bad_kind.status_code == 422
    assert bad_kind.json()["error"]["code"] == "MNX-FORMULAS-0001"
    bad_unit = client.post(
        "/api/formulas",
        json={**RATIO, "result": {"key": "r", "label": "r", "si_unit": "furlong"}},
        headers=admin_headers,
    )
    assert bad_unit.status_code == 422
    assert bad_unit.json()["error"]["code"] == "MNX-FORMULAS-0003"
    unknown_name = client.post(
        "/api/formulas",
        json={**RATIO, "expression": "proof_stress / area"},
        headers=admin_headers,
    )
    assert unknown_name.status_code == 422, "변수에 없는 이름을 식에 쓰면 저장하지 않는다"

    # 같은 키 두 번은 안 된다. 안 쓰인 식은 지워지고 목록에서 빠진다.
    first = client.post("/api/formulas", json=RATIO, headers=admin_headers)
    assert first.status_code == 201
    dup = client.post("/api/formulas", json=RATIO, headers=admin_headers)
    assert dup.status_code == 409
    assert "formula.yield_ratio_api" in _step_ids(client, admin_headers)
    gone = client.delete(f"/api/formulas/{first.json()['id']}", headers=admin_headers)
    assert gone.status_code == 204
    assert "formula.yield_ratio_api" not in _step_ids(client, admin_headers)
    assert client.get("/api/formulas", headers=admin_headers).json() == []
