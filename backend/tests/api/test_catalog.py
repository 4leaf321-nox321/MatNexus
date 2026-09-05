"""물성 카탈로그 — **무손실·멱등 이관과 읽기 전용 API** (ADR 0027).

무는 것이 넷이다.

    무손실이다        원본 컬럼·JSON(정정 이력 포함)이 그대로 돌아온다
    멱등이다          두 번 돌리면 전부 「동일」— 중복이 생기지 않는다
    모르면 멈춘다      원본에 모르는 컬럼이 있으면 거부한다 (조용히 버리는 것 금지)
    API 는 읽기뿐     값을 만들고 고치는 길은 이관 스크립트 하나다
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog import importer
from app.modules.catalog.models import CatalogMaterial, CatalogValue


def make_snapshot(path: Path) -> Path:
    """원본(materialtwin.db)과 같은 스키마의 작은 SQLite 를 만든다."""
    db = path / "mt.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        create table material (
            id integer primary key, name text, material_code text, category text,
            description text, attributes text, owner_id integer,
            created_at text, updated_at text
        );
        create table source (
            id integer primary key, kind text, doi text, isbn text, url text,
            title text, authors text, year integer, publisher text, license text,
            local_path text, content_hash text, retrieved_at text, created_at text
        );
        create table property_definition (
            id integer primary key, key text, domain text, name text, symbol text,
            si_unit text, value_type text, description text, test_standard text,
            condition_axes text, created_at text
        );
        create table property_value (
            id integer primary key, material_id integer, property_key text,
            value_num real, value_text text, unit text, uncertainty real,
            conditions text, method text, quality_tier integer, source_id integer,
            source_detail text, notes text, created_at text
        );
        """
    )
    con.execute(
        "insert into material values (1, 'SUS304', null, 'metal', null, "
        '\'{"subsystem": "housing", "role": "product", "manufacturer": "POSCO", '
        '"core_absent_from_vendor_sheet": {"optical.emissivity_total": "전수 0건"}}\', '
        "null, '2026-07-16 12:54:53', '2026-08-19 20:09:53')"
    )
    con.execute(
        "insert into material values (2, 'FR-4 generic', null, 'composite', '적층판', "
        "null, null, '2026-07-16 12:54:53', '2026-07-16 12:54:53')"
    )
    con.execute(
        "insert into source values (1, 'journal', '10.1000/x', null, null, "
        "'어느 논문', 'Kim', 2020, null, null, '/corpus/kim2020.md', null, "
        "'2026-07-31 23:06:37.376063', '2026-07-31 23:06:37')"
    )
    con.execute(
        "insert into source values (2, 'datasheet', null, null, 'https://v.example', "
        "'벤더 시트', null, null, 'Vendor', null, null, null, null, '2026-07-31 23:07:03')"
    )
    con.execute(
        "insert into property_definition values (1, 'mechanical.youngs_modulus', "
        "'mechanical', '탄성계수', 'E', 'Pa', 'numeric', null, 'ISO 6892', "
        "'[\"temperature_k\"]', '2026-07-01 00:00:00')"
    )
    con.execute(
        "insert into property_definition values (2, 'thermal.glass_transition', "
        "'thermal', '유리전이온도', 'Tg', 'K', 'numeric', null, null, null, "
        "'2026-07-01 00:00:00')"
    )
    con.execute(
        "insert into property_definition values (3, 'mechanical.poisson_ratio', "
        "'mechanical', '포아송비', 'nu', '1', 'numeric', null, null, null, "
        "'2026-07-01 00:00:00')"
    )
    con.execute(
        "insert into property_definition values (4, 'physical.density', "
        "'physical', '밀도', 'rho', 'kg/m^3', 'numeric', null, null, null, "
        "'2026-07-01 00:00:00')"
    )
    con.execute(
        "insert into property_value values (1, 1, 'mechanical.youngs_modulus', "
        "193e9, null, 'Pa', null, "
        '\'{"temperature_k": 296.15, "value_before_correction": 190e9, '
        '"correction_reason": "표 오독 정정"}\', '
        "'measured', 1, 1, 'Table 2', null, '2026-08-01 00:00:00')"
    )
    con.execute(
        "insert into property_value values (2, 1, 'mechanical.youngs_modulus', "
        "200e9, null, 'Pa', null, '{\"assumption\": true}', 'estimated', 4, 2, "
        "null, '클래스 대표에서 가정', '2026-08-01 00:00:00')"
    )
    con.execute(
        # tau_s=1e23 — PG JSONB 가 정확한 정수로 정규화해 파이썬 float 와
        # `==` 가 어긋나는 실측 함정. 멱등 시험이 이 행으로 문다.
        "insert into property_value values (3, 2, 'thermal.glass_transition', "
        "408.15, null, 'K', null, '{\"tau_s\": 1e+23}', 'handbook', 2, 2, null, null, "
        "'2026-08-01 00:00:00')"
    )
    con.execute(
        "insert into property_value values (4, 1, 'mechanical.poisson_ratio', "
        "0.29, null, '1', null, null, 'handbook', 2, 2, null, null, "
        "'2026-08-01 00:00:00')"
    )
    con.execute(
        "insert into property_value values (5, 1, 'physical.density', "
        "7930, null, 'kg/m^3', null, null, 'measured', 1, 1, null, null, "
        "'2026-08-01 00:00:00')"
    )
    con.commit()
    con.close()
    return db


