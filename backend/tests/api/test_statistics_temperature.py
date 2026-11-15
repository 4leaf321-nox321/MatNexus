"""시험 온도 묶음의 후속(2026-11-15) — **사양 대비의 온도 섞임 · 반복 시편 통계의 온도 칸.**

사양 대비          선언 점 하나를 그 재료의 **모든 온도의** 잰 값 평균과 견줬다 — 23 ℃ ·
                   80 ℃ 가 섞인 평균이 선언과의 차이로 섰다. 이제 선언 점 온도 ±2 K 안의 잰
                   값만 견주고, 상온 선언이면 온도 미기재 값도 넣어 그 수를 센다.
반복 시편 통계     온도를 `curve` JSON 안에 두던 것을 정식 칸(`temperature_k`)으로. 옛 행은
                   칸이 비었을 때만 `curve` 에서 읽는다.

무는 자리는 **조용히 틀린 수**다 — 온도가 섞인 평균, 온도가 다른 통계를 같은 것으로 읽는 것.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material
from app.modules.processing.models import ProcessingResult
from app.modules.statistics import analysis
from app.modules.statistics.models import EnsembleResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType

SPEC_GAP = "/api/statistics/analysis/spec-gap"


def _material(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"TMP-{uuid.uuid4().hex[:6]}",
            "details": "AN",
            "spec_thickness": 1.0,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    material: dict[str, Any],
    *,
    value: float,
    celsius: float | None = None,
) -> TestRun:
    """시험 하나 + 채택된 처리 결과(인장강도 하나). 온도를 주면 시험 조건 `temperature`
    (°C 로 넣어 K 로 담긴다)."""
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
    if celsius is not None:
        data["conditions"] = json.dumps({"temperature": celsius})
        data["condition_units"] = json.dumps({"temperature": "degC"})
    made = client.post(
        "/api/test-runs",
        data=data,
        # 값마다 다른 파일 — 같은 원본으로 겹쳐 세지 않게.
        files={"file": (f"{uuid.uuid4().hex}.csv", f"x,y\n1,{value}\n".encode())},
        headers=headers,
    )
    assert made.status_code == 202, made.text
    run = db.get(TestRun, uuid.UUID(made.json()["id"]))
    assert run is not None
    result = ProcessingResult(
        test_run_id=run.id,
        source_curve_key="raw",
        scalars=[
            {"key": "tensile_strength", "label": "인장강도", "value": value, "si_unit": "Pa"}
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


def _declare(db: Session, material: dict[str, Any], *points: dict[str, Any]) -> None:
    found = db.get(Material, uuid.UUID(material["id"]))
    assert found is not None
    found.declared_properties = [{"item": "인장강도", "points": list(points)}]
    db.commit()


def _rows(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get(SPEC_GAP, headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.fixture
def material(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    return _material(client, admin_headers)


@pytest.fixture
def mixed(
    client: TestClient, db: Session, admin_headers: dict[str, str], material: dict[str, Any]
) -> dict[str, Any]:
    """23 ℃ 두 건(300, 300) · 80 ℃ 한 건(200) · 온도 미기재 한 건(310)."""
    for value, celsius in ((300.0, 23.0), (300.0, 23.0), (200.0, 80.0), (310.0, None)):
        _run(client, db, admin_headers, material, value=value, celsius=celsius)
    return material


# --- 사양 대비 -------------------------------------------------------------------------------


class Test사양_대비_온도:
    def test_상온_선언은_같은_온도와_미기재만_견주고_뺀_수를_센다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        mixed: dict[str, Any],
    ) -> None:
        """전에는 80 ℃ 200 까지 섞여 평균 277.5 였다 — 그 차이는 재료가 아니라 온도의
        것이다."""
        _declare(db, mixed, {"temperature_k": 296.15, "value_si": 250.0})
        [row] = _rows(client, admin_headers)["rows"]
        assert row["temperature_k"] == pytest.approx(296.15)
        # 23 ℃ 두 건 + 미기재 한 건(상온 선언이라 넣는다).
        assert row["measured_count"] == 3
        assert row["measured_mean"] == pytest.approx((300 + 300 + 310) / 3)
        assert row["measured_unknown_temperature"] == 1
        assert row["measured_other_temperature"] == 1
        assert row["gap_ratio"] == pytest.approx(((300 + 300 + 310) / 3 - 250) / 250)

    def test_상온이_아닌_선언은_미기재를_안_넣는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        mixed: dict[str, Any],
    ) -> None:
        _declare(db, mixed, {"temperature_k": 353.15, "value_si": 250.0})
        [row] = _rows(client, admin_headers)["rows"]
        assert row["temperature_k"] == pytest.approx(353.15)
        assert row["measured_count"] == 1
        assert row["measured_mean"] == pytest.approx(200.0)
        assert row["measured_unknown_temperature"] == 0
        # 23 ℃ 두 건과 미기재 한 건(상온으로 본다)을 뺐다.
        assert row["measured_other_temperature"] == 3

    def test_상온_점에_잰_값이_없으면_잰_값이_있는_온도의_점과_견준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        """20 ℃ · 80 ℃ 를 선언하고 80 ℃ 에서만 쟀으면 80 ℃ 끼리 견준다."""
        for _ in range(2):
            _run(client, db, admin_headers, material, value=200.0, celsius=80.0)
        _declare(
            db,
            material,
            {"temperature_k": 293.15, "value_si": 300.0},
            {"temperature_k": 353.15, "value_si": 250.0},
        )
        [row] = _rows(client, admin_headers)["rows"]
        assert row["temperature_k"] == pytest.approx(353.15)
        assert row["declared_si"] == pytest.approx(250.0)
        assert row["gap_ratio"] == pytest.approx(-0.2)
        assert row["measured_other_temperature"] == 0

    def test_그_온도의_잰_값이_없으면_견줄_값_없음_줄로_맨_아래에_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        mixed: dict[str, Any],
    ) -> None:
        """「못 견줌(unmatched)」 과 다르다 — 잰 값은 있는데 그 온도의 것이 없다."""
        _declare(db, mixed, {"temperature_k": 673.15, "value_si": 250.0})
        other = _material(client, admin_headers)
        _run(client, db, admin_headers, other, value=330.0)
        _declare(db, other, {"temperature_k": 293.15, "value_si": 300.0})

        body = _rows(client, admin_headers)
        assert body["unmatched_items"] == []
        first, last = body["rows"]
        assert first["material_id"] == other["id"]
        assert first["gap_ratio"] == pytest.approx(0.1)
        assert last["material_id"] == mixed["id"]
        assert last["measured_mean"] is None and last["gap_ratio"] is None
        assert last["measured_count"] == 0
        assert last["measured_other_temperature"] == 4
        assert last["temperature_k"] == pytest.approx(673.15)
        assert last["si_unit"] == "Pa"

    def test_온도_없는_선언은_상온으로_보고_그렇게_말한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        mixed: dict[str, Any],
    ) -> None:
        _declare(db, mixed, {"value_si": 250.0})
        [row] = _rows(client, admin_headers)["rows"]
        # 적힌 그대로 — 상온이라고 지어 적지 않는다(견주기는 상온으로 했다).
        assert row["temperature_k"] is None
        # 293.15 ± 2 K 에 23 ℃(296.15)는 없다 — 미기재 한 건만 견준다.
        assert row["measured_count"] == 1
        assert row["measured_mean"] == pytest.approx(310.0)
        assert row["measured_unknown_temperature"] == 1
        assert row["measured_other_temperature"] == 3


def _observation(value: float, kelvin: float | None) -> analysis.Observation:
    return analysis.Observation(
        run_id=uuid.uuid4(),
        material_id=uuid.uuid4(),
        material_name="M",
        family="Metal",
        category="Steel",
        division="MX",
        test_type_key="tensile",
        test_type_label="인장",
        orientation="MD",
        tested_at=None,
        scalar_key="tensile_strength",
        scalar_label="인장강도",
        si_unit="Pa",
        value=value,
        temperature_k=kelvin,
    )


def test_선언_점_고르기는_폭_2K_와_상온_5K_를_지킨다() -> None:
    seen = [
        _observation(1.0, 295.0),  # 상온 선언(293.15)에서 1.85 K — 든다
        _observation(2.0, 295.25),  # 2.1 K — 빠진다
        _observation(3.0, None),
    ]
    match = analysis.match_declared([{"temperature_k": 293.15, "value_si": 10.0}], seen)
    assert match is not None
    assert [one.value for one in match.measured] == [1.0, 3.0]
    assert (match.unknown_temperature, match.other_temperature) == (1, 1)

    # 상온에서 5 K 까지는 「상온 선언」 — 미기재를 넣는다. 5 K 를 넘으면 안 넣는다.
    edge = analysis.match_declared([{"temperature_k": 298.0, "value_si": 10.0}], seen)
    assert edge is not None and edge.unknown_temperature == 1
    beyond = analysis.match_declared([{"temperature_k": 298.5, "value_si": 10.0}], seen)
    assert beyond is not None and beyond.unknown_temperature == 0
    assert beyond.measured == [] and beyond.other_temperature == 3

    # 견줄 선언값(숫자 · 0 아님)이 없으면 줄이 없다.
    assert analysis.match_declared([{"temperature_k": 293.15, "value_si": 0}], seen) is None
    assert analysis.match_declared([{"value_si": True}], seen) is None


# --- 반복 시편 통계의 온도 칸 ------------------------------------------------------------


class Test반복_시편_통계_온도_칸:
    def test_저장은_칸에_하고_curve_에는_안_넣는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        for value, celsius in ((300.0, 23.0), (310.0, 23.0), (200.0, 80.0), (210.0, 80.0)):
            _run(client, db, admin_headers, material, value=value, celsius=celsius)
        saved = client.post(
            "/api/statistics/ensembles",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "temperature_k": 353.15,
            },
            headers=admin_headers,
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["temperature_k"] == pytest.approx(353.15)

        db.expire_all()
        item = db.get(EnsembleResult, uuid.UUID(saved.json()["id"]))
        assert item is not None
        assert item.temperature_k == pytest.approx(353.15)
        assert "temperature_k" not in item.curve
        # 화면과 같은 노트 — 다른 온도의 묶음이 있었다는 것까지 남는다.
        assert any("따로 묶었습니다" in note for note in item.notes)

    def test_읽기는_칸을_먼저_보고_비었을_때만_옛_curve_를_본다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
        assert tensile is not None
        material_id = uuid.UUID(material["id"])

        def stored(kelvin: float | None, curve: dict[str, Any]) -> EnsembleResult:
            return EnsembleResult(
                material_id=material_id,
                test_type_id=tensile.id,
                orientation="MD",
                temperature_k=kelvin,
                sample_count=2,
                curve=curve,
            )

        rows = {
            # v1.337.0 이 칸 없이 남긴 행(마이그레이션이 못 옮긴 경우) — curve 에서 읽는다.
            "old": stored(None, {"temperature_k": 296.15}),
            # 칸과 curve 가 다르면 칸이 이긴다.
            "both": stored(353.15, {"temperature_k": 296.15}),
            # 온도 구분 전 · 미기재 — 모름.
            "none": stored(None, {}),
        }
        db.add_all(rows.values())
        db.commit()

        listed = client.get(
            "/api/statistics/ensembles",
            params={"material_id": material["id"]},
            headers=admin_headers,
        )
        assert listed.status_code == 200, listed.text
        by_id = {one["id"]: one["temperature_k"] for one in listed.json()}
        assert by_id[str(rows["old"].id)] == pytest.approx(296.15)
        assert by_id[str(rows["both"].id)] == pytest.approx(353.15)
        assert by_id[str(rows["none"].id)] is None

    def test_미기재_묶음은_칸이_비어_있다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        for value in (300.0, 310.0):
            _run(client, db, admin_headers, material, value=value)
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
        assert saved.json()["temperature_k"] is None
        db.expire_all()
        item = db.get(EnsembleResult, uuid.UUID(saved.json()["id"]))
        assert item is not None and item.temperature_k is None
