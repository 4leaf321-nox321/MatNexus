"""[계획] 데이터 체계 개선 — 2026-09-05 점검에서 고친 것들이 무는가.

1  처리 결과가 있는 시험의 영구 삭제       FK 위반 500 이었다 → 결과와 곁 폴더까지 지운다
2  처리·마스터커브 파일                    세지도 지우지도 않았다 → 오펀·만료로 잡힌다
3  부서 합치기의 이름 충돌                  UPDATE 가 500 이었다 → 미리 세고 422 로 말한다
5·6 선언 물성 열쇠                          셋만 알고 라벨로 이었다 → 기준정보 항목 전부, 키로
7  grade 오타                              아무도 못 잡았다 → 비슷한 이름을 보여 준다
8  안내서                                  지우면 못 돌아왔다 → 휴지통 종류가 됐다
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.processing.models import ProcessingResult
from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.shared import curvedata, filestore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TRA = FIXTURES / "Example.tra"
STEPS = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}}
]


def _material(client: TestClient, headers: dict[str, str], **extra: Any) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"PLAN-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            **extra,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    created: dict[str, Any] = made.json()
    return created


def _processed_run(client: TestClient, db: Session, headers: dict[str, str]) -> str:
    """처리 결과를 하나 저장한 시험. 그 파일이 `processing/{run}` 에 선다."""
    ensure_builtin_test_types(db)
    db.commit()
    material = _material(client, headers)
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens", json={"orientation": "MD"}, headers=headers
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    test_services.parse_run(db, uuid.UUID(run_id))
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": STEPS},
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    assert filestore.resolve(f"processing/{run_id}").is_dir()
    return run_id


class Test1_처리_결과가_있는_시험의_영구_삭제:
    def test_결과와_곁_폴더까지_지운다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        run_id = _processed_run(client, db, admin_headers)
        gone = client.delete(f"/api/test-runs/{run_id}", headers=admin_headers)
        assert gone.status_code in (200, 204), gone.text

        purged = client.delete(
            f"/api/trash/test_run/{run_id}?confirm=true", headers=admin_headers
        )
        assert purged.status_code == 200, purged.text
        db.expire_all()
        assert not db.scalars(
            select(ProcessingResult).where(ProcessingResult.test_run_id == uuid.UUID(run_id))
        ).all()
        assert not filestore.resolve(f"processing/{run_id}").exists()

    def test_여럿을_함께_골라도_전부_지워진다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """한 트랜잭션이라 하나가 FK 로 터지면 함께 고른 것까지 안 지워졌다."""
        run_id = _processed_run(client, db, admin_headers)
        client.delete(f"/api/test-runs/{run_id}", headers=admin_headers)
        purged = client.post(
            "/api/trash/purge",
            json={"items": [{"kind": "test_run", "id": run_id}], "confirm": True},
            headers=admin_headers,
        )
        assert purged.status_code == 200, purged.text
        assert purged.json()["purged"] == 1


class Test2_곁_폴더_파일:
    def test_행_없는_처리_폴더는_오펀이다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        run_id = _processed_run(client, db, admin_headers)
        path = f"processing/{run_id}"
        report = test_services.storage_report(db)
        assert path not in {item["path"] for item in report["orphans"]}
        assert report["processing_bytes"] > 0

        # 행을 직접 지워 오펀을 만든다 — 트랜잭션이 파일시스템까지 덮지 못하는 상황.
        from app.modules.tests.models import Curve, TestRun, TestSummary

        run = db.get(TestRun, uuid.UUID(run_id))
        assert run is not None
        for model in (ProcessingResult, Curve, TestSummary):
            for row in db.scalars(select(model).where(model.test_run_id == run.id)):
                db.delete(row)
        # 시험-요약 사이에 ORM 관계가 없어 순서를 모른다 — 자식을 먼저 밀어낸다.
        db.flush()
        db.delete(run)
        db.commit()

        assert path in {item["path"] for item in test_services.storage_report(db)["orphans"]}
        removed = test_services.cleanup_storage(db, dry_run=False)
        assert path in removed["removed"]
        assert not filestore.resolve(path).exists()

    def test_보존기간이_지난_시험의_처리_파일도_치운다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        run_id = _processed_run(client, db, admin_headers)
        client.delete(f"/api/test-runs/{run_id}", headers=admin_headers)
        db.expire_all()
        path = f"processing/{run_id}"
        expired = test_services.storage_report(db, retention_days=0)
        assert path in {item["path"] for item in expired["expired"]}
        result = test_services.cleanup_storage(db, dry_run=False, retention_days=0)
        assert path in result["removed"]
        # 파일이 없어진 처리 결과 행은 뜻이 없다 — 시험 행만 남는다.
        assert not db.scalars(
            select(ProcessingResult).where(ProcessingResult.test_run_id == uuid.UUID(run_id))
        ).all()


class Test3_부서_합치기_이름_충돌:
    def _two(self, client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
        a, b = f"a-{uuid.uuid4().hex[:5]}", f"b-{uuid.uuid4().hex[:5]}"
        for slug in (a, b):
            made = client.post(
                "/api/workspaces", json={"slug": slug, "name": slug}, headers=headers
            )
            assert made.status_code == 201, made.text
        return a, b

    def test_같은_이름이_양쪽에_있으면_미리_말하고_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        a, b = self._two(client, admin_headers)
        for slug in (a, b):
            _material(client, admin_headers, grade="DUP", workspace_slug=slug)

        seen = client.get(
            f"/api/workspaces/{a}/merge-conflicts?target_slug={b}", headers=admin_headers
        )
        assert seen.status_code == 200, seen.text
        assert seen.json() == [{"label": "재료", "names": ["DUP_-_1.0"]}]

        merged = client.post(
            f"/api/workspaces/{a}/merge", json={"target_slug": b}, headers=admin_headers
        )
        assert merged.status_code == 422, merged.text
        assert merged.json()["error"]["code"] == "MNX-WORKSPACES-0023"
        assert "DUP_-_1.0" in merged.json()["error"]["message"]

    def test_지운_것은_안_센다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """부분 유니크 인덱스 밖이라 UPDATE 도 안 터진다 — 세면 없는 충돌로 막는다."""
        a, b = self._two(client, admin_headers)
        mine = _material(client, admin_headers, grade="DUP", workspace_slug=a)
        _material(client, admin_headers, grade="DUP", workspace_slug=b)
        gone = client.post(
            "/api/materials/delete", json={"material_ids": [mine["id"]]}, headers=admin_headers
        )
        assert gone.status_code == 200, gone.text
        seen = client.get(
            f"/api/workspaces/{a}/merge-conflicts?target_slug={b}", headers=admin_headers
        )
        assert seen.json() == []
        merged = client.post(
            f"/api/workspaces/{a}/merge", json={"target_slug": b}, headers=admin_headers
        )
        assert merged.status_code == 200, merged.text


class Test5_6_선언_물성_열쇠:
    @pytest.fixture(autouse=True)
    def _items(self, db: Session) -> None:
        # `db` 픽스처는 축만 심는다 — 물성 항목은 따로.
        ensure_builtin_property_items(db)
        db.commit()

    def test_기준정보의_항목이_전부_파이프라인_키를_갖는다(self, db: Session) -> None:
        keys = curvedata.declared_keys(db)
        assert keys["탄성계수"].key == "youngs_modulus"
        assert keys["선팽창계수(CTE)"].key == "thermal_expansion"
        assert keys["선팽창계수(CTE)"].si_unit == "1/K"
        assert keys["비열"].key == "specific_heat"

    def test_잰_값이_있는_항목은_그_키로_잇는다(self, db: Session) -> None:
        """라벨 문자열이 아니라 항목의 `measured_key` 가 열쇠다."""
        from app.modules.vocabulary.models import Vocabulary, VocabularyTerm

        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        terms = list(
            db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_id == axis.id))
        )
        term = next((one for one in terms if one.value.strip() == "탄성계수"), None)
        assert term is not None, [one.value for one in terms]
        term.attributes = {**term.attributes, "measured_key": "youngs_modulus"}
        db.commit()
        keys = curvedata.declared_keys(db)
        assert keys["탄성계수"].measured_key == "youngs_modulus"

    def test_적어_둔_열물성이_파이프라인에_들어간다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """전에는 셋 밖의 항목이 **오류 없이 조용히 무시**됐다."""
        run_id = _processed_run(client, db, admin_headers)
        from app.modules.tests.models import TestRun

        run = db.get(TestRun, uuid.UUID(run_id))
        assert run is not None
        material_id = client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()[
            "material_id"
        ]
        changed = client.patch(
            f"/api/materials/{material_id}",
            json={
                "declared_properties": [
                    {
                        "item": "선팽창계수(CTE)",
                        "points": [{"value": 1.2e-5}],
                        "source": "literature",
                        "reference": "예시",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        db.expire_all()
        given = {one.key: one for one in curvedata.declared_scalars(db, run)}
        assert given["declared_thermal_expansion"].value == pytest.approx(1.2e-5)
        assert given["declared_thermal_expansion"].si_unit == "1/K"


class Test7_비슷한_이름:
    def test_grade_오타를_등록_전에_보여_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        tag = uuid.uuid4().hex[:4].upper()
        made = _material(client, admin_headers, grade=f"SGARC440{tag}", details="MDOI")
        seen = client.post(
            "/api/materials/preview-name",
            json={"grade": f"SGARC 440{tag}", "details": "MDOI", "spec_thickness": 1.0},
            headers=admin_headers,
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["taken"] is False
        assert made["record_name"] in [row["record_name"] for row in seen.json()["similar"]]

    def test_같은_이름은_taken_이지_similar_가_아니다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = _material(client, admin_headers, details="MDOI")
        seen = client.post(
            "/api/materials/preview-name",
            json={"grade": made["grade"], "details": "MDOI", "spec_thickness": 1.0},
            headers=admin_headers,
        ).json()
        assert seen["taken"] is True
        assert made["record_name"] not in [row["record_name"] for row in seen["similar"]]


class Test8_안내서_휴지통:
    def test_지운_안내서를_되살리고_영영_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        key = f"doc-{uuid.uuid4().hex[:6]}"
        made = client.post(
            "/api/guide/documents",
            json={"key": key, "title": "예시 안내서", "kind": "calculation", "topic": "dma"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        doc_id = made.json()["id"]
        section = client.post(
            f"/api/guide/documents/{key}/sections",
            json={"key": "s1", "title": "절"},
            headers=admin_headers,
        )
        assert section.status_code == 201, section.text

        gone = client.delete(f"/api/guide/documents/{key}", headers=admin_headers)
        assert gone.status_code == 204, gone.text
        rows = client.get("/api/trash?kind=guide_document", headers=admin_headers).json()
        mine = [row for row in rows if row["id"] == doc_id]
        assert mine and mine[0]["kind_label"] == "안내서" and mine[0]["name"] == "예시 안내서"

        back = client.post(
            f"/api/trash/guide_document/{doc_id}/restore", headers=admin_headers
        )
        assert back.status_code == 200, back.text
        assert (
            client.get(f"/api/guide/documents/{key}", headers=admin_headers).status_code == 200
        )

        client.delete(f"/api/guide/documents/{key}", headers=admin_headers)
        purged = client.delete(
            f"/api/trash/guide_document/{doc_id}?confirm=true", headers=admin_headers
        )
        assert purged.status_code == 200, purged.text
        assert (
            client.get(f"/api/guide/documents/{key}", headers=admin_headers).status_code == 404
        )
        assert not [
            row
            for row in client.get(
                "/api/trash?kind=guide_document", headers=admin_headers
            ).json()
            if row["id"] == doc_id
        ]
