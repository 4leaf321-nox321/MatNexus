"""수치 표가 중간에 끊기면 **시험 점검까지** 간다(2026-11-15).

천 단위 쉼표 · `#DIV/0!` 한 칸에서 숫자 블록이 끊기면 첫 표만 읽는 기본 규칙이 뒤의 줄을
버리고 곡선이 잘린 채 「읽힘」 이 됐다. 읽기 경고(`profile._truncated`)가 시험 메모
(`_warnings`)에 한 번 · 시험 점검(`checks`, 처리 결과로 옮겨 가 채택할 때 확인받는 자리)에
올라가는지 본다. 막지는 않는다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.tests.models import Curve, TestRun
from matcore.readers import profile as profiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _upload(client: TestClient, db: Session, headers: dict[str, str], data: bytes) -> TestRun:
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "Adhesive", "grade": "CUT-1"},
        headers=headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens", json={"orientation": "NA"}, headers=headers
    ).json()
    created = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen["id"],
            "test_type": "stress_relaxation",
            "conditions": '{"held_strain": 0.005}',
        },
        files={"file": ("relaxation_cut.csv", data)},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    run_id = uuid.UUID(created.json()["id"])
    assert test_services.parse_run(db, run_id) == "parsed"
    run = db.get(TestRun, run_id)
    assert run is not None
    return run


def test_끊긴_표는_시험_점검과_메모에_한_번씩_선다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    lines = (FIXTURES / "relaxation_standard.csv").read_bytes().decode("utf-8").splitlines()
    # 머리 두 줄 뒤 데이터 30번째 줄의 응력 칸을 스프레드시트 오류 값으로.
    cells = lines[31].split(",")
    cells[1] = "#DIV/0!"
    lines[31] = ",".join(cells)
    run = _upload(client, db, admin_headers, "\n".join(lines).encode("utf-8"))

    found = [one for one in run.checks if one["code"] == "table_truncated"]
    assert len(found) == 1, run.checks
    message = found[0]["message"]
    assert message.startswith(profiles.TRUNCATED)
    assert "32행에서 끊겨" in message and "스프레드시트 오류 값" in message
    # 메모에는 한 번 — 읽기 경고와 점검이 같은 말이다.
    assert run.source_metadata["_warnings"].count(profiles.TRUNCATED) == 1
    # 값은 그대로 — 끊긴 줄 앞의 29점만 곡선이 된다(막지 않는다).
    curve = db.query(Curve).filter(Curve.test_run_id == run.id).one()
    assert curve.row_count == 29


def test_끝까지_읽은_표는_점검이_없다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    run = _upload(
        client, db, admin_headers, (FIXTURES / "relaxation_standard.csv").read_bytes()
    )
    assert not [one for one in run.checks or [] if one["code"] == "table_truncated"]
