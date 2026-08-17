"""재료 단위 통계 — **묶음이 맞는가, 아무것도 조용히 빠지지 않는가.**

이 파일이 지키는 것은 둘이다.

1. **묶음은 재료 + 시험종류 + 방향이다.** 인장은 압연 방향에 따라 물성이 다르다
   — MD 와 TD 를 섞으면 CV 가 크게 나오는데 그것은 산포가 아니라 다른 것을
   섞은 것이다.

2. **빠진 것을 말한다.** 채택 안 된 시험, 이상치, 격자가 달라 못 낸 곡선 —
   전부 이유와 함께 남는다. 조용히 빠지면 n 이 왜 그 수인지 알 수 없다.

계산 자체는 `tests/unit/test_statistics.py` 가 손으로 검산한 값으로 본다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
]


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    created: dict[str, Any] = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "STAT",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    return created


def _run(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    material_id: str,
    orientation: str,
) -> str:
    sample = client.post(
        f"/api/materials/{material_id}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": orientation},
        headers=headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


def _adopt(client: TestClient, headers: dict[str, str], run_id: str) -> None:
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": STEPS},
        headers=headers,
    ).json()
    client.post(f"/api/processing/results/{stored['id']}/adopt", headers=headers)


class Test묶음:
    def test_방향을_섞지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**압연 방향에 따라 물성이 다르다.**

        MD 와 TD 를 한 통계로 묶으면 CV 가 크게 나오는데, 그것은 산포가 아니라
        서로 다른 것을 섞은 것이다. 강판은 20% 넘게 차이 나기도 한다.
        """
        for orientation in ("MD", "MD", "TD"):
            _adopt(
                client,
                admin_headers,
                _run(client, admin_headers, db, material["id"], orientation),
            )

        body = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()
        by_orientation = {group["orientation"]: group for group in body["groups"]}
        assert set(by_orientation) == {"MD", "TD"}
        assert by_orientation["MD"]["sample_count"] == 2
        assert by_orientation["TD"]["sample_count"] == 1

    def test_채택_안_된_시험은_빠지고_그_사실을_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        # **조용히 빼면 n 이 왜 그 수인지 모른다.**
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        _run(client, admin_headers, db, material["id"], "MD")  # 채택 안 함

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        assert group["sample_count"] == 2
        assert group["skipped_unadopted"] == 1
        assert any("채택되지 않은 시험 1건" in note for note in group["notes"])


class Test통계값:
    @pytest.fixture
    def three(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> dict[str, Any]:
        for _ in range(3):
            _adopt(
                client, admin_headers, _run(client, admin_headers, db, material["id"], "MD")
            )
        groups = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"]
        return dict(groups[0])

    def test_항목마다_흩어짐을_낸다(self, three: dict[str, Any]) -> None:
        keys = {row["key"] for row in three["scalars"]}
        assert "tensile_strength" in keys
        row = next(row for row in three["scalars"] if row["key"] == "tensile_strength")
        assert row["count"] == 3
        assert row["ci95_low"] is not None and row["ci95_high"] is not None
        assert row["median"] == pytest.approx(row["mean"])

    def test_평균이_뜻없는_항목은_빼놓는다(self, three: dict[str, Any]) -> None:
        """`necking_candidate_index` 는 배열 위치다. 평균 14.0 은 아무 뜻이 없다."""
        keys = {row["key"] for row in three["scalars"]}
        assert not any(key.endswith("_index") for key in keys)
        assert "elastic_r_squared" not in keys
        assert "proof_offset" not in keys

    def test_곡선_통계가_나온다(self, three: dict[str, Any]) -> None:
        # 같은 파일이라 격자가 같다 — 실무에서는 재샘플을 거쳐야 이 상태가 된다.
        assert three["curve"] is not None
        assert three["curve"]["x"] == "strain_engineering"
        assert len(three["curve"]["mean"]) == len(three["curve"]["median"])
        assert len(three["curve"]["sd"]) == len(three["curve"]["mean"])


class Test저장:
    def test_불변으로_남긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**쓴 시험을 함께 박아 둔다.**

        나중에 시험이 늘면 평균이 달라지는데, 어제 보고서에 적은 값은 어제의
        표본으로 나온 것이다.
        """
        for _ in range(2):
            _adopt(
                client, admin_headers, _run(client, admin_headers, db, material["id"], "MD")
            )

        saved = client.post(
            "/api/statistics/ensembles",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["sample_count"] == 2
        assert len(saved.json()["test_run_ids"]) == 2

        # 시험을 하나 더 채택해도 저장된 것은 그대로다.
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        listed = client.get(
            f"/api/statistics/ensembles?material_id={material['id']}", headers=admin_headers
        ).json()
        assert len(listed) == 1
        assert listed[0]["sample_count"] == 2

    def test_표본이_모자라면_남기지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        response = client.post(
            "/api/statistics/ensembles",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "2건 이상" in response.json()["error"]["message"]
