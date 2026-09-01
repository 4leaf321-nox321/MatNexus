"""예제 인장 파일 — **읽히는가, 그리고 정답을 되찾는가.**

`scripts/make_example_tensile.py` 가 만든 파일이다. 예제는 사람이 손으로 눌러 보는
것이지만, **읽히지 않는 예제는 예제가 아니다** — 그 사실을 사람이 발견하기 전에 여기서
안다. 파일과 리더 사이의 계약(열 이름·단위·머리말)이 어느 한쪽만 바뀌면 여기가 문다.

정답을 아는 파일이라 한 걸음 더 본다: **되찾은 탄성계수와 항복이 넣은 값과 맞는가.**
합성 데이터로 그것을 못 맞히면 실데이터에서는 더 못 맞힌다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles

#: 예제를 처리하는 단계. **시편 치수를 숫자로 직접 준다** — 참조(`@`)는 시편이
#: 무엇을 들고 있느냐에 달렸고, 여기서 보려는 것은 그것이 아니다.
STEPS: list[dict[str, Any]] = [
    {
        "plugin": "tensile.engineering",
        # 12.5 mm 곱하기 1.0 mm = 12.5e-6 m2, 표점 50 mm — 파일이 적은 그대로.
        "options": {"gauge_length": 0.05, "area": 12.5e-6},
    },
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
    # 탄성계수를 **먼저** 잰다 — 오프셋 선의 기울기가 그것이라, 항복이 이 값을 쓴다.
    {
        "plugin": "tensile.elastic_modulus",
        "options": {
            "method": "linear_regression",
            "minimum_strain": 0.0005,
            "maximum_strain": 0.0015,
        },
    },
    # 오프셋 선의 기울기는 **사람이 정한다**(앞 단계 값을 쓰거나 직접 넣는다).
    # 예제는 넣은 값을 그대로 준다 — 여기서 보려는 것은 항복을 되찾느냐이지
    # 탄성계수를 어떻게 넘기느냐가 아니다.
    {
        "plugin": "tensile.proof_stress",
        "options": {"offset_strain": 0.002, "youngs_modulus": 206e9},
    },
]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EXAMPLES = sorted(FIXTURES.glob("example_tensile_0*.mtet"))


def test_예제가_세_장_있다() -> None:
    """한 장으로는 묶음도 통계도 못 본다 — 예제의 쓸모가 절반이 된다."""
    assert len(EXAMPLES) == 3


@pytest.fixture
def uploaded(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> list[dict[str, Any]]:
    """예제 셋을 올려 읽는다."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()

    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "SECC", "grade": "EX01", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()

    runs: list[dict[str, Any]] = []
    for path in EXAMPLES:
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": (path.name, path.read_bytes())},
            headers=admin_headers,
        ).json()
        assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed", path.name
        runs.append(created)
    return runs


class Test예제가_읽힌다:
    def test_곡선과_요약값이_나온다(
        self, client: TestClient, admin_headers: dict[str, str], uploaded: list[dict[str, Any]]
    ) -> None:
        detail = client.get(
            f"/api/test-runs/{uploaded[0]['id']}", headers=admin_headers
        ).json()
        assert detail["status"] == "parsed"
        # 무릎을 보려고 촘촘히 박은 파일이다. 점이 줄면 「점 수 맞추기」 를 걸어도
        # 원본에 그 모양이 없어 차이가 안 보인다.
        [curve] = detail["curves"]
        assert curve["row_count"] == 1200
        assert {"displacement", "force"} <= set(curve["channels"])
        # 장비가 계산한 값도 함께 온다 — 나란히 놓고 견주는 것이 그 화면의 쓰임이다.
        assert any("0.2" in str(one.get("label", "")) for one in detail["summary"])

    def test_시편_치수가_파일에서_온다(
        self, client: TestClient, admin_headers: dict[str, str], uploaded: list[dict[str, Any]]
    ) -> None:
        """**입력값이지 시험 결과가 아니다** — 시편 실측치를 덮어쓰지 않고 따로 온다."""
        dimensions = client.get(
            f"/api/test-runs/{uploaded[0]['id']}/instrument-dimensions", headers=admin_headers
        ).json()
        fields = {one["field"] for one in dimensions["items"]}
        assert {"width", "thickness"} <= fields


class Test정답을_되찾는다:
    """합성으로도 못 맞히면 실데이터에서는 더 못 맞힌다."""

    def test_탄성계수와_항복이_넣은_값에_가깝다(
        self, client: TestClient, admin_headers: dict[str, str], uploaded: list[dict[str, Any]]
    ) -> None:
        run = uploaded[1]  # 흔들지 않은 가운데 시편(scale = 1.00)
        done = client.post(
            "/api/processing/results",
            json={"test_run_id": run["id"], "steps": STEPS},
            headers=admin_headers,
        )
        assert done.status_code == 201, done.text
        values = {
            one["key"]: one["value"]
            for one in done.json()["scalars"]
            if one.get("value") is not None
        }
        # 넣은 값: E = 206 GPa, 항복 350 MPa. 처리 규칙(구간·오프셋)이 달라지면
        # 여기가 먼저 흔들린다 — 그때 예제부터 다시 본다.
        assert values["youngs_modulus"] == pytest.approx(206e9, rel=0.05)
        assert values["proof_stress"] == pytest.approx(350e6, rel=0.05)