class Test무손실:
    def test_컬럼과_JSON_이_그대로_돌아온다(self, db: Session, tmp_path: Path) -> None:
        report = importer.run(db, make_snapshot(tmp_path))
        assert report.problems == []
        assert {name: t.added for name, t in report.tables.items()} == {
            "정의": 4,
            "출처": 2,
            "재료": 2,
            "값": 5,
        }
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        assert sus is not None and sus.name == "SUS304"
        # 발췌 컬럼과 정본(attributes)이 같이 온다 — 부재 판정(core_*)까지.
        assert sus.subsystem == "housing" and sus.manufacturer == "POSCO"
        assert sus.attributes is not None
        assert "core_absent_from_vendor_sheet" in sus.attributes

        first = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == 1))
        assert first is not None and first.value_num == 193e9
        # 정정 이력이 conditions 안에 그대로 산다 — 원본은 값을 지우지 않고 표시했다.
        assert first.conditions is not None
        assert first.conditions["correction_reason"] == "표 오독 정정"
        assert first.quality_tier == 1 and first.source_id is not None

        assumed = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == 2))
        assert assumed is not None and assumed.quality_tier == 4
        assert assumed.conditions == {"assumption": True}

    def test_두_번_돌리면_전부_동일이다(self, db: Session, tmp_path: Path) -> None:
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        again = importer.run(db, snapshot)
        assert again.problems == []
        for name, table in again.tables.items():
            assert table.added == 0 and table.updated == 0, (name, table)

    def test_원본이_바뀌면_갱신으로_따라간다(self, db: Session, tmp_path: Path) -> None:
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        con = sqlite3.connect(snapshot)
        con.execute("update property_value set value_num = 195e9 where id = 1")
        con.commit()
        con.close()
        again = importer.run(db, snapshot)
        assert again.tables["값"].updated == 1 and again.tables["값"].added == 0
        row = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == 1))
        assert row is not None and row.value_num == 195e9


