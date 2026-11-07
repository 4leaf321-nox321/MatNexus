"""문헌 응력-변형률 한 벌 → 덱 — **지은 곡선보다 잰 곡선** (2026-11-08, ADR 0074).

무는 것:

    그 밖의 재료   인장 곡선이 소성 표가 된다 — 0.2 % 오프셋 항복부터, 최대 응력에서
                  자르고, E 는 카드의 것
    고무          벌이 없으면 그 곡선에 식을 맞춘다 — 벌 > 맞춤 > E/6, 압축 곡선도
    고르기        등급 · 모드 · 바탕 조건(노화 0) 차례 — 이름표 글자 차례가 아니다
    셈            BOM 은 잰 곡선을 쓴 줄을 「합성」 으로 세지 않는다
    미리보기      합성 곡선 미리보기가 「덱은 실측 곡선을 쓴다」 고 말한다
"""

from __future__ import annotations

import itertools
import math
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_literature_deck import load

from app.modules.catalog import parameters
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSeries,
    CatalogValue,
)
from app.shared import litdeck
from matcore import plastic_table

TENSILE = "mechanical.tensile_stress_at_strain"
COMPRESSIVE = "local.mechanical.compressive_stress_at_strain"

#: 이선형 강 — E 193 GPa(SUS304 스냅샷의 대표 E 와 같다) · 항복 250 MPa · 경화 2 GPa,
#: 30 % 에서 최대.
E = 193e9
SY0 = 250e6
H = 2e9
STRAINS_PCT = (0.0, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 33.0, 35.0)


def bilinear(pct: float) -> float:
    e = pct / 100.0
    if e <= SY0 / E:
        return E * e
    stress = SY0 + H * (e - SY0 / E)
    # 30 % 뒤는 네킹 — 공칭 응력이 내려간다.
    return stress if pct <= 30.0 else stress - 40e6 * (pct - 30.0)


def mooney(pct: float, c10: float, c01: float) -> float:
    """비압축 단축의 공칭 응력 P = 2(C10 + C01/λ)(λ - λ⁻²). 음의 변형률이면 압축."""
    stretch = 1.0 + pct / 100.0
    return 2.0 * (c10 + c01 / stretch) * (stretch - 1.0 / (stretch * stretch))


def define_keys(db: Session) -> None:
    for key, name in (
        (TENSILE, "지정 변형률에서의 인장응력"),
        (COMPRESSIVE, "압축 변형률별 공칭 응력"),
    ):
        db.add(
            CatalogDefinition(
                key=key,
                domain="mechanical",
                name=name,
                si_unit="Pa",
                value_type="numeric",
                condition_axes=["strain_pct", "temperature_k"],
            )
        )
    db.commit()


def add_curve(
    db: Session,
    material_id: uuid.UUID,
    key: str,
    points: list[tuple[float, float]],
    *,
    label: str,
    tier: int = 2,
    conditions: dict[str, Any] | None = None,
) -> CatalogSeries:
    """응력-변형률 한 벌 — 축은 %, 응력은 Pa(저장 꼴 그대로)."""
    series = CatalogSeries(
        material_id=material_id,
        kind="curve",
        label=label,
        x_key="strain_pct",
        columns=[key],
        conditions=conditions,
        method="measured",
        quality_tier=tier,
    )
    db.add(series)
    db.flush()
    for pct, stress in points:
        db.add(
            CatalogValue(
                material_id=material_id,
                property_key=key,
                series_id=series.id,
                value_num=stress,
                unit="Pa",
                quality_tier=tier,
                method="measured",
                conditions={**(conditions or {}), "strain_pct": pct},
            )
        )
    db.commit()
    return series


@pytest.fixture
def sus(db: Session, tmp_path: Path) -> CatalogMaterial:
    sus_id, _ = load(db, tmp_path)
    define_keys(db)
    material = db.get(CatalogMaterial, sus_id)
    assert material is not None and material.category == "metal"
    return material


