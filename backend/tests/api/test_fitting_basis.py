"""카드의 대표 곡선 — **평균만이 아니라 상한·하한으로도**(2026-09-29).

통계 화면은 「어느 것을 쓸지는 피팅할 때 고르면 된다」 고 적어 두었는데, 정작 카드 만들기는
늘 평균이었다. 무는 것:

    미리보기가 고른 기준의 곡선을 평균 곁에 준다    얼마나 물러섰는지 눈으로 본다
    카드가 기준을 근거에 남긴다                    이름만 「하한」 인 카드가 되지 않게
    곡선에만 적용했다고 적는다                     탄성계수까지 하한인 줄 알면 안 된다
    못 서는 기준은 이유와 함께 거절한다             시편 1개 · 공차 한계에 시편 2개
    기준을 안 주면 전과 같다                       옛 화면·스크립트는 전과 같은 카드를 받는다

곡선은 **합성**이다 — 같은 원본 파일을 여러 번 올리면 흩어짐이 0 이라 상·하한이 평균과
같아져 아무것도 못 잰다. 배율 0.9 · 1.0 · 1.1 로 세 벌을 둔다.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.processing.models import ProcessingResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from app.modules.workspaces.models import Workspace
from app.shared import filestore
from matcore import curves
from matcore.parsers import Channel

STRAIN = np.linspace(0.0, 0.1, 41)
BASE = 300e6 + 400e6 * STRAIN**0.5


def _material(client: TestClient, headers: dict[str, str], grade: str) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": grade,
            "details": "MDOI",
            "spec_thickness": 1.0,
            "spec_thickness_unit": "mm",
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _runs(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    workspace: Workspace,
    material_id: str,
    scales: list[float],
) -> list[str]:
    """배율마다 시편 하나 · 채택된 처리 결과 하나(진소성변형률 - 진응력)."""
    ensure_builtin_test_types(db)
    db.commit()
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    names: list[str] = []
    for scale in scales:
        sample = client.post(
            f"/api/materials/{material_id}/samples", json={}, headers=headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=headers,
        ).json()
        data = curves.to_parquet(
            [
                Channel(
                    key="strain_true_plastic",
                    label="진소성변형률",
                    si_unit="1",
                    values=tuple(float(one) for one in STRAIN),
                ),
                Channel(
                    key="stress_true",
                    label="진응력",
                    si_unit="Pa",
                    values=tuple(float(one) for one in scale * BASE),
                ),
            ]
        )
        stored = filestore.write_bytes(
            data, relative_dir="test-basis", filename=f"{uuid.uuid4().hex}.parquet"
        )
        run = TestRun(
            workspace_id=workspace.id,
            specimen_id=uuid.UUID(specimen["id"]),
            test_type_id=tensile.id,
            seq_no=1,
            record_name=f"{specimen['record_name']}__TEN_01",
            status="parsed",
        )
        db.add(run)
        db.flush()
        result = ProcessingResult(
            test_run_id=run.id,
            source_curve_key="raw",
            storage_path=stored.relative_path,
            row_count=len(STRAIN),
            sha256=stored.sha256,
            byte_size=stored.size,
            columns=["strain_true_plastic", "stress_true"],
            scalars=[{"key": "youngs_modulus", "value": 200e9, "si_unit": "Pa"}],
            stages=[],
        )
        db.add(result)
        db.flush()
        run.adopted_result_id = result.id
        names.append(run.record_name)
    db.commit()
    return names


def _ask(material_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "material_id": material_id,
        "test_type_key": "tensile",
        "orientation": "MD",
        "families": ["voce"],
        **extra,
    }


@pytest.fixture
def spread(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> tuple[str, list[str]]:
    material = _material(client, admin_headers, "BASIS")
    names = _runs(client, admin_headers, db, workspace, material["id"], [0.9, 1.0, 1.1])
    return material["id"], names


class Test미리보기:
    def test_하한을_평균_곁에_준다(
        self, client: TestClient, admin_headers: dict[str, str], spread: tuple[str, list[str]]
    ) -> None:
        material_id, _ = spread
        got = client.post(
            "/api/fitting/preview",
            json=_ask(material_id, basis={"kind": "lower", "method": "sd", "k": 2}),
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["basis_label"] == "하한 — 평균 - 2σ"
        source = np.asarray(body["source_points"])
        reference = np.asarray(body["reference_points"])
        assert len(source) == len(reference) == len(STRAIN)
        # 평균은 배율 1.0 곡선이다 — 하한은 그 아래, 흩어짐(0.1 배)의 두 배만큼.
        assert np.allclose(reference[:, 1], BASE)
        assert np.allclose(source[:, 1], BASE - 2 * 0.1 * BASE)
        assert any("표준편차" in note for note in body["notes"])

    def test_기준을_안_주면_전과_같다(
        self, client: TestClient, admin_headers: dict[str, str], spread: tuple[str, list[str]]
    ) -> None:
        material_id, _ = spread
        body = client.post(
            "/api/fitting/preview", json=_ask(material_id), headers=admin_headers
        ).json()
        assert body["basis_label"] == "평균"
        assert body["reference_points"] == []
        assert np.allclose(np.asarray(body["source_points"])[:, 1], BASE)

    def test_실제_시편은_어느_시편인지_이름을_단다(
        self, client: TestClient, admin_headers: dict[str, str], spread: tuple[str, list[str]]
    ) -> None:
        material_id, names = spread
        body = client.post(
            "/api/fitting/preview",
            json=_ask(material_id, basis={"kind": "upper", "method": "specimen"}),
            headers=admin_headers,
        ).json()
        # 배율 1.1 이 가장 높다.
        assert body["basis_label"] == f"상한 — 가장 높은 시편({names[2]})"
        assert np.allclose(np.asarray(body["source_points"])[:, 1], 1.1 * BASE)


class Test카드:
    def test_기준을_근거에_남기고_곡선에만_적용했다고_적는다(
        self, client: TestClient, admin_headers: dict[str, str], spread: tuple[str, list[str]]
    ) -> None:
        material_id, _ = spread
        made = client.post(
            "/api/fitting/cards",
            json={
                "material_id": material_id,
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "BASIS MD 하한",
                "basis": {"kind": "lower", "method": "envelope"},
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        card = made.json()
        assert card["source"]["curve_basis"] == {
            "kind": "lower",
            "method": "envelope",
            "k": None,
            "label": "하한 — 포락선(점마다 최솟값)",
        }
        stresses = [row["true_stress"] for row in card["blocks"]["table"]["rows"]]
        assert np.allclose(stresses, 0.9 * BASE), "표가 가장 낮은 곡선이 아니다"
        assert any("곡선(소성 표·식)에만 적용" in note for note in card["source"]["notes"])
        # 탄성계수는 평균 그대로다.
        assert card["blocks"]["elastic"]["values"]["youngs_modulus"] == pytest.approx(200e9)

    def test_기준을_안_주면_근거에_안_적는다(
        self, client: TestClient, admin_headers: dict[str, str], spread: tuple[str, list[str]]
    ) -> None:
        material_id, _ = spread
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": material_id,
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "BASIS MD",
            },
            headers=admin_headers,
        ).json()
        assert "curve_basis" not in card["source"]
        stresses = [row["true_stress"] for row in card["blocks"]["table"]["rows"]]
        assert np.allclose(stresses, BASE)


class Test거절:
    def test_시편_1개면_상하한을_못_낸다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        material = _material(client, admin_headers, "ONE")
        _runs(client, admin_headers, db, workspace, material["id"], [1.0])
        got = client.post(
            "/api/fitting/preview",
            json=_ask(material["id"], basis={"kind": "lower", "method": "envelope"}),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-FITTING-0043"
        assert "흩어짐을 모릅니다" in got.json()["error"]["message"]

    def test_공차_한계는_시편_3개부터다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        material = _material(client, admin_headers, "TWO")
        _runs(client, admin_headers, db, workspace, material["id"], [0.95, 1.05])
        got = client.post(
            "/api/fitting/preview",
            json=_ask(material["id"], basis={"kind": "lower", "method": "tolerance"}),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-FITTING-0043"
        assert "3개부터" in got.json()["error"]["message"]

    def test_방법_없는_하한은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], spread: tuple[str, list[str]]
    ) -> None:
        material_id, _ = spread
        got = client.post(
            "/api/fitting/preview",
            json=_ask(material_id, basis={"kind": "lower"}),
            headers=admin_headers,
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-FITTING-0043"
