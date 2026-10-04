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

from app.modules.catalog import importer, parameters
from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogMaterial, CatalogValue
from app.modules.vocabulary.definitions import ensure_builtin_property_items


def link_builtin(db: Session) -> None:
    """기본 물성 항목과 문헌 키의 연결 — 배포가 까는 것(`scripts/refresh_builtins.py`).

    문헌 덱은 **사내 물성 매핑을 거쳐** 값을 싣는다(2026-09-28). 연결이 없으면 문헌 값이
    덱에 안 실리는 것이 맞는 결과라, 덱 시험은 운영과 같은 연결을 먼저 깐다.
    """
    ensure_builtin_property_items(db)
    ensure_builtin_property_links(db)
    db.flush()


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


def _drop(snapshot: Path, *statements: str) -> None:
    """원본이 줄을 지운 다음 스냅샷을 흉내 낸다."""
    con = sqlite3.connect(snapshot)
    for statement in statements:
        con.execute(statement)
    con.commit()
    con.close()


class Test원본에서_빠진_줄:
    """**원본이 줄을 지워도 MatNexus 는 지우지 않고 표시한다**(2026-10-04).

    이관은 배포마다 돌고 지우지 않는다 — 선언 물성 · 카드 · 덱 근거가 그 줄을 쥐고 있을 수
    있어서다. 전에는 빠진 줄이 조용히 남았고, 더 나쁘게는 검산이 행 수를 견줘 **적재가 통째로
    거부**되었다(배포는 계속되므로 그 뒤로 문헌 데이터가 영영 안 바뀐다).
    """

    def test_빠진_줄은_지우지_않고_표시하고_검산은_통과한다(
        self, db: Session, tmp_path: Path
    ) -> None:
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        # 원본이 재료 2(FR-4)와 그 값, SUS304 의 가정값 하나를 지웠다.
        _drop(
            snapshot,
            "delete from property_value where id in (2, 3)",
            "delete from material where id = 2",
        )
        again = importer.run(db, snapshot)
        db.flush()

        assert again.problems == [], again.problems
        assert (again.tables["값"].missing, again.tables["값"].newly_missing) == (2, 2)
        assert again.tables["재료"].missing == 1
        assert "원본에서 빠짐 2(이번에 새로 2)" in again.line()
        for mt_id in (2, 3):
            row = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == mt_id))
            assert row is not None, "원본에서 빠진 줄을 지웠다"
            assert row.source_missing_at is not None
        kept = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == 1))
        assert kept is not None and kept.source_missing_at is None
        gone = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 2))
        assert gone is not None and gone.source_missing_at is not None

        # 한 번 더 돌려도 새로 빠진 것은 없다 — 처음 본 때를 지킨다.
        stamp = gone.source_missing_at
        third = importer.run(db, snapshot)
        assert third.tables["값"].newly_missing == 0 and third.tables["값"].missing == 2
        assert gone.source_missing_at == stamp

    def test_원본에_다시_나타나면_표시를_거둔다(self, db: Session, tmp_path: Path) -> None:
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        _drop(snapshot, "delete from property_value where id = 2")
        importer.run(db, snapshot)
        db.flush()

        fresh = tmp_path / "again"
        fresh.mkdir()
        back = importer.run(db, make_snapshot(fresh))
        assert back.tables["값"].revived == 1
        row = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == 2))
        assert row is not None and row.source_missing_at is None

    def test_직접_넣은_줄은_건드리지_않는다(self, db: Session, tmp_path: Path) -> None:
        """MatNexus 에서 넣은 줄(`mt_id` 없음)은 원본에 원래 없다 — 「빠짐」 이 아니다."""
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        assert sus is not None
        local = CatalogValue(
            material_id=sus.id,
            property_key="physical.density",
            value_num=7900,
            unit="kg/m^3",
            quality_tier=3,
        )
        db.add(local)
        db.flush()
        _drop(snapshot, "delete from property_value where id = 5")
        report = importer.run(db, snapshot)
        assert report.tables["값"].missing == 1
        assert local.source_missing_at is None

    def test_한꺼번에_많이_빠지면_원본이_다른_파일로_보고_거부한다(
        self, db: Session, tmp_path: Path, monkeypatch: object
    ) -> None:
        """잘못 고른 스냅샷 · id 를 새로 매긴 원본을 받으면 수만 줄이 「빠짐」 으로 바뀐다."""
        from app.shared import mt_import

        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        # 시험 표는 작아서 바닥(50)을 낮춘다 — 값 다섯 중 셋이 빠지면 한도(10%)를 넘는다.
        monkeypatch.setattr(mt_import, "MASS_MISSING_FLOOR", 1)  # type: ignore[attr-defined]
        _drop(snapshot, "delete from property_value where id in (1, 2, 5)")
        try:
            importer.run(db, snapshot)
        except importer.ImportRefused as refused:
            assert "한꺼번에 사라졌습니다" in str(refused)
        else:
            raise AssertionError("값 다섯 중 셋이 사라졌는데 그대로 적재했다")

    def test_빠진_값은_대표가_못_되고_상세가_표시를_싣는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """대표값은 덱 · 비교 · Ashby 가 쓰는 값이다 — 원본이 버린 값을 계속 내면 안 된다."""
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        # SUS304 의 영률 둘 중 대표(193 GPa, 1등급)를 원본이 지웠다.
        _drop(snapshot, "delete from property_value where id = 1")
        importer.run(db, snapshot)
        db.commit()
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        assert sus is not None

        detail = client.get(f"/api/catalog/materials/{sus.id}", headers=admin_headers)
        assert detail.status_code == 200, detail.text
        modulus = {
            one["value_num"]: one
            for one in detail.json()["values"]
            if one["property_key"] == "mechanical.youngs_modulus"
        }
        assert modulus[193e9]["source_missing_at"] is not None
        assert modulus[193e9]["representative"] is False
        assert modulus[193e9]["separated_by"] == "원본에서 빠짐"
        assert modulus[200e9]["representative"] is True

        # 그 물성의 값이 **전부** 빠지면 대표가 없다 — 남은 것이 빠진 값뿐이어도 내지 않는다.
        _drop(snapshot, "delete from property_value where id = 2")
        importer.run(db, snapshot)
        db.commit()
        detail = client.get(f"/api/catalog/materials/{sus.id}", headers=admin_headers)
        both = [
            one
            for one in detail.json()["values"]
            if one["property_key"] == "mechanical.youngs_modulus"
        ]
        assert len(both) == 2, "빠진 값도 줄은 지킨다"
        assert all(one["representative"] is False for one in both)

    def test_값_범위_검색은_빠진_값을_찾지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        snapshot = make_snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        _drop(snapshot, "delete from property_value where id in (1, 2)")
        importer.run(db, snapshot)
        db.commit()
        asked = (
            "value_key=mechanical.youngs_modulus&value_unit=GPa&value_min=190&value_max=210"
        )
        got = client.get(f"/api/catalog/materials?{asked}", headers=admin_headers)
        assert got.status_code == 200, got.text
        assert got.json()["items"] == []


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