class Test모르면_멈춘다:
    def test_모르는_컬럼이_있으면_거부한다(self, db: Session, tmp_path: Path) -> None:
        """미래 스냅샷에 새 컬럼이 생겼을 때 조용히 버리는 것이 최악이다."""
        snapshot = make_snapshot(tmp_path)
        con = sqlite3.connect(snapshot)
        con.execute("alter table property_value add column new_field text")
        con.commit()
        con.close()
        try:
            importer.run(db, snapshot)
        except importer.ImportRefused as refused:
            assert "new_field" in str(refused)
        else:
            raise AssertionError("모르는 컬럼인데 통과했다")

    def test_안_쓰던_자리에_값이_생기면_거부한다(self, db: Session, tmp_path: Path) -> None:
        snapshot = make_snapshot(tmp_path)
        con = sqlite3.connect(snapshot)
        con.execute("update material set owner_id = 7 where id = 1")
        con.commit()
        con.close()
        try:
            importer.run(db, snapshot)
        except importer.ImportRefused:
            pass
        else:
            raise AssertionError("owner_id 가 채워졌는데 통과했다")


class Test읽기_API:
    def test_목록과_상세가_값·등급·출처를_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()

        listed = client.get("/api/catalog/materials?q=SUS", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        page = listed.json()
        assert page["total"] == 1 and page["items"][0]["value_count"] == 4

        detail = client.get(
            f"/api/catalog/materials/{page['items'][0]['id']}", headers=admin_headers
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        # 후보를 숨기지 않는다 — 같은 물성의 값 둘이 다 온다.
        keys = [one["property_key"] for one in body["values"]]
        assert keys.count("mechanical.youngs_modulus") == 2
        tiers = {one["quality_tier"] for one in body["values"]}
        assert tiers == {1, 2, 4}
        # 대표는 실측(tier1)이고 먼저 선다. 진 후보는 밀린 자리를 들고 온다.
        youngs = [
            one for one in body["values"] if one["property_key"] == "mechanical.youngs_modulus"
        ]
        assert youngs[0]["representative"] and youngs[0]["quality_tier"] == 1
        assert not youngs[1]["representative"]
        assert youngs[1]["separated_by"] == "등급"
        assert {one["n_candidates"] for one in youngs} == {2}
        sourced = [one for one in body["values"] if one["source"]]
        assert sourced and sourced[0]["source"]["kind"] in ("journal", "datasheet")

        summary = client.get("/api/catalog/summary", headers=admin_headers)
        assert summary.status_code == 200
        assert summary.json()["values"] == 5

    def test_없는_재료는_404_다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        gone = client.get(
            "/api/catalog/materials/00000000-0000-0000-0000-000000000000",
            headers=admin_headers,
        )
        assert gone.status_code == 404
        assert gone.json()["error"]["code"] == "MNX-CATALOG-0001"


class Test덱_만들기:
    """BOM 붙여넣기 → 매칭 → 덱. **쓰인 값마다 출처 각주가 덱에 적힌다.**"""

    def test_매칭이_줄과_MID_를_읽고_후보를_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        matched = client.post(
            "/api/catalog/deck/match",
            json={"text": "101, SUS\n\nFR-4"},
            headers=admin_headers,
        )
        assert matched.status_code == 200, matched.text
        rows = matched.json()
        assert len(rows) == 2
        assert rows[0]["mid"] == 101 and rows[0]["candidates"][0]["name"] == "SUS304"
        assert rows[1]["mid"] is None
        assert rows[1]["candidates"][0]["name"] == "FR-4 generic"

    def test_덱에_값과_출처_각주가_실린다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        fr4 = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 2))
        assert sus is not None and fr4 is not None

        built = client.post(
            "/api/catalog/deck/build",
            json={
                "items": [
                    {"mid": 101, "catalog_material_id": str(sus.id)},
                    {"mid": 102, "catalog_material_id": str(fr4.id)},
                ],
                "format": "dyna_elastic",
            },
            headers=admin_headers,
        )
        assert built.status_code == 200, built.text
        body = built.json()
        assert "*MAT_ELASTIC" in body["text"]
        # 대표값(tier1, 193e9)이 실리고 — tier4 가정값이 아니다.
        assert "1.930E+11" in body["text"]
        # 값마다 출처 각주: 논문 제목·doi·등급까지 덱 주석으로.
        assert "어느 논문" in body["text"]
        assert "doi:10.1000/x" in body["text"]
        assert "tier 1" in body["text"]
        # FR-4 는 탄성 셋이 없어 덱에 못 실리고 — 조용히 빠지지 않는다.
        assert body["material_count"] == 1
        assert body["skipped"][0]["name"] == "FR-4 generic"
        assert body["skipped"][0]["missing"]

    def test_단위계를_고르면_MPa_로_적힌다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        assert sus is not None
        built = client.post(
            "/api/catalog/deck/build",
            json={
                "items": [{"mid": 1, "catalog_material_id": str(sus.id)}],
                "format": "dyna_elastic",
                "units": "mm_n_tonne",
            },
            headers=admin_headers,
        )
        assert built.status_code == 200, built.text
        text = built.json()["text"]
        assert "Consistent units: tonne, mm, s, MPa" in text
        assert "1.930E+05" in text  # 193 GPa → MPa
        assert "7.930E-09" in text  # 7930 kg/m3 → tonne/mm3

    def test_MID_중복과_모르는_형식은_거절한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        assert sus is not None
        item = {"mid": 7, "catalog_material_id": str(sus.id)}
        doubled = client.post(
            "/api/catalog/deck/build",
            json={"items": [item, item], "format": "dyna_elastic"},
            headers=admin_headers,
        )
        assert doubled.status_code == 422
        assert "두 번" in doubled.json()["error"]["message"]
        odd = client.post(
            "/api/catalog/deck/build",
            json={"items": [item], "format": "abaqus"},
            headers=admin_headers,
        )
        assert odd.status_code == 422
        assert "시험" in odd.json()["error"]["message"]


