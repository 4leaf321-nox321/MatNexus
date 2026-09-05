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
    con.commit()
    con.close()
    return db


class Test무손실:
    def test_컬럼과_JSON_이_그대로_돌아온다(self, db: Session, tmp_path: Path) -> None:
        report = importer.run(db, make_snapshot(tmp_path))
        assert report.problems == []
        assert {name: t.added for name, t in report.tables.items()} == {
            "정의": 2,
            "출처": 2,
            "재료": 2,
            "값": 3,
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
        assert page["total"] == 1 and page["items"][0]["value_count"] == 2

        detail = client.get(
            f"/api/catalog/materials/{page['items'][0]['id']}", headers=admin_headers
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        # 후보를 숨기지 않는다 — 같은 물성의 값 둘이 다 온다.
        keys = [one["property_key"] for one in body["values"]]
        assert keys.count("mechanical.youngs_modulus") == 2
        tiers = {one["quality_tier"] for one in body["values"]}
        assert tiers == {1, 4}
        sourced = [one for one in body["values"] if one["source"]]
        assert sourced and sourced[0]["source"]["kind"] in ("journal", "datasheet")

        summary = client.get("/api/catalog/summary", headers=admin_headers)
        assert summary.status_code == 200
        assert summary.json()["values"] == 3

    def test_없는_재료는_404_다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        gone = client.get(
            "/api/catalog/materials/00000000-0000-0000-0000-000000000000",
            headers=admin_headers,
        )
        assert gone.status_code == 404
        assert gone.json()["error"]["code"] == "MNX-CATALOG-0001"
