"""목록 찾기 — **재료·시험 목록이 전체 검색처럼 찾고, 이름 말고 다른 조건으로도 좁힌다.**

2026-09-29 지적: 「상단의 전체 검색처럼 재료·시험 검색도 강화 · 이름·별칭·Grade 말고도
다른 조건으로」. 무는 것:

    일치 · 포함 · 비슷      「비슷」 은 오타까지 걸고, 가까운 순으로 서고, 줄마다 이유가 붙는다
    뜻으로                  재료를 뜻으로 찾고, 시험은 그 재료의 뜻으로 걸린다(mock 배관)
    이름 밖의 말            용도 · 제조사(별칭까지) · 로트 · 시험 종류 이름을 찾기 상자가 본다
    조건 칸                 두께 범위 · 시험 종류 · 카드 · 등록일 · 시험일 · 장비 · 조건 범위
    없는 값은 0건           거르려고 눌렀는데 늘어나면 안 된다
    내보내기는 목록과 같다   같은 조건 → 같은 재료
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_semantic_search import semantic_off, semantic_ready  # noqa: F401  (픽스처)

from app.jobs import kinds
from app.jobs.models import Job
from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.search.jobs import index_materials
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.modules.workspaces.models import Workspace
from app.shared import semantic

SECC = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "MDOI",
    "spec_thickness": 1.0,
    "spec_thickness_unit": "mm",
}


def _material(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    made = client.post("/api/materials", json={**SECC, **overrides}, headers=headers)
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _sample(
    client: TestClient, headers: dict[str, str], material_id: str, **fields: Any
) -> dict[str, Any]:
    made = client.post(f"/api/materials/{material_id}/samples", json=fields, headers=headers)
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _materials(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    got = client.get("/api/materials", params=params, headers=headers)
    assert got.status_code == 200, got.text
    body: dict[str, Any] = got.json()
    return body


def _names(body: dict[str, Any]) -> list[str]:
    return [one["record_name"] for one in body["items"]]


def _runs(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    got = client.get("/api/test-runs", params=params, headers=headers)
    assert got.status_code == 200, got.text
    body: dict[str, Any] = got.json()
    return body


def _run(
    db: Session,
    workspace: Workspace,
    *,
    name: str,
    conditions: dict[str, Any] | None = None,
    tested_at: datetime | None = None,
    instrument: str | None = None,
    source_filename: str | None = None,
    material: Material | None = None,
) -> TestRun:
    """시험 하나 — 재료·시료·시편을 곧장 만든다(업로드·파싱은 여기서 볼 것이 아니다)."""
    ensure_builtin_test_types(db)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    if material is None:
        material = Material(record_name=name, family="Metal", category="Steel", grade=name)
        db.add(material)
        db.flush()
    sample = Sample(
        workspace_id=workspace.id,
        material_id=material.id,
        seq_no=1,
        record_name=f"{name}_S{datetime.now(UTC).timestamp():.0f}",
    )
    db.add(sample)
    db.flush()
    specimen = Specimen(
        workspace_id=workspace.id,
        sample_id=sample.id,
        seq_no=1,
        orientation="MD",
        record_name=f"{name}_MD_01",
    )
    db.add(specimen)
    db.flush()
    run = TestRun(
        workspace_id=workspace.id,
        specimen_id=specimen.id,
        test_type_id=tensile.id,
        seq_no=1,
        record_name=f"{name}_MD_01__TEN_01",
        conditions=conditions or {},
        tested_at=tested_at,
        instrument=instrument,
        source_filename=source_filename,
    )
    db.add(run)
    db.commit()
    return run


# --- 재료: 세 방식 ------------------------------------------------------------------


#: **뜻 검색은 끈다.** 개발 `.env` 가 `ollama` 라 켜 두면 시험이 사람 기계의 엔진에 기댄다
#: (`test_semantic_search.semantic_off` 의 사연). 뜻은 `Test뜻으로_찾기` 가 mock 으로 잰다.
@pytest.mark.usefixtures("semantic_off")
class Test재료_세_방식:
    def test_일치는_이름_전체가_같아야_한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        first = _material(client, admin_headers)  # SECC_MDOI_1.0
        _material(client, admin_headers, spec_thickness=1.2)

        exact = _materials(client, admin_headers, q="secc_mdoi_1.0", mode="exact")
        assert _names(exact) == ["SECC_MDOI_1.0"], "대소문자만 무시하고 통째로 같아야 한다"

        assert _materials(client, admin_headers, q="SECC", mode="exact")["total"] == 0
        # **밑줄은 글자다.** 와일드카드로 새면 `SECC_MDOI_1_0` 이 `SECC_MDOI_1.0` 에 걸린다.
        assert _materials(client, admin_headers, q="SECC_MDOI_1_0", mode="exact")["total"] == 0
        # 번호도 정확히 — 패딩 없이 쳐도 된다.
        number = int(str(first["code"]).split("-")[1])
        by_code = _materials(client, admin_headers, q=f"M-{number}", mode="exact")
        assert _names(by_code) == ["SECC_MDOI_1.0"]

    def test_비슷은_오타도_찾고_가까운_순으로_서며_이유가_붙는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _material(client, admin_headers)  # SECC_MDOI_1.0 — 먼저 만든다
        _material(client, admin_headers, spec_thickness=1.2)  # 나중 것이 등록순으로는 위
        _material(client, admin_headers, grade="AL5052", details=None, spec_thickness=2.0)

        # 영문 O 와 숫자 0 — 「포함」 으로는 안 걸린다.
        assert _materials(client, admin_headers, q="SECC_MDOI_1.O")["total"] == 0
        typo = _materials(client, admin_headers, q="SECC_MDOI_1.O", mode="similar")
        assert "SECC_MDOI_1.0" in _names(typo)
        assert "AL5052_-_2.0" not in _names(typo)
        assert all(one["matched"] == "similar" for one in typo["items"])

        # **가까운 순이다.** 등록순이면 1.2 가 위에 선다 — 정확히 맞은 것이 먼저여야 한다.
        near = _materials(client, admin_headers, q="SECC_MDOI_1.0", mode="similar")
        assert _names(near)[0] == "SECC_MDOI_1.0"
        assert near["items"][0]["matched"] == "contains"
        assert near["items"][1]["record_name"] == "SECC_MDOI_1.2"
        assert near["items"][1]["matched"] == "similar"

        # 「포함」 에는 이유를 안 붙인다 — 전부 같은 이유다.
        plain = _materials(client, admin_headers, q="SECC")
        assert all(one["matched"] is None for one in plain["items"])

    def test_모르는_방식은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.get(
            "/api/materials", params={"q": "SECC", "mode": "fuzzy"}, headers=admin_headers
        )
        assert got.status_code == 422, got.text
        assert got.json()["error"]["code"] == "MNX-MATERIALS-0039"


# --- 재료: 찾기 상자가 이름 밖의 말을 본다 ------------------------------------------


class Test재료_이름_밖의_말:
    def test_용도로_찾고_이름과_AND_로_묶인다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _material(client, admin_headers, applied_products=["범퍼"])
        _material(client, admin_headers, grade="AL5052", details=None, applied_parts=["후드"])

        assert _names(_materials(client, admin_headers, q="범퍼")) == ["SECC_MDOI_1.0"]
        assert _names(_materials(client, admin_headers, q="후드")) == ["AL5052_-_1.0"]
        assert _materials(client, admin_headers, q="SECC 범퍼")["total"] == 1
        assert _materials(client, admin_headers, q="AL5052 범퍼")["total"] == 0, (
            "낱말 조건이 OR 로 샜다"
        )

    def test_제조사는_기준정보_별칭으로도_찾는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        steel = _material(client, admin_headers)
        _material(client, admin_headers, grade="AL5052", details=None)
        _sample(client, admin_headers, steel["id"], manufacturer="포스코")

        assert _names(_materials(client, admin_headers, q="포스코")) == ["SECC_MDOI_1.0"]
        assert _materials(client, admin_headers, q="POSCO")["total"] == 0

        term = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "포스코"},
            headers=admin_headers,
        ).json()["items"][0]
        added = client.post(
            f"/api/vocabularies/manufacturer/terms/{term['id']}/aliases",
            json={"alias": "POSCO"},
            headers=admin_headers,
        )
        assert added.status_code == 201, added.text

        # **별칭은 「같은 회사」 라는 뜻이다** — 검색도 그것을 알아야 한다.
        assert _names(_materials(client, admin_headers, q="posco")) == ["SECC_MDOI_1.0"]
        assert _names(_materials(client, admin_headers, maker="POSCO")) == ["SECC_MDOI_1.0"]

    def test_로트로_찾는다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        steel = _material(client, admin_headers)
        _material(client, admin_headers, grade="AL5052", details=None)
        _sample(client, admin_headers, steel["id"], lot_no="L2409-77")

        assert _names(_materials(client, admin_headers, q="L2409")) == ["SECC_MDOI_1.0"]
        assert _names(_materials(client, admin_headers, lot="2409-7")) == ["SECC_MDOI_1.0"]


# --- 재료: 조건 칸 --------------------------------------------------------------------


@pytest.mark.usefixtures("semantic_off")
class Test재료_조건_칸:
    def test_두께_범위는_사람_단위로_받고_끝값을_포함한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        for thickness in (1.0, 1.2, 2.0):
            _material(client, admin_headers, spec_thickness=thickness)

        middle = _materials(
            client, admin_headers, thickness_min=1.1, thickness_max=2.0, thickness_unit="mm"
        )
        assert sorted(_names(middle)) == ["SECC_MDOI_1.2", "SECC_MDOI_2.0"]
        # 끝값 — `1.2 * 0.001` 의 부동소수 꼬리에 걸려 빠지면 안 된다.
        just = _materials(
            client, admin_headers, thickness_min=1.2, thickness_max=1.2, thickness_unit="mm"
        )
        assert _names(just) == ["SECC_MDOI_1.2"]

        # **차원이 다른 단위는 거절한다** — 1 kg 을 두께로 읽으면 조용히 틀린다.
        wrong = client.get(
            "/api/materials",
            params={"thickness_min": 1, "thickness_unit": "kg"},
            headers=admin_headers,
        )
        assert wrong.status_code == 422, wrong.text

    def test_용도_제조사_로트_칸은_없는_값이면_0건이다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        steel = _material(client, admin_headers, applied_products=["범퍼"])
        _material(client, admin_headers, grade="AL5052", details=None)
        _sample(client, admin_headers, steel["id"], manufacturer="현대제철", lot_no="H-001")

        assert _names(_materials(client, admin_headers, use="범퍼")) == ["SECC_MDOI_1.0"]
        assert _names(_materials(client, admin_headers, maker="현대")) == ["SECC_MDOI_1.0"]
        assert _names(_materials(client, admin_headers, lot="H-001")) == ["SECC_MDOI_1.0"]
        for field in ("use", "maker", "lot"):
            got = _materials(client, admin_headers, **{field: "없는값zz"})
            assert got["total"] == 0, f"{field} 가 없는 값인데 {got['total']}건이 나왔다"

    def test_시험_종류가_있는_재료만(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        _run(db, workspace, name="TESTED")
        db.add(Material(record_name="UNTESTED", family="Metal", category="Steel", grade="U"))
        db.commit()

        assert _names(_materials(client, admin_headers, test_type="tensile")) == ["TESTED"]
        assert _materials(client, admin_headers, test_type="없는종류")["total"] == 0

    def test_카드로_거른다_폐기는_없는_것으로(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
    ) -> None:
        made: dict[str, Material] = {}
        for name in ("PUB", "DRAFT", "DEPRECATED", "NONE"):
            made[name] = Material(
                record_name=name, family="Metal", category="Steel", grade=name
            )
            db.add(made[name])
        db.flush()
        for name, status in (
            ("PUB", "published"),
            ("DRAFT", "draft"),
            ("DEPRECATED", "deprecated"),
        ):
            db.add(PropertyCard(material_id=made[name].id, label=name, status=status))
        db.commit()

        assert _names(_materials(client, admin_headers, card="published")) == ["PUB"]
        assert sorted(_names(_materials(client, admin_headers, card="any"))) == [
            "DRAFT",
            "PUB",
        ]
        assert sorted(_names(_materials(client, admin_headers, card="none"))) == [
            "DEPRECATED",
            "NONE",
        ]
        bad = client.get("/api/materials", params={"card": "some"}, headers=admin_headers)
        assert bad.status_code == 422

    def test_물성_값_범위로_잰_값과_선언_값을_거른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        """「항복강도 250 MPa 이상인 재료」(2026-10-04). 시험으로 잰 값은 **채택된 것만**,
        선언 값은 기본 항목 「항복강도」 로 이어진 것을 본다. 단위가 없으면 거절한다."""
        key = "mechanical.yield_strength"
        if db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key)) is None:
            db.add(
                CatalogDefinition(
                    mt_id=990_001,
                    key=key,
                    name="항복강도",
                    domain="mechanical",
                    si_unit="Pa",
                    value_type="number",
                )
            )
        ensure_builtin_property_items(db)
        db.commit()
        ensure_builtin_property_links(db)
        db.commit()

        def result(run: TestRun, value: float) -> ProcessingResult:
            made = ProcessingResult(
                test_run_id=run.id,
                source_curve_key="raw",
                scalars=[{"key": "proof_stress", "label": "항복강도", "value": value}],
                storage_path="none",
                row_count=0,
                sha256="0" * 64,
                byte_size=0,
            )
            db.add(made)
            db.flush()
            return made

        measured = _run(db, workspace, name="MEASURED")
        measured.adopted_result_id = result(measured, 300e6).id
        loose = _run(db, workspace, name="LOOSE")
        result(loose, 300e6)  # 돌려만 보고 채택 안 한 값은 그 시험의 물성이 아니다
        db.commit()
        declared = _material(client, admin_headers, grade="DECLARED", details=None)
        saved = client.patch(
            f"/api/materials/{declared['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "항복강도",
                        "points": [{"value": 260}],
                        "input_unit": "MPa",
                        "source": "literature",
                        "reference": "핸드북",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text

        def names(**params: Any) -> list[str]:
            return sorted(_names(_materials(client, admin_headers, value_key=key, **params)))

        both = ["DECLARED_-_1.0", "MEASURED"]
        assert names(value_unit="MPa", value_min=250) == both
        assert names(value_unit="MPa", value_min=270) == ["MEASURED"]
        assert names(value_unit="MPa", value_max=270) == ["DECLARED_-_1.0"]
        # 같은 범위를 SI 로 물어도 같다 — 단위는 환산된다.
        assert names(value_unit="Pa", value_min=250e6) == both
        assert names(value_unit="MPa", value_min=400) == []

        # **단위 없이 「250」 은 거절한다** — 그대로 걸면 250 Pa 이상이 다 걸린다.
        bare = client.get(
            "/api/materials",
            params={"value_key": key, "value_min": 250},
            headers=admin_headers,
        )
        assert bare.status_code == 422, bare.text
        assert bare.json()["error"]["code"] == "MNX-CATALOG-0067"

    def test_등록일로_거르고_끝날은_그날_끝까지(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        early = _material(client, admin_headers)
        late = _material(client, admin_headers, spec_thickness=1.2)
        # 정오 — 서울과 UTC 에서 같은 날이다(CI 의 DB 는 UTC 다).
        for one, when in (
            (early, datetime(2026, 1, 15, 3, tzinfo=UTC)),
            (late, datetime(2026, 3, 1, 3, tzinfo=UTC)),
        ):
            db.execute(
                update(Material).where(Material.id == one["id"]).values(created_at=when)
            )
        db.commit()

        after = _materials(client, admin_headers, registered_from="2026-02-01")
        assert _names(after) == ["SECC_MDOI_1.2"]
        until = _materials(client, admin_headers, registered_to="2026-01-15")
        assert _names(until) == ["SECC_MDOI_1.0"], "끝날에 올린 것이 빠졌다"

    def test_엔진이_꺼져_있으면_색인_작업을_안_넣는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """할 일 없는 작업이 큐에 쌓이면 진짜 실패가 묻힌다."""
        _material(client, admin_headers)
        queued = db.scalar(select(Job).where(Job.kind == kinds.SEARCH_INDEX_MATERIALS))
        assert queued is None

    def test_내보내기도_같은_조건으로_거른다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**화면에서 본 것과 받아 간 파일이 같아야 한다** — 두 라우트가 한 벌을 쓴다."""
        _material(client, admin_headers, applied_products=["범퍼"])
        _material(client, admin_headers, grade="AL5052", details=None)

        got = client.get(
            "/api/materials/export",
            params={"use": "범퍼", "mode": "similar", "q": "SECC"},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        body = json.loads(got.content)
        assert body["count"] == 1
        assert [one["record_name"] for one in body["materials"]] == ["SECC_MDOI_1.0"]
        # 무슨 조건으로 거른 것인지 파일이 말한다 — 기본값(단위)은 안 적는다.
        assert body["filters"] == {"q": "SECC", "mode": "similar", "use": "범퍼"}


# --- 시험: 찾기 상자 --------------------------------------------------------------------


@pytest.mark.usefixtures("semantic_off")
class Test시험_찾기:
    def test_낱말로_나눠_찾고_시험_종류_이름도_본다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        run = _run(db, workspace, name="SECCX")

        both = _runs(client, admin_headers, q="SECCX 인장")
        assert [one["id"] for one in both["items"]] == [str(run.id)], (
            "재료 이름과 종류 이름을 함께 쳤는데 못 찾았다"
        )
        assert _runs(client, admin_headers, q="SECCX 동적")["total"] == 0

    def test_일치는_이름이나_파일명_전체(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        _run(db, workspace, name="SECCX", source_filename="ZWICK-9911.tra")

        assert _runs(client, admin_headers, q="zwick-9911.tra", mode="exact")["total"] == 1
        assert _runs(client, admin_headers, q="ZWICK-9911", mode="exact")["total"] == 0
        assert (
            _runs(client, admin_headers, q="SECCX_MD_01__TEN_01", mode="exact")["total"] == 1
        )

    def test_비슷은_오타를_찾고_이유를_붙인다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        _run(db, workspace, name="SECCX")

        assert _runs(client, admin_headers, q="SECCY_MD_01__TEN_01")["total"] == 0
        typo = _runs(client, admin_headers, q="SECCY_MD_01__TEN_01", mode="similar")
        assert typo["total"] == 1
        assert typo["items"][0]["matched"] == "similar"

        bad = client.get("/api/test-runs", params={"mode": "fuzzy"}, headers=admin_headers)
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-TESTS-0043"


# --- 시험: 조건 칸 ----------------------------------------------------------------------


class Test시험_조건_칸:
    def test_시험일_기간_끝날은_그날_끝까지(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        spring = _run(
            db, workspace, name="SPRING", tested_at=datetime(2026, 3, 10, 3, tzinfo=UTC)
        )
        summer = _run(
            db, workspace, name="SUMMER", tested_at=datetime(2026, 5, 20, 3, tzinfo=UTC)
        )
        _run(db, workspace, name="UNDATED")

        after = _runs(client, admin_headers, tested_from="2026-04-01")
        assert [one["id"] for one in after["items"]] == [str(summer.id)]
        until = _runs(client, admin_headers, tested_to="2026-03-10")
        assert [one["id"] for one in until["items"]] == [str(spring.id)]

    def test_장비로_거르고_거르기_목록에_선다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        zwick = _run(db, workspace, name="ZW", instrument="Zwick Z100")
        _run(db, workspace, name="BARE")

        got = _runs(client, admin_headers, instrument="Zwick Z100")
        assert [one["id"] for one in got["items"]] == [str(zwick.id)]
        assert _runs(client, admin_headers, instrument="__none__")["total"] == 1

        facets = client.get("/api/test-runs/facets", headers=admin_headers).json()
        rows = {one["key"]: one["count"] for one in facets["instruments"]}
        assert rows == {"Zwick Z100": 1, "__none__": 1}

    def test_조건_범위는_단위를_받아_표준_키로_묻는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        _run(db, workspace, name="ROOM", conditions={"temperature": 296.15})
        hot = _run(db, workspace, name="HOT", conditions={"temperature": 353.15})
        # **숫자가 아닌 조건 값이 있어도 터지지 않는다** — 캐스트가 먼저 돌면 500 이다.
        _run(db, workspace, name="WORDS", conditions={"temperature": "상온"})

        celsius = _runs(
            client,
            admin_headers,
            condition="temperature",
            condition_unit="°C",
            condition_min=70,
            condition_max=90,
        )
        assert [one["id"] for one in celsius["items"]] == [str(hot.id)]
        kelvin = _runs(
            client,
            admin_headers,
            condition="temperature",
            condition_unit="K",
            condition_min=350,
            condition_max=360,
        )
        assert [one["id"] for one in kelvin["items"]] == [str(hot.id)]

        def refused(**params: Any) -> str:
            got = client.get("/api/test-runs", params=params, headers=admin_headers)
            assert got.status_code == 422, got.text
            code: str = got.json()["error"]["code"]
            return code

        # 「80」 만으로는 °C 인지 K 인지 모른다.
        assert refused(condition="temperature", condition_min=70) == "MNX-TESTS-0044"
        # 온도를 길이로 물으면 환산은 무사히 끝나고 엉뚱한 범위가 걸린다.
        assert (
            refused(condition="temperature", condition_unit="mm", condition_min=70)
            == "MNX-CATALOG-0032"
        )
        assert (
            refused(condition="없는조건", condition_unit="K", condition_min=1)
            == "MNX-CATALOG-0051"
        )


# --- 뜻으로 (mock 배관) ------------------------------------------------------------------


@pytest.mark.usefixtures("semantic_ready")
class Test뜻으로_찾기:
    """`mock` 임베딩은 뜻이 없다 — **같은 글은 같은 벡터**라는 것만 믿는다. 그래서 색인한
    글을 그대로 물어 「뜻으로만 걸린 것이 목록에 서는가」 의 배관을 잰다."""

    def test_재료는_뜻으로_걸리고_시험은_그_재료로_걸린다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        made = _material(
            client, admin_headers, note="자동차 도어 안쪽 판에 쓰는 전기아연도금 강판"
        )
        _material(client, admin_headers, grade="AL5052", details=None)
        material = db.get(Material, made["id"])
        assert material is not None
        run = _run(db, workspace, name="MEANT", material=material)
        semantic.reindex(db)
        chunk = next(
            one
            for one in semantic.collect(db)
            if one.kind == "material" and one.entity_id == made["id"]
        )
        # 색인한 글 그대로 — 낱말(「—」·「·」)이 이름에 없어 글자로는 안 걸린다.
        said = f"{chunk.title}\n{chunk.body}"

        assert _materials(client, admin_headers, q=said)["total"] == 0
        meant = _materials(client, admin_headers, q=said, mode="similar")
        assert [(one["record_name"], one["matched"]) for one in meant["items"]] == [
            ("SECC_MDOI_1.0", "meaning")
        ]

        runs = _runs(client, admin_headers, q=said, mode="similar")
        assert [(one["id"], one["matched"]) for one in runs["items"]] == [
            (str(run.id), "meaning")
        ]

    def test_저장하면_그_재료만_곧바로_다시_색인한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**밤의 전체 색인까지 기다리지 않는다** — 오늘 넣은 재료가 내일에야 뜻으로 걸리면
        「방금 넣은 재료가 안 나온다」 로 보인다. 임베딩은 워커가 한다(요청 안에서 안 한다)."""
        # 메모가 짧으면 질의 글의 대부분이 이름이라 **글자로도(트라이그램) 걸린다** — 그러면
        # 뜻의 길을 못 잰다. 길게 둔다.
        made = _material(
            client,
            admin_headers,
            note="자동차 도어 안쪽 판에 쓰는 전기아연도금 강판, 프레스 성형용",
        )
        job = db.scalars(
            select(Job)
            .where(Job.kind == kinds.SEARCH_INDEX_MATERIALS)
            .order_by(Job.created_at.desc())
        ).first()
        assert job is not None, "등록했는데 색인 작업이 안 들어갔다"
        assert job.payload == {"material_ids": [made["id"]]}

        index_materials(db, job.payload)
        chunk = next(
            one
            for one in semantic.collect(db)
            if one.kind == "material" and one.entity_id == made["id"]
        )
        said = f"{chunk.title}\n{chunk.body}"
        found = _materials(client, admin_headers, q=said, mode="similar")
        assert [one["matched"] for one in found["items"]] == ["meaning"]

        # 고치면 **옛 뜻은 걷히고** 새 뜻으로 걸린다.
        patched = client.patch(
            f"/api/materials/{made['id']}",
            json={"note": "후드 바깥 판에 쓰는 합금화용융아연도금 강판, 외판 성형용"},
            headers=admin_headers,
        )
        assert patched.status_code == 200, patched.text
        again = db.scalars(
            select(Job)
            .where(Job.kind == kinds.SEARCH_INDEX_MATERIALS)
            .order_by(Job.created_at.desc())
        ).first()
        assert again is not None and again.id != job.id
        index_materials(db, again.payload)
        assert _materials(client, admin_headers, q=said, mode="similar")["total"] == 0