@pytest.fixture
def rubber(sus: CatalogMaterial, db: Session) -> CatalogMaterial:
    """초탄성 벌이 없는 고무 — 스냅샷의 SUS304 를 고무로 돌린다(E 는 쓰지 않는다)."""
    sus.category = "rubber"
    db.commit()
    parameters.forget()
    return sus


class Test그_밖의_재료는_곡선이_소성_표가_된다:
    def test_오프셋_항복부터_최대_응력까지_진응력_진소성변형률(
        self, db: Session, sus: CatalogMaterial
    ) -> None:
        add_curve(
            db, sus.id, TENSILE, [(pct, bilinear(pct)) for pct in STRAINS_PCT], label="인장"
        )
        target = litdeck.find_format(db, "abaqus")
        deck = litdeck.literature_deck(db, sus, 1, synthesize=False, target=target)
        assert not isinstance(deck, str), deck
        table = deck.blocks[litdeck.SYNTHETIC_BLOCK]
        assert table["origin"] == "measured" and litdeck.curve_origin(deck) == "measured"
        rows = table["rows"]

        # 0.2 % 오프셋 항복을 손으로 — 경화 구간에서 e - s/E = 0.002 를 푼다.
        yield_strain = 0.002 / (1.0 - H / E) + SY0 / E
        yield_stress = SY0 + H * (yield_strain - SY0 / E)
        assert rows[0]["plastic_strain"] == 0.0
        assert rows[0]["true_stress"] == pytest.approx(
            yield_stress * (1 + yield_strain), rel=1e-9
        )
        # 끝 줄은 최대 응력 점(30 %) — 그 뒤 네킹 두 점은 안 든다. 식은 처리 단계와 같다.
        top = bilinear(30.0)
        assert rows[-1]["true_stress"] == pytest.approx(top * 1.3, rel=1e-12)
        assert rows[-1]["plastic_strain"] == pytest.approx(math.log(1.3) - top * 1.3 / E)
        # 단조 증가 — 솔버는 뒤섞인 표를 조용히 보간한다.
        assert all(
            b["plastic_strain"] > a["plastic_strain"] and b["true_stress"] > a["true_stress"]
            for a, b in itertools.pairwise(rows)
        )
        said = "\n".join(deck.provenance)
        assert "소성 표 = 문헌 실측 곡선 「인장」" in said
        assert f"{yield_stress / 1e6:.4g} MPa" in said and "30 %)에서 잘랐습니다" in said
        assert "합성" not in said

    def test_곡선_합성을_켜도_잰_곡선이_이긴다(
        self, db: Session, sus: CatalogMaterial
    ) -> None:
        add_curve(
            db, sus.id, TENSILE, [(pct, bilinear(pct)) for pct in STRAINS_PCT], label="인장"
        )
        deck = litdeck.literature_deck(
            db, sus, 1, synthesize=True, target=litdeck.find_format(db, "abaqus")
        )
        assert not isinstance(deck, str), deck
        assert deck.blocks[litdeck.SYNTHETIC_BLOCK]["origin"] == "measured"
        assert not any(line.startswith("합성 소성 표") for line in deck.provenance)

    def test_E_는_카드의_것이고_백분율을_비율로_읽는다(
        self, db: Session, sus: CatalogMaterial
    ) -> None:
        """곡선 기울기로 E 를 따로 재면 카드 안에서 탄성과 소성이 다른 재료가 된다."""
        points = [(pct, bilinear(pct)) for pct in STRAINS_PCT]
        add_curve(db, sus.id, TENSILE, points, label="인장")
        deck = litdeck.literature_deck(
            db, sus, 1, synthesize=False, target=litdeck.find_format(db, "abaqus")
        )
        assert not isinstance(deck, str)
        assert deck.blocks["elastic"]["values"]["youngs_modulus"] == E
        expected = plastic_table.from_nominal(
            [pct / 100 for pct, _ in points], [stress for _, stress in points], E
        )
        assert not isinstance(expected, str)
        assert deck.blocks[litdeck.SYNTHETIC_BLOCK]["rows"] == [
            dict(one) for one in expected.rows
        ]

    def test_등급이_좋은_곡선을_고르고_나머지를_말한다(
        self, db: Session, sus: CatalogMaterial
    ) -> None:
        add_curve(
            db,
            sus.id,
            TENSILE,
            [(pct, bilinear(pct) * 1.5) for pct in STRAINS_PCT],
            label="A 추정 곡선",
            tier=3,
        )
        add_curve(
            db, sus.id, TENSILE, [(pct, bilinear(pct)) for pct in STRAINS_PCT], label="B 실측"
        )
        deck = litdeck.literature_deck(
            db, sus, 1, synthesize=False, target=litdeck.find_format(db, "abaqus")
        )
        assert not isinstance(deck, str)
        assert deck.blocks[litdeck.SYNTHETIC_BLOCK]["rows"][-1][
            "true_stress"
        ] == pytest.approx(bilinear(30.0) * 1.3)
        assert any(
            "다른 응력-변형률 곡선 1벌(「A 추정 곡선」)" in one for one in deck.provenance
        )

    def test_탄성뿐인_곡선은_옮기지_않고_합성도_못_하면_그_까닭부터(
        self, db: Session, sus: CatalogMaterial
    ) -> None:
        add_curve(
            db,
            sus.id,
            TENSILE,
            [(pct, E * pct / 100) for pct in (0.0, 0.05, 0.1)],
            label="탄성",
        )
        target = litdeck.find_format(db, "abaqus")
        plain = litdeck.literature_deck(db, sus, 1, synthesize=False, target=target)
        assert not isinstance(plain, str)
        assert litdeck.SYNTHETIC_BLOCK not in plain.blocks
        assert any("0.2 % 오프셋 항복에 이르지 않습니다" in one for one in plain.provenance)
        # 합성할 스칼라(항복 · 인장)도 없다 — 곡선을 못 쓴 까닭이 앞에 선다.
        refused = litdeck.literature_deck(db, sus, 1, synthesize=True, target=target)
        assert isinstance(refused, str)
        assert refused.startswith("문헌 곡선 「탄성」 을 소성 표로 옮기지 않았습니다")
        assert refused.endswith(litdeck.SYNTH_MISSING)

    def test_미리보기는_덱이_잰_곡선을_쓴다고_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        sus: CatalogMaterial,
    ) -> None:
        add_curve(
            db, sus.id, TENSILE, [(pct, bilinear(pct)) for pct in STRAINS_PCT], label="인장"
        )
        # 합성할 항복 스칼라 — 정의와 연결은 `load` 가 깔았다.
        db.add(
            CatalogValue(
                material_id=sus.id,
                property_key="mechanical.yield_strength",
                value_num=215e6,
                unit="Pa",
                quality_tier=2,
            )
        )
        db.commit()
        got = client.get(
            f"/api/catalog/materials/{sus.id}/synthetic-curve", headers=admin_headers
        )
        assert got.status_code == 200, got.text
        assert got.json()["ok"], got.json()
        assert any(
            "덱은 이 합성 곡선 대신 문헌 실측 곡선 「인장」" in one
            for one in got.json()["notes"]
        )


