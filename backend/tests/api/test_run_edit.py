"""시험 등록 뒤 고치기 — 메타·조건 편집과 원본 교체 (VOC 2026-09-13).

등록한 뒤 지그를 적거나 시험자를 바꾸거나 파일을 잘못 올린 것을 갈 자리가 없었다.
여기서 못 박는 것 셋: **안 보낸 칸은 그대로**, 단위 딸린 조건은 **단위와 함께 SI 로**,
원본을 바꾸면 **옛 파일은 남고 옛 결과는 「옛 원본의 것」 으로 보인다.**
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
from app.modules.tests.models import TestRun

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "curve.sort_unique", "options": {"x": "strain_engineering"}},
    {"plugin": "tensile.strength", "options": {}},
]


@pytest.fixture
def run(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SECC", "spec_thickness": 1.0},
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
        data={
            "specimen_id": specimen["id"],
            "test_type": "tensile",
            "conditions": '{"temperature": 25, "speed_elastic": 10}',
            "condition_units": '{"temperature": "degC", "speed_elastic": "mm/min"}',
            "operator": "김시험",
            "note": "처음 메모",
        },
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    )
    assert created.status_code == 202, created.text
    body: dict[str, Any] = created.json()
    return body


class TestUpdate:
    def test_보낸_칸만_바뀌고_조건은_단위와_함께_SI_로_담긴다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        run: dict[str, Any],
    ) -> None:
        patched = client.patch(
            f"/api/test-runs/{run['id']}",
            json={
                "operator": "박시험",
                "instrument": "Zwick Z100",
                # 온도는 그대로, 속도만 바꾼다 — 화면은 조건 전부를 보낸다.
                "conditions": {"temperature": 25, "speed_elastic": 5, "testing_group": "A조"},
                "condition_units": {"temperature": "degC", "speed_elastic": "mm/min"},
            },
            headers=admin_headers,
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert body["operator"] == "박시험"
        assert body["instrument"] == "Zwick Z100"
        assert body["note"] == "처음 메모", "안 보낸 칸은 그대로다"

        stored = db.get(TestRun, uuid.UUID(run["id"]))
        assert stored is not None
        db.refresh(stored)
        assert stored.conditions["speed_elastic"] == pytest.approx(5 / 60000)
        assert stored.conditions["temperature"] == pytest.approx(298.15)
        assert stored.conditions["testing_group"] == "A조"
        assert stored.input_units["speed_elastic"] == "mm/min"
        assert stored.instrument_term_id is not None, "장비는 기준정보를 거친다"

    def test_조건을_비우면_그_조건이_빠진다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        run: dict[str, Any],
    ) -> None:
        patched = client.patch(
            f"/api/test-runs/{run['id']}",
            json={
                "conditions": {"temperature": 25},
                "condition_units": {"temperature": "degC"},
            },
            headers=admin_headers,
        )
        assert patched.status_code == 200, patched.text
        stored = db.get(TestRun, uuid.UUID(run["id"]))
        assert stored is not None
        db.refresh(stored)
        assert "speed_elastic" not in stored.conditions
        assert "speed_elastic" not in stored.input_units

    def test_정의에_없는_조건과_틀린_단위는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        unknown = client.patch(
            f"/api/test-runs/{run['id']}",
            json={"conditions": {"nope": 1}},
            headers=admin_headers,
        )
        assert unknown.status_code == 422
        wrong_unit = client.patch(
            f"/api/test-runs/{run['id']}",
            json={
                "conditions": {"speed_elastic": 10},
                "condition_units": {"speed_elastic": "K"},
            },
            headers=admin_headers,
        )
        assert wrong_unit.status_code == 422

    def test_바뀐_것이_없으면_감사_기록도_없다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        before = client.get("/api/audit", headers=admin_headers)
        assert before.status_code == 200
        count = len(before.json()["items"]) if "items" in before.json() else len(before.json())
        same = client.patch(
            f"/api/test-runs/{run['id']}", json={"operator": "김시험"}, headers=admin_headers
        )
        assert same.status_code == 200
        after = client.get("/api/audit", headers=admin_headers).json()
        assert (len(after["items"]) if "items" in after else len(after)) == count


class TestReplaceSource:
    def test_원본을_바꾸면_옛_파일이_남고_옛_결과는_옛_원본의_것으로_보인다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        run: dict[str, Any],
    ) -> None:
        run_id = uuid.UUID(run["id"])
        assert test_services.parse_run(db, run_id) == "parsed"
        result = client.post(
            "/api/processing/results",
            json={"test_run_id": run["id"], "steps": STEPS},
            headers=admin_headers,
        )
        assert result.status_code == 201, result.text
        adopted = client.post(
            f"/api/processing/results/{result.json()['id']}/adopt", headers=admin_headers
        )
        assert adopted.status_code == 200 and adopted.json()["stale"] is False

        # 같은 내용에 줄 하나를 더한 파일 — 다른 sha 가 나온다.
        replaced = client.post(
            f"/api/test-runs/{run['id']}/source",
            files={"file": ("Example_v2.tra", TRA.read_bytes() + b"\r\n")},
            headers=admin_headers,
        )
        assert replaced.status_code == 202, replaced.text
        body = replaced.json()
        assert body["previous_filename"] == "Example.tra"
        assert body["stale_results"] == 1
        assert "다시 돌리세요" in body["message"]

        stored = db.get(TestRun, run_id)
        assert stored is not None
        db.refresh(stored)
        assert stored.source_filename == "Example_v2.tra"
        assert stored.source_replaced_at is not None
        assert stored.status == "uploaded", "다시 읽기가 큐에 들어갔다"
        assert len(stored.source_history) == 1
        assert stored.source_history[0]["filename"] == "Example.tra"
        assert stored.source_history[0]["sha256"] == run["source_sha256"]
        assert stored.source_sha256 != run["source_sha256"]
        # 옛 파일은 지우지 않는다.
        from app.shared import filestore

        assert filestore.read_bytes(stored.source_history[0]["path"]) == TRA.read_bytes()

        # 옛 결과는 그대로 있고, 「옛 원본의 것」 으로 보인다. 채택도 풀지 않는다.
        listed = client.get(
            "/api/processing/results", params={"test_run_id": run["id"]}, headers=admin_headers
        ).json()
        assert len(listed) == 1
        assert listed[0]["stale"] is True and listed[0]["is_adopted"] is True

        shown = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert shown["source_filename"] == "Example_v2.tra"
        assert shown["source_history"][0]["filename"] == "Example.tra"
        assert shown["source_replaced_at"] is not None

        # 다시 읽고 새로 돌린 결과는 옛 것이 아니다.
        assert test_services.parse_run(db, run_id) == "parsed"
        fresh = client.post(
            "/api/processing/results",
            json={"test_run_id": run["id"], "steps": STEPS},
            headers=admin_headers,
        )
        assert fresh.status_code == 201, fresh.text
        listed = client.get(
            "/api/processing/results", params={"test_run_id": run["id"]}, headers=admin_headers
        ).json()
        by_id = {one["id"]: one for one in listed}
        assert by_id[fresh.json()["id"]]["stale"] is False
        assert by_id[result.json()["id"]]["stale"] is True