class Test목록_거르개:
    """목록의 제조사 · 분야 · 값 범위(2026-10-03). 내보내기도 같은 규칙으로 거른다.

    값 범위는 **조용히 틀리는 자리**다 — 단위를 잘못 풀면 8 Pa 짜리가 걸리고, 변수 달린 값
    (식의 상수)이 섞이면 그 물성이 아닌 값이 걸린다. 둘 다 결과만 봐서는 안 드러난다.
    """

    def _loaded(self, db: Session, tmp_path: Path) -> None:
        importer.run(db, make_snapshot(tmp_path))
        # 대소문자 · 공백만 다른 제조사 — 같은 회사다.
        spcc = CatalogMaterial(name="SPCC", category="metal", manufacturer="posco ")
        db.add(spcc)
        db.flush()
        # 영률 키에 섞인 **식의 상수** — 범위 안의 값이지만 영률이 아니다. 식의 변수는 한 벌의
        # 표지(`model` …)를 함께 단다 — `term` 만 있으면 구분이라 그 물성의 값이다
        # (`representative.is_term`, 원본의 변수 값은 모두 표지를 단다).
        db.add(
            CatalogValue(
                material_id=spcc.id,
                property_key="mechanical.youngs_modulus",
                value_num=195e9,
                unit="Pa",
                conditions={"term": "E0", "model": "prony"},
                quality_tier=2,
            )
        )
        db.commit()
        parameters.forget()

    def _names(self, client: TestClient, headers: dict[str, str], query: str) -> set[str]:
        got = client.get(f"/api/catalog/materials?{query}", headers=headers)
        assert got.status_code == 200, got.text
        return {one["name"] for one in got.json()["items"]}

    def test_제조사는_대소문자를_안_가리고_요약도_하나로_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        self._loaded(db, tmp_path)
        assert self._names(client, admin_headers, "manufacturer=POSCO") == {"SUS304", "SPCC"}
        summary = client.get("/api/catalog/summary", headers=admin_headers).json()
        assert list(summary["manufacturers"].values()) == [2]
        # 분야는 재료를 센다 — 값 수(영률 셋 · 포아송비)가 아니다.
        assert summary["materials_by_domain"]["mechanical"] == 2
        assert summary["domains"]["mechanical"] == 4

    def test_분야는_그_분야의_값이_있는_재료만(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        self._loaded(db, tmp_path)
        assert self._names(client, admin_headers, "domain=thermal") == {"FR-4 generic"}
        assert self._names(client, admin_headers, "domain=physical") == {"SUS304"}

    def test_값_범위는_물은_단위로_풀고_걸린_값을_그_단위로_싣는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        self._loaded(db, tmp_path)
        asked = (
            "value_key=mechanical.youngs_modulus&value_unit=GPa&value_min=190&value_max=210"
        )
        got = client.get(f"/api/catalog/materials?{asked}", headers=admin_headers)
        assert got.status_code == 200, got.text
        items = got.json()["items"]
        # SPCC 의 195 GPa 는 식의 상수(E0)라 안 걸린다.
        assert [one["name"] for one in items] == ["SUS304"]
        assert items[0]["matched"] == {"count": 2, "low": 193.0, "high": 200.0, "unit": "GPa"}
        # 범위를 안 걸면 걸린 값도 없다.
        plain = client.get("/api/catalog/materials?q=SUS", headers=admin_headers).json()
        assert plain["items"][0]["matched"] is None

        # 내보내기도 같은 규칙 — 화면에서 본 것과 받아 간 파일이 갈리지 않는다.
        exported = client.get(f"/api/catalog/export?{asked}", headers=admin_headers)
        assert exported.status_code == 200, exported.text
        assert [one["name"] for one in exported.json()["materials"]] == ["SUS304"]
        assert (
            self._names(
                client,
                admin_headers,
                "value_key=mechanical.youngs_modulus&value_unit=GPa&value_min=300",
            )
            == set()
        )

    def test_단위가_없거나_안_맞으면_거절한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        self._loaded(db, tmp_path)

        def code(query: str) -> str:
            got = client.get(f"/api/catalog/materials?{query}", headers=admin_headers)
            assert got.status_code in (404, 422), got.text
            return str(got.json()["error"]["code"])

        key = "value_key=mechanical.youngs_modulus"
        # 「200」 만으로는 Pa 인지 GPa 인지 모른다 — 짐작하면 조용히 틀린다.
        assert code(f"{key}&value_min=190") == "MNX-CATALOG-0067"
        assert code("value_unit=GPa&value_min=190") == "MNX-CATALOG-0067"
        assert code(f"{key}&value_unit=degC&value_min=190") == "MNX-CATALOG-0032"
        assert (
            code("value_key=mechanical.nope&value_unit=GPa&value_min=1") == "MNX-CATALOG-0066"
        )


class Test활용_화면_API:
    """비교·Ashby·커버리지 — 전부 대표값 기준이고 상세 화면과 같은 선택이다."""

    def _loaded(self, db: Session, tmp_path: Path) -> tuple[str, str]:
        importer.run(db, make_snapshot(tmp_path))
        db.commit()
        sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
        fr4 = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 2))
        assert sus is not None and fr4 is not None
        return str(sus.id), str(fr4.id)

    def test_비교_표가_대표값과_후보_수를_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        sus_id, fr4_id = self._loaded(db, tmp_path)
        got = client.get(f"/api/catalog/compare?ids={sus_id},{fr4_id}", headers=admin_headers)
        assert got.status_code == 200, got.text
        body = got.json()
        assert [one["name"] for one in body["materials"]] == ["SUS304", "FR-4 generic"]
        rows = {one["property_key"]: one for one in body["rows"]}
        youngs = rows["mechanical.youngs_modulus"]
        # SUS 칸: 대표(tier1, 193e9)와 후보 수 2. FR-4 칸: 빈 칸.
        assert youngs["cells"][0]["value_num"] == 193e9
        assert youngs["cells"][0]["quality_tier"] == 1
        assert youngs["cells"][0]["n_candidates"] == 2
        assert youngs["cells"][1]["value_num"] is None
        # 도메인 차례 — mechanical 이 physical·thermal 앞이 아니어도 되지만
        # 같은 도메인끼리 붙어 있어야 한다.
        domains = [one["domain"] for one in body["rows"]]
        assert domains == sorted(domains)

    def test_비교는_2에서_8종이다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        sus_id, _ = self._loaded(db, tmp_path)
        alone = client.get(f"/api/catalog/compare?ids={sus_id}", headers=admin_headers)
        assert alone.status_code == 422

    def test_Ashby_는_두_축을_다_가진_재료만_점이_된다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        self._loaded(db, tmp_path)
        got = client.get(
            "/api/catalog/ashby?x=mechanical.youngs_modulus&y=physical.density",
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["x_unit"] == "Pa" and body["y_unit"] == "kg/m^3"
        # FR-4 는 밀도가 없어 점이 못 된다. SUS 점은 대표값 좌표다.
        assert len(body["points"]) == 1
        point = body["points"][0]
        assert point["name"] == "SUS304"
        assert point["x"] == 193e9 and point["y"] == 7930
        assert point["group"] == "metal"

    def test_커버리지_격자가_계통과_도메인으로_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        self._loaded(db, tmp_path)
        got = client.get("/api/catalog/coverage", headers=admin_headers)
        assert got.status_code == 200, got.text
        body = got.json()
        # SUS(housing): 기계 3(E 둘+포아송비) + 물리 1(밀도). FR-4(미분류 ""): 열 1(Tg).
        assert body["cells"]["housing"]["mechanical"] == 3
        assert body["cells"]["housing"]["physical"] == 1
        assert body["cells"][""]["thermal"] == 1
        # 미분류는 맨 뒤에 선다.
        assert body["subsystems"][-1] == ""

    def test_축_후보는_재료_5종_미만이면_안_선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """시험 데이터는 물성마다 재료 1~2종뿐이라 축이 하나도 안 선다 —
        바닥값(5종)이 실제로 거르는지를 이것으로 문다."""
        self._loaded(db, tmp_path)
        got = client.get("/api/catalog/axes", headers=admin_headers)
        assert got.status_code == 200
        assert got.json() == []


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
        link_builtin(db)
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
                # SI 숫자를 대조하는 시험이라 SI 를 고른다 — 기본은 mm·N·tonne(ADR 0036).
                "units": "si",
            },
            headers=admin_headers,
        )
        assert built.status_code == 200, built.text
        body = built.json()
        assert "*MAT_ELASTIC" in body["text"]
        # 대표값(tier1, 193e9)이 실리고 — tier4 가정값이 아니다.
        assert "  1.93E+11" in body["text"]
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
        link_builtin(db)
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
        assert "  193000.0" in text  # 193 GPa → MPa
        assert "   7.93E-9" in text  # 7930 kg/m3 → tonne/mm3

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