class Test고무는_곡선에_초탄성을_맞춘다:
    C10, C01 = 0.2e6, 0.05e6

    def _curve(self, scale: float = 1.0) -> list[tuple[float, float]]:
        return [
            (pct, mooney(pct, self.C10 * scale, self.C01 * scale))
            for pct in np.linspace(2.0, 200.0, 40)
        ]

    def test_벌이_없으면_곡선에_맞추고_합성을_안_켜도_쓴다(
        self, db: Session, rubber: CatalogMaterial
    ) -> None:
        add_curve(db, rubber.id, TENSILE, self._curve(), label="인장 평균")
        target = litdeck.find_format(db, "abaqus_hyperelastic")
        deck = litdeck.literature_deck(db, rubber, 1, synthesize=False, target=target)
        assert not isinstance(deck, str), deck
        block = deck.blocks["hyperelastic"]
        assert block["origin"] == "fitted" and litdeck.curve_origin(deck) == "fitted"
        values = block["values"]
        assert values["family"] == "mooney_rivlin"
        assert values["label"] == "Mooney-Rivlin (문헌 곡선 맞춤)"
        assert values["mode"] == "단축 인장"
        terms = {row["name"]: row["value"] for row in block["rows"]}
        assert terms["c10"] == pytest.approx(self.C10, rel=1e-4)
        assert terms["c01"] == pytest.approx(self.C01, rel=1e-4)
        assert values["strain_max"] == pytest.approx(2.0)
        said = "\n".join(deck.provenance)
        assert "초탄성 = Mooney-Rivlin — 문헌 곡선 「인장 평균」(단축 인장 공칭 40점" in said
        assert "출판된 벌이 아니라" in said and "견준 식(상대 RMSE)" in said
        assert "단축 인장 하나로 맞춘 계수" in said
        assert "합성 초탄성" not in said

    def test_압축_곡선뿐이면_압축으로_맞춘다(
        self, db: Session, rubber: CatalogMaterial
    ) -> None:
        # 압축은 양수로 적혀 있다(εc = -ε, σc = -P).
        points: list[tuple[float, float]] = [
            (float(pct), -mooney(-pct, self.C10, self.C01))
            for pct in np.linspace(1.0, 50.0, 30)
        ]
        add_curve(db, rubber.id, COMPRESSIVE, points, label="압축 평균")
        deck = litdeck.literature_deck(
            db,
            rubber,
            1,
            synthesize=False,
            target=litdeck.find_format(db, "abaqus_hyperelastic"),
        )
        assert not isinstance(deck, str), deck
        block = deck.blocks["hyperelastic"]
        assert block["values"]["mode"] == "단축 압축"
        terms = {row["name"]: row["value"] for row in block["rows"]}
        assert terms["c10"] == pytest.approx(self.C10, rel=1e-4)
        assert terms["c01"] == pytest.approx(self.C01, rel=1e-4)
        assert any("단축 압축 하나로 맞춘 계수" in one for one in deck.provenance)

    def test_바탕_조건의_곡선이_노화한_곡선보다_앞선다(
        self, db: Session, rubber: CatalogMaterial
    ) -> None:
        """이름표 글자 차례가 아니다 — 「A …」 가 앞서도 노화 840 시간은 바탕 곡선에 진다."""
        add_curve(
            db,
            rubber.id,
            TENSILE,
            self._curve(scale=2.0),
            label="A 노화",
            conditions={"aging_hours": 840, "storage_environment": "DI water"},
        )
        add_curve(
            db,
            rubber.id,
            TENSILE,
            self._curve(),
            label="B 바탕",
            conditions={"aging_hours": 0, "storage_environment": "none"},
        )
        deck = litdeck.literature_deck(
            db,
            rubber,
            1,
            synthesize=False,
            target=litdeck.find_format(db, "abaqus_hyperelastic"),
        )
        assert not isinstance(deck, str)
        terms = {row["name"]: row["value"] for row in deck.blocks["hyperelastic"]["rows"]}
        assert terms["c10"] == pytest.approx(self.C10, rel=1e-4)
        assert any("다른 응력-변형률 곡선 1벌(「A 노화」)" in one for one in deck.provenance)

    def test_인장이_압축보다_앞선다(self, db: Session, rubber: CatalogMaterial) -> None:
        add_curve(
            db,
            rubber.id,
            COMPRESSIVE,
            [
                (pct, -mooney(-pct, 2 * self.C10, 2 * self.C01))
                for pct in np.linspace(1, 50, 30)
            ],
            label="A 압축",
        )
        add_curve(db, rubber.id, TENSILE, self._curve(), label="B 인장")
        deck = litdeck.literature_deck(
            db,
            rubber,
            1,
            synthesize=False,
            target=litdeck.find_format(db, "abaqus_hyperelastic"),
        )
        assert not isinstance(deck, str)
        assert deck.blocks["hyperelastic"]["values"]["mode"] == "단축 인장"

    def test_출판된_벌이_있으면_맞추지_않는다(
        self, db: Session, rubber: CatalogMaterial
    ) -> None:
        key = "mechanical.hyperelastic_coefficient"
        db.add(
            CatalogDefinition(
                mt_id=880,
                key=key,
                domain="mechanical",
                name="초탄성 계수",
                si_unit="Pa",
                value_type="numeric",
            )
        )
        db.flush()
        db.add(
            CatalogValue(
                material_id=rubber.id,
                property_key=key,
                value_num=600000.0,
                unit="Pa",
                quality_tier=2,
                conditions={"term": "mu", "model": "neo_hookean", "set_id": "a2020"},
            )
        )
        db.commit()
        parameters.forget()
        add_curve(db, rubber.id, TENSILE, self._curve(), label="인장 평균")
        deck = litdeck.literature_deck(
            db,
            rubber,
            1,
            synthesize=True,
            target=litdeck.find_format(db, "abaqus_hyperelastic"),
        )
        assert not isinstance(deck, str)
        block = deck.blocks["hyperelastic"]
        assert block["origin"] == "set" and "(문헌 벌)" in block["values"]["label"]
        assert litdeck.curve_origin(deck) is None
        assert not any("문헌 곡선 「" in one for one in deck.provenance)

    def test_고무_곡선은_소성_표로_옮기지_않는다(
        self, db: Session, rubber: CatalogMaterial
    ) -> None:
        add_curve(db, rubber.id, TENSILE, self._curve(), label="인장 평균")
        deck = litdeck.assemble(db, rubber, target=litdeck.find_format(db, "abaqus"))
        assert not isinstance(deck, str)
        assert litdeck.SYNTHETIC_BLOCK not in deck.blocks


