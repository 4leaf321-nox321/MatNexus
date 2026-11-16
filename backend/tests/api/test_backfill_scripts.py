"""배포가 도는 보정 · 점검 스크립트 — 2026-11-16 운영 배포에서 드러난 셋.

    문헌 등급 되살리기    `declared_catalog.match` 가 (등급, 값 id, SI 값) 셋을 돌려주게
                        바뀌었는데 `backfill_declared_catalog.py` 만 둘로 받아 배포마다
                        터졌다. 시험이 없었고 mypy 는 `scripts/` 를 안 본다
    정의 단위 숫자       직접 만든 정의(MPa)의 저장 숫자로 받아 온 줄은 값이 100만 배 틀린
                        줄이다 — 배포 보정이 근거(문헌 등급)를 붙이지도, 값을 바꾸지도 않는다
    보고서 요약          점검 스크립트의 **마지막 줄**을 요약으로 집어, 곡선 하강 분포의 마지막
                        재료군 줄이 전체처럼 찍혔다 — 「요약:」 줄을 집는다

스크립트의 `main` 은 부르지 않는다 — `SessionLocal` 로 개발 DB 에 붙는다. 판정 함수만
시험 DB 로.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.materials.models import Material

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _script(name: str) -> Any:
    """스크립트를 모듈로 읽는다 — `scripts` 는 꾸러미가 아니다."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"{name}_for_test", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mpa_value(db: Session, number: float) -> CatalogValue:
    """직접 만든 MPa 정의의 문헌 값 하나 — 저장 숫자는 MPa."""
    db.add(
        CatalogDefinition(
            key="local.mechanical.e_mpa",
            domain="mechanical",
            name="시험용 MPa 탄성률",
            si_unit="MPa",
            value_type="numeric",
        )
    )
    owner = CatalogMaterial(name="MPa 강", category="metal")
    paper = CatalogSource(kind="journal", title="MPa 로 적은 논문")
    db.add_all([owner, paper])
    db.flush()
    value = CatalogValue(
        material_id=owner.id,
        property_key="local.mechanical.e_mpa",
        value_num=number,
        unit="MPa",
        quality_tier=2,
        source_id=paper.id,
        method="measured",
    )
    db.add(value)
    db.commit()
    return value


def _adopted_row(value_si: float) -> dict[str, Any]:
    return {
        "item": "탄성계수",
        "points": [{"value": value_si, "value_si": value_si}],
        "source": "literature",
        "reference": "MPa 로 적은 논문 (문헌 물성 카탈로그, 실측)",
        "note": "문헌 물성 카탈로그에서 채택 — MPa 강",
    }


class Test문헌_등급_되살리기:
    def test_SI_로_맞는_받아_온_줄에는_그_문헌_값의_등급을_붙인다(self, db: Session) -> None:
        script = _script("backfill_declared_catalog")
        _mpa_value(db, 210000.0)
        made, said = script.evidence_for(db, _adopted_row(2.1e11), {"local.mechanical.e_mpa"})
        assert said == "등급 2"
        assert made is not None and made["catalog"]["tier"] == 2
        assert made["points"][0]["value_si"] == pytest.approx(2.1e11)

    def test_정의_단위_숫자로_들어간_줄은_근거도_안_붙이고_값도_안_바꾼다(
        self, db: Session
    ) -> None:
        """옛 화면 · MCP 가 MPa 숫자를 SI 인 줄 알고 받아 온 줄 — 210000 MPa 가 210000 Pa."""
        script = _script("backfill_declared_catalog")
        _mpa_value(db, 210000.0)
        row = _adopted_row(210000.0)
        made, said = script.evidence_for(db, row, {"local.mechanical.e_mpa"})
        assert made is None
        assert said == script.UNIT_SLIP
        assert row["points"][0]["value_si"] == 210000.0  # 받은 줄을 고치지 않았다


def test_칸_근거는_SI_로_맞는_문헌_값에만_붙는다(db: Session) -> None:
    """밀도 칸 7.85 가 g/cm3 로 저장된 문헌 값 7.85 와 **저장 숫자로만** 맞으면 근거를 안
    붙인다.

    붙이면 근거는 SI(7850)로 바로잡힌 값을, 칸은 7.85 를 들어 둘이 갈린다 — 그 칸은 단위부터
    볼 일이다.
    """
    script = _script("backfill_column_evidence")
    db.add(
        CatalogDefinition(
            key="physical.density",
            domain="physical",
            name="밀도",
            si_unit="kg/m3",
            value_type="numeric",
        )
    )
    owner = CatalogMaterial(name="g/cm3 강", category="metal")
    paper = CatalogSource(kind="journal", title="g/cm3 로 적은 논문")
    slipped = Material(
        record_name="단위 실수 강",
        family="Metal",
        category="Steel",
        grade="A",
        density_si=7.85,
    )
    right = Material(
        record_name="바른 강", family="Metal", category="Steel", grade="B", density_si=7850.0
    )
    db.add_all([owner, paper, slipped, right])
    db.flush()
    db.add_all(
        [
            CatalogValue(
                material_id=owner.id,
                property_key="physical.density",
                value_num=7.85,
                unit="g/cm3",
                quality_tier=1,
                source_id=paper.id,
                method="measured",
            ),
            CatalogLink(material_id=slipped.id, catalog_material_id=owner.id),
            CatalogLink(material_id=right.id, catalog_material_id=owner.id),
        ]
    )
    db.commit()

    found, reasons = script.plan(db)
    stamped = {material.record_name: row for material, _field, row, _ in found}
    assert set(stamped) == {"바른 강"}
    assert stamped["바른 강"]["points"][0]["value_si"] == pytest.approx(7850.0)
    assert reasons["숫자가 이어진 문헌 값과 다름"] == 1


class Test보고서_요약:
    def test_요약_줄이_있으면_그것을_마지막_줄보다_먼저_집는다(self) -> None:
        report = _script("ops_report")
        output = [
            "  인장 곡선 12건을 쟀습니다.",
            "  ■ Metal: 8건",
            "    경고를 받을 곡선: 지속 하강 3건(그중 항복점 현상 1건) · 큰 요철 2건",
            "  요약: 전체 지속 하강 3건",
            "  ■ Polymer: 4건",
            "    경고를 받을 곡선: 지속 하강 0건(그중 항복점 현상 0건) · 큰 요철 0건",
        ]
        assert report.head_of(output) == "전체 지속 하강 3건"
        assert report.head_of(output[:3]) == output[2].strip()  # 표지가 없으면 옛 규칙
        assert report.head_of([]) == "(출력 없음)"

    def test_곡선_하강_요약은_모든_재료군을_합친다(self) -> None:
        drops = _script("measure_curve_drops")
        rows = [
            ("M1", "Metal", 0.04, 0.03),  # 지속 하강 · 항복점 현상(≥ 2.5 %)
            ("M2", "Metal", 0.01, 0.008),  # 지속 하강
            ("M3", "Metal", 0.03, None),  # 큰 요철(곧 다시 오름)
            ("P1", "Polymer", 0.0, None),  # 마지막 재료군 — 경고 없음
        ]
        lines = drops.by_family(rows)
        assert (
            lines[-1].strip().startswith("경고를 받을 곡선: 지속 하강 0건")
        )  # 옛 요약이 집던 줄
        summary = drops.summary(rows)
        assert summary.startswith("요약:")
        assert "4건(재료군 2개)" in summary
        assert "지속 하강 2건(그중 항복점 현상 1건) · 큰 요철 1건" in summary
