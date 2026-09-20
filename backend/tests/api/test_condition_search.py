"""값 검색의 조건·등급 — **「80 °C 에서 잰, 믿을 만한 것」 이 답이 된다.**

무는 것이 넷이다. 전부 「조용히 틀리는」 부류다.

    조건이 한 키로 모인다        시험 canonical_key · 문헌 temperature_c/k · 선언 점의 온도
    조건 모르는 값은 안 걸린다    상온 값은 80 °C 의 답이 아니다
    사내 값에도 등급이 붙는다          표본 3 → 1 · 1~2 → 2 · 데이터시트 선언 → 1 · 추정 → 4
    단위 없는 조건은 거절한다          「80」 은 °C 인지 K 인지 모른다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestConditionField, TestRun, TestType
from app.modules.workspaces.models import Workspace

KEY = "mechanical.yield_strength"


@pytest.fixture
def yield_def(db: Session) -> CatalogDefinition:
    made = CatalogDefinition(
        mt_id=880_002,
        key=KEY,
        name="항복강도",
        domain="mechanical",
        si_unit="Pa",
        value_type="number",
    )
    db.add(made)
    db.commit()
    return made


def _measured(
    db: Session, workspace: Workspace, *, name: str, temperature_k: float, values: list[float]
) -> Material:
    """시험으로 잰 항복강도 — 시편마다 채택된 처리 결과 하나. 조건은 시험의 온도 칸에."""
    ensure_builtin_test_types(db)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    field = db.scalar(
        select(TestConditionField).where(
            TestConditionField.test_type_id == tensile.id,
            TestConditionField.key == "temperature",
        )
    )
    assert field is not None and field.canonical_key == "temperature", (
        "내장 정의가 표준 조건에 안 이어졌다"
    )

    material = Material(record_name=name, family="Metal", category="Steel", grade=name)
    db.add(material)
    db.flush()
    sample = Sample(
        workspace_id=workspace.id, material_id=material.id, seq_no=1, record_name=f"{name}_S1"
    )
    db.add(sample)
    db.flush()
    for index, value in enumerate(values, start=1):
        specimen = Specimen(
            workspace_id=workspace.id,
            sample_id=sample.id,
            seq_no=index,
            orientation="MD",
            record_name=f"{name}_MD_{index:02d}",
        )
        db.add(specimen)
        db.flush()
        run = TestRun(
            workspace_id=workspace.id,
            specimen_id=specimen.id,
            test_type_id=tensile.id,
            seq_no=1,
            record_name=f"{name}_MD_{index:02d}__TEN_01",
            conditions={"temperature": temperature_k},
        )
        db.add(run)
        db.flush()
        result = ProcessingResult(
            test_run_id=run.id,
            source_curve_key="raw",
            storage_path="test/none.parquet",
            row_count=0,
            sha256="0" * 64,
            byte_size=0,
            scalars=[{"key": "proof_stress", "value": value}],
            stages=[{"plugin": "tensile.proof_stress", "options": {"offset_strain": 0.002}}],
        )
        db.add(result)
        db.flush()
        run.adopted_result_id = result.id
    db.commit()
    return material


def _catalog(
    db: Session, *, name: str, value: float, conditions: dict[str, Any], tier: int
) -> None:
    source = db.scalar(select(CatalogSource).limit(1))
    if source is None:
        source = CatalogSource(kind="journal", title="시험용 출처")
        db.add(source)
        db.flush()
    material = CatalogMaterial(name=name, category="Steel", grade=name)
    db.add(material)
    db.flush()
    db.add(
        CatalogValue(
            material_id=material.id,
            property_key=KEY,
            value_num=value,
            unit="Pa",
            conditions=conditions,
            quality_tier=tier,
            source_id=source.id,
        )
    )
    db.commit()


def _search(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    got = client.get(
        "/api/catalog/properties/search",
        params={"q": KEY, "unit": "MPa", "min": 100, "max": 900, **params},
        headers=headers,
    )
    assert got.status_code == 200, got.text
    body: dict[str, Any] = got.json()
    return body


def _by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {one["material_name"]: one for one in body["hits"]}


class Test조건:
    def test_세계마다_다른_키가_한_조건으로_모인다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Workspace,
        yield_def: CatalogDefinition,
    ) -> None:
        _measured(
            db, workspace, name="HOT", temperature_k=353.15, values=[300e6, 310e6, 305e6]
        )
        _measured(
            db, workspace, name="ROOM", temperature_k=296.15, values=[400e6, 410e6, 405e6]
        )
        _catalog(db, name="LIT_C", value=500e6, conditions={"temperature_c": 80}, tier=2)
        _catalog(db, name="LIT_K", value=520e6, conditions={"temperature_k": 355.0}, tier=2)
        _catalog(db, name="LIT_NONE", value=540e6, conditions={}, tier=2)

        body = _search(
            client,
            admin_headers,
            condition="temperature",
            condition_unit="degC",
            condition_near=80,
        )
        names = set(_by_name(body))
        # 시험(칸 이름 temperature → canonical) · 문헌 °C · 문헌 K 가 같은 답에 선다.
        assert {"HOT", "LIT_C", "LIT_K"} <= names, names
        # 상온 시험과 조건 없는 문헌값은 **80 °C 의 답이 아니다.**
        assert "ROOM" not in names and "LIT_NONE" not in names
        assert any("조건 온도" in note for note in body["notes"])

        # 조건 없이 물으면 전부 나온다 — 조건은 좁히는 것이지 숨기는 것이 아니다.
        assert {"HOT", "ROOM", "LIT_C", "LIT_K", "LIT_NONE"} <= set(
            _by_name(_search(client, admin_headers))
        )

    def test_단위_없는_조건은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], yield_def: CatalogDefinition
    ) -> None:
        refused = client.get(
            "/api/catalog/properties/search",
            params={
                "q": KEY,
                "unit": "MPa",
                "min": 100,
                "max": 900,
                "condition": "temperature",
                "condition_near": 80,
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert "condition_unit" in refused.json()["error"]["message"]
        unknown = client.get(
            "/api/catalog/properties/search",
            params={
                "q": KEY,
                "unit": "MPa",
                "min": 100,
                "max": 900,
                "condition": "moon_phase",
                "condition_unit": "K",
                "condition_near": 1,
            },
            headers=admin_headers,
        )
        assert (
            unknown.status_code == 422 and "temperature" in unknown.json()["error"]["message"]
        )


class Test등급:
    def test_사내_값에_등급이_붙고_등급으로_거른다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Workspace,
        yield_def: CatalogDefinition,
    ) -> None:
        _measured(
            db, workspace, name="THREE", temperature_k=296.15, values=[300e6, 310e6, 305e6]
        )
        _measured(db, workspace, name="ONE", temperature_k=296.15, values=[400e6])
        _catalog(db, name="LIT4", value=500e6, conditions={}, tier=4)

        hits = _by_name(_search(client, admin_headers))
        assert hits["THREE"]["quality_tier"] == 1 and hits["THREE"]["world"] == "measured"
        assert hits["ONE"]["quality_tier"] == 2
        assert hits["LIT4"]["quality_tier"] == 4

        good = _by_name(_search(client, admin_headers, min_tier=1))
        assert set(good) == {"THREE"}
        fair = _by_name(_search(client, admin_headers, min_tier=2))
        assert set(fair) == {"THREE", "ONE"}

    def test_세계를_고른다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Workspace,
        yield_def: CatalogDefinition,
    ) -> None:
        _measured(db, workspace, name="MEAS", temperature_k=296.15, values=[300e6])
        _catalog(db, name="LIT", value=500e6, conditions={}, tier=2)
        only_measured = _by_name(_search(client, admin_headers, origins="measured"))
        assert set(only_measured) == {"MEAS"}
        only_catalog = _by_name(_search(client, admin_headers, origins="catalog"))
        assert set(only_catalog) == {"LIT"}
        bad = client.get(
            "/api/catalog/properties/search",
            params={"q": KEY, "unit": "MPa", "min": 100, "max": 900, "origins": "rumor"},
            headers=admin_headers,
        )
        assert bad.status_code == 422


class Test근처:
    """**「근처」 로 물었으면 가까운 순이다.**

    실측(기준선 5차, 2026-09-20): 「탄성계수 200 GPa 근처」 를 `near=200, limit=20` 으로
    물으니 180~220 창의 **아래쪽 20개**가 왔다 — 값 오름차순이라서다. AI 는 200 근처를 못
    보고 창을 195~205, 199~201 로 좁혀 세 번 더 불렀다. 네 문항이 그렇게 예산을 넘겼다.
    """

    def test_near_는_가까운_것부터_주고_limit_이_먼_것을_자른다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        yield_def: CatalogDefinition,
    ) -> None:
        # 창(±10 %) 안에 셋: 아래쪽 끝·한가운데·위쪽. limit=2 면 **가운데와 가까운 하나**.
        _catalog(db, name="LOW", value=182e6, conditions={}, tier=2)
        _catalog(db, name="MID", value=201e6, conditions={}, tier=2)
        _catalog(db, name="HIGH", value=215e6, conditions={}, tier=2)
        got = client.get(
            "/api/catalog/properties/search",
            params={"q": KEY, "unit": "MPa", "near": 200, "limit": 2},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        names = [one["material_name"] for one in got.json()["hits"]]
        assert names == ["MID", "HIGH"], names  # 값 오름차순이었으면 LOW, MID 가 왔다

    def test_범위로_물으면_전처럼_값_순이다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        yield_def: CatalogDefinition,
    ) -> None:
        _catalog(db, name="B", value=300e6, conditions={}, tier=2)
        _catalog(db, name="A", value=200e6, conditions={}, tier=2)
        names = [one["material_name"] for one in _search(client, admin_headers)["hits"]]
        assert names == ["A", "B"]


def test_선언_물성의_등급은_출처가_정한다() -> None:
    from app.shared import tiers

    assert tiers.declared_tier("millsheet") == 1
    assert tiers.declared_tier("datasheet") == 1
    assert tiers.declared_tier("standard") == 2
    assert tiers.declared_tier("literature") == 3
    assert tiers.declared_tier("estimate") == 4
    # 모르는 출처는 좋게 봐 주지 않는다.
    assert tiers.declared_tier("") == 4 and tiers.declared_tier(None) == 4
    assert tiers.measured_tier(3) == 1 and tiers.measured_tier(2) == 2


def test_조건_칸_정의가_표준_조건에_이어진다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """부서가 `temp` 라고 적어도 온도로 잇고, 모르는 표준 키는 거절한다."""
    made = client.post(
        "/api/test-types",
        json={
            "key": "hot_tensile",
            "label": "고온 인장",
            "abbr": "HT",
            "channels": [
                {
                    "key": "strain",
                    "label": "변형률",
                    "dimension": "dimensionless",
                    "si_unit": "1",
                },
                {"key": "stress", "label": "응력", "dimension": "stress", "si_unit": "Pa"},
            ],
            "conditions": [
                {
                    "key": "temp",
                    "label": "온도",
                    "value_type": "number",
                    "dimension": "temperature",
                    "si_unit": "K",
                },
                {
                    "key": "rate",
                    "label": "속도",
                    "value_type": "number",
                    "dimension": "dimensionless",
                    "si_unit": "1",
                },
                {"key": "clamp", "label": "지그", "value_type": "text"},
            ],
        },
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    fields = {one["key"]: one for one in made.json()["conditions"]}
    assert fields["temp"]["canonical_key"] == "temperature"
    # `rate` 는 변형률속도의 별칭이지만 저장 단위가 1/s 가 아니다 — 이름만 같은 것은 안 잇는다.
    assert fields["rate"]["canonical_key"] is None
    assert fields["clamp"]["canonical_key"] is None

    refused = client.post(
        "/api/test-types",
        json={
            "key": "bad_type",
            "label": "잘못",
            "abbr": "BAD",
            "channels": [
                {
                    "key": "strain",
                    "label": "변형률",
                    "dimension": "dimensionless",
                    "si_unit": "1",
                },
                {"key": "stress", "label": "응력", "dimension": "stress", "si_unit": "Pa"},
            ],
            "conditions": [
                {
                    "key": "x",
                    "label": "x",
                    "value_type": "number",
                    "canonical_key": "moon_phase",
                }
            ],
        },
        headers=admin_headers,
    )
    assert refused.status_code == 422 and "moon_phase" in refused.json()["error"]["message"]

    listed = client.get("/api/test-types/standard-conditions")
    assert listed.status_code == 200
    assert {one["key"] for one in listed.json()} >= {"temperature", "strain_rate", "frequency"}


def test_지도에_표준_조건이_실린다(client: TestClient, admin_headers: dict[str, str]) -> None:
    got = client.get("/api/ontology", headers=admin_headers)
    assert got.status_code == 200
    keys = {one["key"] for one in got.json()["conditions"]}
    assert "temperature" in keys