class TestBOM_은_잰_곡선을_합성으로_세지_않는다:
    def _bom(
        self, client: TestClient, headers: dict[str, str], material: CatalogMaterial
    ) -> Any:
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {
                        "mid": 5,
                        "name": material.name,
                        "catalog_material_id": str(material.id),
                        "synthesize": True,
                    }
                ],
                "units": "si",
            },
            headers=headers,
        )
        assert body.status_code == 200, body.text
        return body.json()

    def test_금속_줄은_실측_곡선으로(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        sus: CatalogMaterial,
    ) -> None:
        add_curve(
            db, sus.id, TENSILE, [(pct, bilinear(pct)) for pct in STRAINS_PCT], label="인장"
        )
        made = self._bom(client, admin_headers, sus)
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in made["text"]
        assert "문헌 실측 곡선" in made["text"] and "합성 소성 표" not in made["text"]
        assert made["measured_curve_count"] == 1
        assert made["synthetic_count"] == 0 and made["literature_count"] == 0

    def test_고무_줄은_곡선에_맞춘_초탄성으로(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        rubber: CatalogMaterial,
    ) -> None:
        add_curve(
            db,
            rubber.id,
            TENSILE,
            Test고무는_곡선에_초탄성을_맞춘다()._curve(),
            label="인장 평균",
        )
        made = self._bom(client, admin_headers, rubber)
        assert "*MAT_MOONEY-RIVLIN_RUBBER" in made["text"]
        # LS-DYNA 덱은 블록 이름표를 안 찍는다 — 각주가 어디서 왔는지 말한다.
        assert (
            "문헌 곡선 「인장 평균」" in made["text"] and "출판된 벌이 아니라" in made["text"]
        )
        assert "합성 초탄성" not in made["text"]
        assert made["measured_curve_count"] == 1 and made["synthetic_count"] == 0
