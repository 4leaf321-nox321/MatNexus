"""물성 분석 — **다섯 화면이 같은 관측을 보는가.**

무는 자리를 「표가 나온다」 보다 **「채택 안 된 것을 안 센다」**·「1건이면 흩어짐이
없다」·「못 견준 항목을 숨기지 않는다」 에 둔다. 앞엣것은 화면에서 바로 보이지만,
뒤엣것은 **조용히 틀린 수**를 말한다 — 처리 전 값이 평균에 섞이면 그 평균은
아무것도 아니게 된다.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.processing.models import ProcessingResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun


def _material(client: TestClient, headers: dict[str, str], grade: str, **extra: Any) -> Any:
    body = {
        "family": "Metal",
        "category": "Steel",
        "grade": grade,
        "details": "AN",
        "spec_thickness": 1.0,
        **extra,
    }
    made = client.post("/api/materials", json=body, headers=headers)
    assert made.status_code == 201, made.text
    return made.json()


def _run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    material: Any,
    *,
    value: float,
    division: str | None = None,
    adopt: bool = True,
    label: str = "인장강도",
) -> TestRun:
    """시험 하나 + 채택된 처리 결과. **채택이 있어야 물성으로 센다**(ADR 0007)."""
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens", json={"orientation": "MD"}, headers=headers
    ).json()
    data: dict[str, Any] = {
        "specimen_id": specimen["id"],
        "test_type": "tensile",
        "conditions": "{}",
    }
    if division:
        data["division"] = division
    made = client.post(
        "/api/test-runs",
        data=data,
        files={"file": (f"{value}.csv", f"x,y\n1,{value}\n".encode())},
        headers=headers,
    )
    assert made.status_code == 202, made.text
    run = db.get(TestRun, uuid.UUID(made.json()["id"]))
    assert run is not None
    if adopt:
        result = ProcessingResult(
            test_run_id=run.id,
            source_curve_key="raw",
            scalars=[
                {"key": "tensile_strength", "label": label, "value": value, "si_unit": "Pa"}
            ],
            storage_path=f"x/{run.id}.parquet",
            row_count=1,
            sha256="0" * 64,
            byte_size=1,
            columns=[],
        )
        db.add(result)
        db.flush()
        run.adopted_result_id = result.id
    db.commit()
    return run


@pytest.fixture
def seeded(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    first = _material(client, admin_headers, "SECC")
    second = _material(client, admin_headers, "SPCC")
    _run(client, db, admin_headers, first, value=300.0, division="MX")
    _run(client, db, admin_headers, first, value=320.0, division="MX")
    _run(client, db, admin_headers, first, value=310.0, division="VD")
    _run(client, db, admin_headers, second, value=500.0, division="VD")
    # **처리 안 한 것** — 값이 없으므로 세지 않되, 몇 건이 빠졌는지 말해야 한다.
    _run(client, db, admin_headers, second, value=999.0, adopt=False)
    return {"first": first, "second": second}


class Test비교:
    def test_고른_재료만_나란히_세고_1건은_흩어짐이_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        response = client.get(
            f"/api/statistics/analysis/compare?material_ids={seeded['first']['id']}"
            f"&material_ids={seeded['second']['id']}",
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        by_name = {one["material_name"]: one for one in body["materials"]}
        secc = by_name[seeded["first"]["record_name"]]["scalars"][0]
        assert secc["count"] == 3
        assert secc["mean"] == pytest.approx(310.0)
        assert secc["sample_sd"] is not None

        spcc = by_name[seeded["second"]["record_name"]]["scalars"][0]
        # 채택 안 된 999 는 안 섞인다.
        assert spcc["count"] == 1 and spcc["mean"] == pytest.approx(500.0)
        # **1건이면 흩어짐이 없다** — 0 은 「완벽히 일정」 으로 읽힌다.
        assert spcc["sample_sd"] is None
        assert body["skipped_unadopted"] == 1

    def test_안_고르면_빈_표다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        """전체를 자동으로 세우면 94개짜리 표가 나온다."""
        body = client.get("/api/statistics/analysis/compare", headers=admin_headers).json()
        assert body["materials"] == []


class Test분포:
    def test_분류로_묶고_안_고르면_가장_많은_항목_하나(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        body = client.get(
            "/api/statistics/analysis/distribution?group_by=category", headers=admin_headers
        ).json()
        assert [one["key"] for one in body["selected"]] == ["tensile_strength"]
        groups = {one["group"]: one for one in body["groups"]}
        assert groups["Steel"]["cells"]["tensile_strength"]["count"] == 4

    def test_항목을_여럿_고르면_열이_여럿이다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        seeded: dict[str, Any],
    ) -> None:
        """「인장강도와 탄성계수가 같은 분류에서 어떻게 흩어지나」 를 한 표에서."""
        from app.modules.processing.models import ProcessingResult

        for result in db.scalars(select(ProcessingResult)):
            result.scalars = [
                *result.scalars,
                {
                    "key": "youngs_modulus",
                    "label": "탄성계수",
                    "value": 200.0,
                    "si_unit": "Pa",
                },
            ]
        db.commit()

        body = client.get(
            "/api/statistics/analysis/distribution"
            "?group_by=category&scalar=tensile_strength&scalar=youngs_modulus",
            headers=admin_headers,
        ).json()
        assert [one["key"] for one in body["selected"]] == [
            "tensile_strength",
            "youngs_modulus",
        ]
        cells = body["groups"][0]["cells"]
        assert set(cells) == {"tensile_strength", "youngs_modulus"}

    def test_2건_미만이면_상자가_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        """0 을 그리면 「일정하다」 로 읽힌다 — 없는 것과 다르다."""
        body = client.get(
            "/api/statistics/analysis/distribution?group_by=family", headers=admin_headers
        ).json()
        assert body["groups"][0]["cells"]["tensile_strength"]["count"] == 4


class Test담을_수_있는_재료:
    def test_채택된_물성이_있는_것만_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        """물성이 없는 재료를 담으면 빈 줄을 본다."""
        rows = client.get("/api/statistics/analysis/materials", headers=admin_headers).json()
        by_name = {one["material_name"]: one for one in rows}
        first = by_name[seeded["first"]["record_name"]]
        assert first["run_count"] == 3 and first["scalar_count"] == 1
        # 채택 안 된 시험만 있는 재료는 목록에 없다.
        assert by_name[seeded["second"]["record_name"]]["run_count"] == 1


class Test사양_대비:
    def test_차이가_큰_것이_위로_오고_못_견준_것은_남긴다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        seeded: dict[str, Any],
    ) -> None:
        from app.modules.materials.models import Material

        material = db.get(Material, uuid.UUID(seeded["first"]["id"]))
        assert material is not None
        material.declared_properties = [
            {"item": "인장강도", "points": [{"temperature_k": 293.15, "value_si": 200.0}]},
            # 잰 적 없는 항목 — **숨기면 「차이가 없다」 로 읽힌다.**
            {"item": "열전도도", "points": [{"temperature_k": 293.15, "value_si": 50.0}]},
        ]
        db.commit()

        body = client.get("/api/statistics/analysis/spec-gap", headers=admin_headers).json()
        assert len(body["rows"]) == 1
        row = body["rows"][0]
        assert row["item"] == "인장강도"
        assert row["declared_si"] == pytest.approx(200.0)
        assert row["measured_mean"] == pytest.approx(310.0)
        assert row["gap_ratio"] == pytest.approx(0.55)
        assert body["unmatched_items"] == ["열전도도"]


class Test추이:
    def test_해별로_접고_사업부를_계열로_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        body = client.get(
            "/api/statistics/analysis/trend?group_by=division", headers=admin_headers
        ).json()
        assert [one["key"] for one in body["series"]] == ["MX", "VD"]
        mx = body["series"][0]["points"][0]
        assert mx["count"] == 2 and mx["mean"] == pytest.approx(310.0)


class Test커버리지:
    def test_시험_수와_채택_수를_따로_센다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: dict[str, Any]
    ) -> None:
        """**올리기만 한 것과 물성이 나온 것은 다르다** — 그 차이가 남은 일이다."""
        body = client.get("/api/statistics/analysis/coverage", headers=admin_headers).json()
        assert [one["key"] for one in body["test_types"]] == ["tensile"]
        # **행은 재료가 아니라 분류다** — 94줄짜리 표에서는 「무엇을 안 쟀나」 가 안 읽힌다.
        group = next(
            one
            for one in body["groups"]
            if (one["family"], one["category"]) == ("Metal", "Steel")
        )
        assert group["material_count"] == 2
        cell = group["cells"]["tensile"]
        assert cell["run_count"] == 5 and cell["adopted_count"] == 4
        assert cell["material_count"] == 2
