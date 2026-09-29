"""시편 목록 — **기준 두께와 차이가 큰 시편만**(2026-09-29).

두께가 다른 재료에 잘못 넣은 시편을 찾는 거르기다(ADR 0042). 무는 것:

    시험 파일이 잰 두께도 본다          개발 DB 에서 20% 넘게 다른 7개 중 6개가 그쪽에만
    경계는 사람의 셈이다               0.9 mm / 1.0 mm 는 9.999…% 로 나오지만 「10% 이상」
    가장 크게 어긋난 실측으로 판정     하나라도 크게 어긋나면 살펴볼 까닭이 있다
    기준 두께가 없는 재료는 안 견준다   견줄 것이 없는데 0% 로 세면 거짓말이다
    거르기 · 줄의 판정 · 선택지 수가 같다  「10% 이상 (3)」 을 골랐는데 두 줄이 나오면 안 된다
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Specimen
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from app.modules.workspaces.models import Workspace

SECC = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "MDOI",
    "spec_thickness": 1.0,
    "spec_thickness_unit": "mm",
}


def _sample(client: TestClient, headers: dict[str, str], **material: Any) -> str:
    made = client.post("/api/materials", json={**SECC, **material}, headers=headers)
    assert made.status_code == 201, made.text
    sample = client.post(
        f"/api/materials/{made.json()['id']}/samples", json={"lot_no": "L1"}, headers=headers
    )
    assert sample.status_code == 201, sample.text
    return str(sample.json()["id"])


def _specimen(
    client: TestClient, headers: dict[str, str], sample_id: str, thickness: float | None = None
) -> dict[str, Any]:
    """`thickness` 는 mm — 시편에 적은 두께(옛 두께 칸)."""
    body: dict[str, Any] = {"orientation": "MD"}
    if thickness is not None:
        body |= {"thickness": thickness, "length_unit": "mm"}
    made = client.post(f"/api/samples/{sample_id}/specimens", json=body, headers=headers)
    assert made.status_code == 201, made.text
    specimen: dict[str, Any] = made.json()
    return specimen


def _run(
    db: Session, workspace: Workspace, specimen: dict[str, Any], dimensions: dict[str, Any]
) -> TestRun:
    """시험 파일이 잰 치수(SI)를 든 시험."""
    ensure_builtin_test_types(db)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    count = db.scalar(
        select(TestRun.id).where(TestRun.specimen_id == uuid.UUID(specimen["id"])).limit(1)
    )
    run = TestRun(
        workspace_id=workspace.id,
        specimen_id=uuid.UUID(specimen["id"]),
        test_type_id=tensile.id,
        seq_no=2 if count else 1,
        record_name=f"{specimen['record_name']}__TEN_0{2 if count else 1}",
        status="parsed",
        dimensions=dimensions,
    )
    db.add(run)
    db.commit()
    return run


def _ids(client: TestClient, headers: dict[str, str], step: float) -> set[str]:
    got = client.get("/api/specimens", params={"thickness_gap": step}, headers=headers)
    assert got.status_code == 200, got.text
    return {one["id"] for one in got.json()["items"]}


class Test기준_두께와_차이:
    def test_시편에_적은_두께와_시험_파일이_잰_두께를_기준과_견준다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        sample = _sample(client, admin_headers)  # SECC_MDOI_1.0
        thick = _specimen(client, admin_headers, sample, thickness=1.2)  # +20% 시편에 적음
        thin = _specimen(client, admin_headers, sample)  # 시편에는 없다
        _run(db, workspace, thin, {"thickness": 0.0008})  # -20% 시험 파일이 잼
        close = _specimen(client, admin_headers, sample)
        row = db.get(Specimen, uuid.UUID(close["id"]))
        assert row is not None
        row.dimensions = {"thickness": 0.00102}  # +2% — 압연 공차
        db.commit()
        edge = _specimen(client, admin_headers, sample, thickness=0.9)  # 정확히 -10%
        # 기준 두께가 없는 재료 — 견줄 것이 없다.
        loose = _specimen(
            client, admin_headers, _sample(client, admin_headers, spec_thickness=None), 3.0
        )

        assert _ids(client, admin_headers, 0.05) == {thick["id"], thin["id"], edge["id"]}
        # **경계는 사람의 셈이다** — 0.9/1.0 은 부동소수로 9.999…% 다.
        assert _ids(client, admin_headers, 0.1) == {thick["id"], thin["id"], edge["id"]}
        assert _ids(client, admin_headers, 0.2) == {thick["id"], thin["id"]}

        rows = {
            one["id"]: one
            for one in client.get("/api/specimens", headers=admin_headers).json()["items"]
        }
        gap = rows[thick["id"]]["thickness_gap"]
        assert gap["source"] == "measured"
        assert (gap["spec"], gap["value"]) == pytest.approx((0.001, 0.0012))
        assert gap["deviation"] == pytest.approx(0.2)
        gap = rows[thin["id"]]["thickness_gap"]
        assert (gap["source"], gap["deviation"]) == ("run", pytest.approx(-0.2))
        assert rows[close["id"]]["thickness_gap"]["deviation"] == pytest.approx(0.02)
        assert rows[loose["id"]]["thickness_gap"] is None

        # **선택지 수가 거르기와 같은 식이다.**
        facets = client.get("/api/specimens/facets", headers=admin_headers).json()
        assert [(one["key"], one["count"]) for one in facets["thickness_gaps"]] == [
            ("0.05", 3),
            ("0.1", 3),
            ("0.2", 2),
        ]
        assert facets["thickness_gaps"][1]["label"] == "기준 두께와 10% 이상 차이"

    def test_가장_크게_어긋난_실측으로_판정하고_지운_시험은_안_본다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        sample = _sample(client, admin_headers)
        specimen = _specimen(
            client, admin_headers, sample, thickness=1.0
        )  # 시편에는 맞게 적었다
        wrong = _run(db, workspace, specimen, {"thickness": 0.00125})  # +25%
        _run(db, workspace, specimen, {"thickness": 0.00105})  # +5%

        [row] = client.get(
            "/api/specimens", params={"thickness_gap": 0.2}, headers=admin_headers
        ).json()["items"]
        assert row["thickness_gap"]["source"] == "run"
        assert row["thickness_gap"]["deviation"] == pytest.approx(0.25)
        # 하나의 시편에서도 **자기 줄로 온다**(시편 하나 화면).
        one = client.get(f"/api/specimens/{specimen['id']}", headers=admin_headers).json()
        assert one["thickness_gap"]["deviation"] == pytest.approx(0.25)

        wrong.deleted_at = datetime.now(UTC)
        db.commit()
        assert specimen["id"] not in _ids(client, admin_headers, 0.2)
        [row] = client.get(
            "/api/specimens", params={"thickness_gap": 0.05}, headers=admin_headers
        ).json()["items"]
        assert row["thickness_gap"]["deviation"] == pytest.approx(0.05)

    def test_숫자가_아닌_치수가_섞여도_목록이_선다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        """**`WHERE a AND b` 는 계산 순서를 보장하지 않는다.** 숫자가 아닌 값이 하나라도
        있을 때 형 검사보다 변환이 먼저 돌면 목록 전체가 500 이 된다."""
        sample = _sample(client, admin_headers)
        specimen = _specimen(client, admin_headers, sample)
        _run(db, workspace, specimen, {"thickness": "1.2 mm"})

        got = client.get(
            "/api/specimens", params={"thickness_gap": 0.05}, headers=admin_headers
        )
        assert got.status_code == 200, got.text
        assert got.json()["items"] == []
        facets = client.get("/api/specimens/facets", headers=admin_headers)
        assert facets.status_code == 200, facets.text
        assert facets.json()["thickness_gaps"] == []
