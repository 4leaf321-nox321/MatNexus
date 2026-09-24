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
            {"item": "열전도율", "points": [{"temperature_k": 293.15, "value_si": 50.0}]},
        ]
        db.commit()

        body = client.get("/api/statistics/analysis/spec-gap", headers=admin_headers).json()
        assert len(body["rows"]) == 1
        row = body["rows"][0]
        assert row["item"] == "인장강도"
        assert row["declared_si"] == pytest.approx(200.0)
        assert row["measured_mean"] == pytest.approx(310.0)
        assert row["gap_ratio"] == pytest.approx(0.55)
        assert body["unmatched_items"] == ["열전도율"]


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


class Test카드_항목:
    """재료 x 카드 항목란 — **어느 재료에서 무엇까지 볼 수 있나.**

    무는 자리는 「표가 나온다」 가 아니라 **상태를 섞지 않는 것**이다. 초안만 있는 것을
    확정으로, 채택 전 시험을 「시험 있음」 으로, 이름만 있는 항목란을 「있다」 로 세면 그
    칸은 조용히 틀린다 — 그 표를 보고 다른 시스템에 넘길 재료를 고른다. 그리고 **요약 ·
    전체 · 칸이 같은 판정**이어야 한다: 요약의 「점탄성 1」 을 누르면 전체에 한 줄이 떠야
    한다.
    """

    @pytest.fixture
    def carded(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        seeded: dict[str, Any],
    ) -> dict[str, Any]:
        from app.modules.fitting.models import PropertyCard

        first = uuid.UUID(seeded["first"]["id"])  # Metal/Steel · 채택된 인장 3건
        second = uuid.UUID(seeded["second"]["id"])  # Metal/Steel · 채택 1건 + 채택 전 1건
        bare = _material(client, admin_headers, "SGCC")  # Metal/Steel · 아무것도 없다
        polymer = _material(client, admin_headers, "PPH", family="Polymer", category="PP")
        db.add_all(
            [
                PropertyCard(
                    material_id=first,
                    label="확정 카드",
                    status="published",
                    blocks={
                        "elastic": {
                            "values": {
                                "youngs_modulus": 2.0e11,
                                "youngs_modulus_source": "measured",
                                "density": None,
                            }
                        },
                        "table": {
                            "values": {},
                            "rows": [
                                {"strain": 0.0, "stress": 2.0e8},
                                {"strain": 0.1, "stress": 3.0e8},
                            ],
                        },
                        # 이름만 있는 항목란 — 볼 것이 없으니 「있다」 가 아니다.
                        "hardening": {"values": {}, "rows": []},
                        # 값에 딸린 말만 있는 항목란도 볼 것이 없다.
                        "thermal": {"values": {"specific_heat_source": "measured"}},
                        # 레지스트리가 모르는 항목란 — 빼면 「그 항목이 없다」 로 읽힌다.
                        "gone_extension": {"values": {"x": 1.0}},
                    },
                ),
                PropertyCard(
                    material_id=first,
                    label="초안 카드",
                    status="draft",
                    blocks={
                        "elastic": {"values": {"youngs_modulus": 1.9e11}},
                        "viscoelastic": {"values": {"instantaneous_pa": 1.0e9}},
                    },
                ),
                PropertyCard(
                    material_id=second,
                    label="내린 카드",
                    status="deprecated",
                    blocks={"thermal": {"values": {"specific_heat": 500.0}}},
                ),
                PropertyCard(
                    material_id=uuid.UUID(polymer["id"]),
                    label="PP 점탄성",
                    status="draft",
                    blocks={"viscoelastic": {"values": {}, "rows": [{"g": 1.0, "tau": 1.0}]}},
                ),
            ]
        )
        db.commit()
        return {"first": first, "second": second, "bare": bare, "polymer": polymer}

    def test_요약은_분류가_줄이고_상태별_재료_수를_센다(
        self, client: TestClient, admin_headers: dict[str, str], carded: dict[str, Any]
    ) -> None:
        response = client.get("/api/statistics/analysis/card-items", headers=admin_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        groups = {(one["family"], one["category"]): one for one in body["groups"]}
        steel = groups[("Metal", "Steel")]
        # **분류의 재료 수는 칸이 없는 재료까지 센다** — SGCC 도 든다.
        assert steel["material_count"] == 3
        cells = steel["cells"]
        # 확정이 하나라도 있으면 확정. 카드가 없는 SPCC 는 채택된 인장이 있어 「시험 있음」.
        assert cells["elastic"] == {"published": 1, "draft": 0, "deprecated": 0, "source": 1}
        # 이름만 있는 경화식은 카드로 안 센다 — 둘 다 채택된 인장이 있으니 시험 있음.
        assert cells["hardening"] == {"published": 0, "draft": 0, "deprecated": 0, "source": 2}
        # 값에 딸린 말뿐인 열물성은 카드로 안 센다 — 남는 것은 SPCC 의 사용 중지 카드.
        assert cells["thermal"] == {"published": 0, "draft": 0, "deprecated": 1, "source": 0}
        assert cells["viscoelastic"]["draft"] == 1
        assert groups[("Polymer", "PP")]["cells"]["viscoelastic"]["draft"] == 1
        # 사용 중지 카드뿐이어도 「카드가 있었던」 재료로 센다 — 둘 다 카드 쪽이다.
        assert steel["card_materials"] == 2 and steel["source_only_materials"] == 0

        columns = {one["key"]: one for one in body["columns"]}
        # **열은 빼지 않는다** — 아무 재료에도 없는 항목란이 「아직 아무도 안 만든 것」 이다.
        assert columns["hyperelastic"]["card_materials"] == 0
        assert columns["viscoelastic"]["card_materials"] == 2
        assert columns["elastic"]["published_materials"] == 1
        assert columns["gone_extension"]["registered"] is False
        assert columns["elastic"]["tests"] and columns["thermal"]["tests"] == []
        assert body["material_total"] == 4
        assert body["card_material_count"] == 3
        assert body["source_only_count"] == 0

    def test_전체는_서버가_거르고_자른다(
        self, client: TestClient, admin_headers: dict[str, str], carded: dict[str, Any]
    ) -> None:
        def rows(query: str) -> dict[str, Any]:
            got = client.get(
                f"/api/statistics/analysis/card-items/materials?{query}", headers=admin_headers
            )
            assert got.status_code == 200, got.text
            return dict(got.json())

        # 기본은 카드가 든 칸이 있는 재료만 — 아무것도 없는 SGCC 는 안 뜬다.
        base = rows("")
        names = [one["material_name"] for one in base["rows"]]
        assert carded["bare"]["record_name"] not in names
        assert base["total"] == 3
        first = next(one for one in base["rows"] if one["material_id"] == str(carded["first"]))
        # **보이는 칸만 싣는다** — 시험 있음인 경화식은 켜기 전에는 없다. 값은 칸을 누를 때.
        assert "hardening" not in first["cells"]
        assert first["cells"]["elastic"] == {
            "state": "published",
            "card_count": 2,
            "tests": True,
            "declared": False,
        }

        shown = rows("with_sources=true")
        first = next(
            one for one in shown["rows"] if one["material_id"] == str(carded["first"])
        )
        assert first["cells"]["hardening"] == {
            "state": "source",
            "card_count": 0,
            "tests": True,
            "declared": False,
        }

        # 요약의 칸을 누르면 오는 길 — 분류 + 항목. 요약이 센 수와 같아야 한다.
        drilled = rows("family=Metal&category=Steel&item=viscoelastic")
        assert [one["material_id"] for one in drilled["rows"]] == [str(carded["first"])]
        # 열은 **거른 재료 가운데서** 센다.
        columns = {one["key"]: one for one in drilled["columns"]}
        assert columns["viscoelastic"]["card_materials"] == 1

        # 자른다 — 거른 뒤의 수는 그대로 말한다.
        page = rows("limit=1&offset=1")
        assert page["total"] == 3 and len(page["rows"]) == 1 and page["offset"] == 1
        assert rows("q=pph")["total"] == 1

        too_many = client.get(
            "/api/statistics/analysis/card-items/materials?limit=100000", headers=admin_headers
        )
        assert too_many.status_code == 422

    def test_칸은_누를_때_값을_준다(
        self, client: TestClient, admin_headers: dict[str, str], carded: dict[str, Any]
    ) -> None:
        def cell(material: uuid.UUID | str, item: str) -> Any:
            return client.get(
                f"/api/statistics/analysis/card-items/cell?material_id={material}&item={item}",
                headers=admin_headers,
            )

        got = cell(carded["first"], "elastic")
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["state"] == "published"
        # 확정 · 초안 차례. 든 값만 항목란이 붙인 이름으로 — 빈 밀도와 `_source` 는 빼고.
        assert [one["status"] for one in body["cards"]] == ["published", "draft"]
        assert body["cards"][0]["values"] == [
            {"label": "탄성계수", "value": pytest.approx(2.0e11), "si_unit": "Pa"}
        ]
        assert body["tests"][0]["adopted_count"] == 3

        # 표는 **줄 수만** — 수천 점을 나르지 않는다.
        table = cell(carded["first"], "table").json()
        assert table["cards"][0]["row_count"] == 2
        assert "rows" not in table["cards"][0]

        # **채택 전 시험은 안 센다** — 채택 1건 + 채택 전 1건에서 1.
        other = cell(carded["second"], "elastic").json()
        assert other["state"] == "source" and other["cards"] == []
        assert other["tests"][0]["adopted_count"] == 1

        # 아무것도 없는 칸 · 없는 재료는 404 — 빈 칸을 「있다」 로 답하지 않는다.
        assert cell(carded["bare"]["id"], "elastic").status_code == 404
        assert cell(uuid.uuid4(), "elastic").status_code == 404

    def test_선언_물성은_그_칸으로_갈_값으로_보인다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
    ) -> None:
        """카드가 없어도 **적어 둔 값이 갈 칸**이 있으면 선언 카드를 만들 수 있다 — 요약 ·
        전체는 그 칸을 「선언 있음」 으로 세고, 칸을 누르면 값이 칸 이름과 함께 온다."""
        from app.modules.catalog.ontology_models import PropertyLink
        from app.modules.vocabulary import services as vocabulary_services
        from app.modules.vocabulary.models import Vocabulary
        from matcore import cards
        from matcore.cards import BlockSpec
        from matcore.registry import Produced

        key = "local.mechanical.card_item_probe"
        cards.load_builtin()
        cards.install(
            BlockSpec(
                key="card_item_probe",
                label="시험용 항목란",
                help="",
                produces=(Produced(key="probe", label="탐침", si_unit="1", property_key=key),),
                order=200,
            )
        )
        try:
            axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
            assert axis is not None
            term = vocabulary_services.resolve_or_create(
                db, axis, "탐침 지수", created_by_id=None
            )
            assert term is not None
            term.attributes = {"dimension": "dimensionless"}
            db.add(PropertyLink(property_key=key, term_id=term.id, kind="exact"))
            db.commit()

            material = _material(client, admin_headers, "PROBE")
            stated = client.patch(
                f"/api/materials/{material['id']}",
                json={
                    "declared_properties": [
                        {
                            "item": "탐침 지수",
                            "points": [{"value": 6.0}],
                            "source": "standard",
                            "reference": "KS D 3512",
                        }
                    ]
                },
                headers=admin_headers,
            )
            assert stated.status_code == 200, stated.text

            summary = client.get(
                "/api/statistics/analysis/card-items", headers=admin_headers
            ).json()
            steel = next(
                one
                for one in summary["groups"]
                if (one["family"], one["category"]) == ("Metal", "Steel")
            )
            assert steel["cells"]["card_item_probe"]["source"] == 1
            assert summary["source_only_count"] == 1

            listed = client.get(
                "/api/statistics/analysis/card-items/materials?with_sources=true"
                "&item=card_item_probe",
                headers=admin_headers,
            ).json()
            assert [one["material_id"] for one in listed["rows"]] == [material["id"]]

            cell = client.get(
                "/api/statistics/analysis/card-items/cell"
                f"?material_id={material['id']}&item=card_item_probe",
                headers=admin_headers,
            ).json()
            assert cell["state"] == "source"
            assert cell["cards"] == [] and cell["tests"] == []
            assert cell["declared"] == [
                {"label": "탐침", "value": pytest.approx(6.0), "si_unit": "1"}
            ]
        finally:
            cards.uninstall("card_item_probe")
