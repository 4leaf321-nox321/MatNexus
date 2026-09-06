"""측정법 — **「그 물성은 무엇으로 재는가」** 의 이관과 읽기 전용 API.

카탈로그와 같은 규율을 문다: 무손실 · 멱등 · 모르면 멈춤 · API 는 읽기뿐.
여기만의 함정 둘도 문다 — ① 능력이 카탈로그 정의를 가리키므로 **카탈로그가
먼저** 들어가야 한다 ② sqlite 동적 타입이 `resolution` 을 float 로 돌려줘
String 컬럼과 매번 어긋났다(실측 30건 + 정수값 4건).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_catalog import make_snapshot  # 같은 폴더 — pytest·mypy 가 같은 이름으로 본다

from app.modules.catalog import importer as catalog_importer
from app.modules.metrology import importer
from app.modules.metrology.models import Instrument, InstrumentCapability
from app.shared.mt_import import ImportRefused


def add_metrology(snapshot: Path) -> Path:
    """카탈로그 스냅샷에 원본과 같은 스키마의 측정법 표 둘을 더한다."""
    con = sqlite3.connect(snapshot)
    con.executescript(
        """
        create table instrument (
            id integer primary key, vendor text, model text, category text,
            technique text, description text, doc_path text, source_id integer,
            notes text, created_at text, owned integer, owned_note text,
            owner_name text, owner_contact text, owned_checked_at text
        );
        create table instrument_capability (
            id integer primary key, instrument_id integer, property_key text,
            technique text, standard text, range_min real, range_max real,
            range_unit text, resolution float, accuracy text,
            temperature_min_k real, temperature_max_k real, specimen text,
            mapping_confidence text, source_detail text, notes text,
            created_at text
        );
        """
    )
    con.execute(
        "insert into instrument values (1, 'Instron', '5982', 'mechanical', "
        "'universal testing', null, '/catalogs/instron.pdf', 2, null, "
        "'2026-08-01 00:00:00', 1, '재료연 1층', '홍측정', null, '2026-08-20 00:00:00')"
    )
    con.execute(
        "insert into instrument values (2, 'Netzsch', 'DSC 214', 'thermal', "
        "'DSC', null, null, null, null, '2026-08-01 00:00:00', 0, null, null, "
        "null, null)"
    )
    con.execute(
        # resolution 0.01 — sqlite 가 float 로 돌려주는 실측 함정. 멱등 시험이 문다.
        "insert into instrument_capability values (1, 1, "
        "'mechanical.youngs_modulus', 'tensile', 'ISO 6892-1', 0.5, 100000.0, "
        "'N', 0.01, null, 233.15, 573.15, 'dogbone', 'high', 'p.12', null, "
        "'2026-08-02 00:00:00')"
    )
    con.execute(
        # resolution 1.0 — PG 가 varchar 로 '1' 로 적는 정수값 float 함정.
        "insert into instrument_capability values (2, 1, "
        "'mechanical.poisson_ratio', 'tensile+extensometer', null, null, null, "
        "null, 1.0, '0.5 %', null, null, null, 'medium', null, null, "
        "'2026-08-02 00:00:00')"
    )
    con.execute(
        # 기법 미정(None) 능력 — None 그룹으로 그대로 보여야 한다.
        "insert into instrument_capability values (3, 2, "
        "'thermal.glass_transition', null, 'ISO 11357', null, 873.15, 'K', "
        "null, null, 93.15, 873.15, null, 'high', null, null, "
        "'2026-08-02 00:00:00')"
    )
    con.commit()
    con.close()
    return snapshot


def run_both(db: Session, tmp_path: Path) -> Path:
    snapshot = add_metrology(make_snapshot(tmp_path))
    catalog_importer.run(db, snapshot)
    report = importer.run(db, snapshot)
    assert report.problems == []
    return snapshot


class Test무손실:
    def test_행수와_필드가_그대로_온다(self, db: Session, tmp_path: Path) -> None:
        run_both(db, tmp_path)
        instron = db.scalar(select(Instrument).where(Instrument.mt_id == 1))
        assert instron is not None and instron.vendor == "Instron"
        # 보유 여부 — 이 표에서 가장 중요한 한 칸.
        assert instron.owned is True and instron.owner_name == "홍측정"
        assert instron.source_id is not None  # 카탈로그 출처(mt 2)로 이어졌다
        dsc = db.scalar(select(Instrument).where(Instrument.mt_id == 2))
        assert dsc is not None and dsc.owned is False and dsc.source_id is None

        tensile = db.scalar(
            select(InstrumentCapability).where(InstrumentCapability.mt_id == 1)
        )
        assert tensile is not None
        assert tensile.property_key == "mechanical.youngs_modulus"
        assert tensile.standard == "ISO 6892-1"
        assert tensile.range_min == 0.5 and tensile.range_unit == "N"
        assert tensile.temperature_min_k == 233.15
        # sqlite 가 float 로 준 resolution 이 문자열로 고정된다.
        assert tensile.resolution == "0.01"
        integral = db.scalar(
            select(InstrumentCapability).where(InstrumentCapability.mt_id == 2)
        )
        assert integral is not None and integral.resolution == "1"

    def test_두_번_돌리면_전부_동일이다(self, db: Session, tmp_path: Path) -> None:
        snapshot = run_both(db, tmp_path)
        db.flush()
        again = importer.run(db, snapshot)
        assert again.problems == []
        for name, table in again.tables.items():
            assert table.added == 0 and table.updated == 0, (name, table)


class Test모르면_멈춘다:
    def test_카탈로그가_비어_있으면_거부한다(self, db: Session, tmp_path: Path) -> None:
        snapshot = add_metrology(make_snapshot(tmp_path))
        try:
            importer.run(db, snapshot)
        except ImportRefused as refused:
            assert "카탈로그" in str(refused)
        else:
            raise AssertionError("카탈로그 정의가 없는데 통과했다")

    def test_모르는_컬럼이_있으면_거부한다(self, db: Session, tmp_path: Path) -> None:
        snapshot = add_metrology(make_snapshot(tmp_path))
        catalog_importer.run(db, snapshot)
        con = sqlite3.connect(snapshot)
        con.execute("alter table instrument add column new_field text")
        con.commit()
        con.close()
        try:
            importer.run(db, snapshot)
        except ImportRefused as refused:
            assert "new_field" in str(refused)
        else:
            raise AssertionError("모르는 컬럼인데 통과했다")

    def test_모르는_물성_키면_거부한다(self, db: Session, tmp_path: Path) -> None:
        snapshot = add_metrology(make_snapshot(tmp_path))
        catalog_importer.run(db, snapshot)
        con = sqlite3.connect(snapshot)
        con.execute(
            "update instrument_capability set property_key = 'no.such_key' where id = 3"
        )
        con.commit()
        con.close()
        try:
            importer.run(db, snapshot)
        except ImportRefused as refused:
            assert "no.such_key" in str(refused)
        else:
            raise AssertionError("정의에 없는 물성 키인데 통과했다")


class Test읽기_API:
    def test_요약이_장비와_보유를_가른다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        run_both(db, tmp_path)
        db.commit()
        body = client.get("/api/metrology/summary", headers=admin_headers).json()
        assert body["instruments"] == 2
        assert body["instruments_owned"] == 1  # 카탈로그 수 ≠ 보유 수
        assert body["capabilities"] == 3
        assert body["properties_covered"] == 3
        assert body["properties_total"] == 4
        assert body["categories"] == {"mechanical": 1, "thermal": 1}

    def test_커버리지가_빈_칸을_숨기지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        run_both(db, tmp_path)
        db.commit()
        body = client.get("/api/metrology/coverage", headers=admin_headers).json()
        covered = {row["property_key"]: row for row in body["covered"]}
        assert set(covered) == {
            "mechanical.youngs_modulus",
            "mechanical.poisson_ratio",
            "thermal.glass_transition",
        }
        young = covered["mechanical.youngs_modulus"]
        assert young["instrument_count"] == 1
        assert young["owned_instrument_count"] == 1
        assert young["value_count"] == 2  # 카탈로그에 실린 값 수
        tg = covered["thermal.glass_transition"]
        assert tg["owned_instrument_count"] == 0  # 카탈로그엔 있지만 우리는 못 잰다
        # 능력이 하나도 없는 밀도는 gaps 로 그대로 보인다.
        assert [row["property_key"] for row in body["gaps"]] == ["physical.density"]

    def test_물성_하나의_측정_지도(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        run_both(db, tmp_path)
        db.commit()
        body = client.get(
            "/api/metrology/by-property/mechanical.youngs_modulus",
            headers=admin_headers,
        ).json()
        assert body["name"] == "탄성계수" and body["si_unit"] == "Pa"
        assert [group["technique"] for group in body["techniques"]] == ["tensile"]
        capability = body["techniques"][0]["capabilities"][0]
        assert capability["instrument"]["vendor"] == "Instron"
        assert capability["instrument"]["owned"] is True
        assert capability["standard"] == "ISO 6892-1"
        assert capability["mapping_confidence"] == "high"

        # 기법 미정(None) 능력도 그룹으로 그대로 온다.
        tg = client.get(
            "/api/metrology/by-property/thermal.glass_transition",
            headers=admin_headers,
        ).json()
        assert [group["technique"] for group in tg["techniques"]] == [None]

        missing = client.get("/api/metrology/by-property/no.such_key", headers=admin_headers)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "MNX-METROLOGY-0001"