class Test문헌_연결:
    """사내 재료 ↔ 문헌 재료 — 재료당 하나, 다시 걸면 교체, 비어도 200."""

    def _material(self, client: TestClient, headers: dict[str, str]) -> str:
        made = client.post(
            "/api/workspaces", json={"slug": "link-team", "name": "링크팀"}, headers=headers
        )
        assert made.status_code == 201, made.text
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "LK01",
                "spec_thickness": 1.0,
                "workspace_slug": "link-team",
            },
            headers=headers,
        )
        assert material.status_code == 201, material.text
        return str(material.json()["id"])

    def test_걸고_바꾸고_푼다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        material_id = self._material(client, admin_headers)
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        fr4 = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 2))
        assert sus is not None and fr4 is not None

        # 비어 있어도 200 — 「아직 없음」 은 오류가 아니다.
        empty = client.get(f"/api/catalog/links/{material_id}", headers=admin_headers)
        assert empty.status_code == 200 and empty.json()["catalog_material_id"] is None

        linked = client.put(
            f"/api/catalog/links/{material_id}",
            json={"catalog_material_id": str(sus.id)},
            headers=admin_headers,
        )
        assert linked.status_code == 200, linked.text
        assert linked.json()["name"] == "SUS304" and linked.json()["value_count"] == 4

        # 다시 걸면 교체 — 두 줄이 되지 않는다.
        swapped = client.put(
            f"/api/catalog/links/{material_id}",
            json={"catalog_material_id": str(fr4.id)},
            headers=admin_headers,
        )
        assert swapped.status_code == 200 and swapped.json()["name"] == "FR-4 generic"

        gone = client.delete(f"/api/catalog/links/{material_id}", headers=admin_headers)
        assert gone.status_code == 204
        after = client.get(f"/api/catalog/links/{material_id}", headers=admin_headers)
        assert after.json()["catalog_material_id"] is None

    def test_없는_대상은_404_다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        material_id = self._material(client, admin_headers)
        bogus = client.put(
            f"/api/catalog/links/{material_id}",
            json={"catalog_material_id": "00000000-0000-0000-0000-000000000000"},
            headers=admin_headers,
        )
        assert bogus.status_code == 404
        missing = client.get(
            "/api/catalog/links/00000000-0000-0000-0000-000000000000",
            headers=admin_headers,
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "MNX-CATALOG-0002"
