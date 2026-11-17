"""BOM 덱의 탄성 대체 보고 · 받은 덱의 값 · 덱 계보 (2026-11-17, HWAX 연결).

무는 것:

    탄성 대체는 빠짐없이 적힌다      소성 표 없는 카드 · 문헌 줄 · 항복 없이 지은 표
    reject 면 탄성 재료가 0건       그 줄은 `skipped`, 다른 카드의 소성 표가 있으면 그것
    사람이 고른 탄성은 대체가 아니다  `format` · `lit_format`
    받은 덱의 ro · e · pr 을 지킨다   같은 MID 면 그 덱 값, 없는 MID 는 알린다, LS-DYNA 만
    계보                              줄마다 카드 · 재료 · 근거 시험, 덱 머리, 덱 글자 → MID
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_bom_deck import catalog_ids, make_card
from test_trash import _tree

from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material, Specimen
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from matcore import export, synth

ELASTIC_ONLY = {
    "elastic": {"values": {"youngs_modulus": 70e9, "poisson_ratio": 0.33, "density": 2700.0}}
}
PLASTIC = {
    **ELASTIC_ONLY,
    "table": {
        "rows": [
            {"plastic_strain": 0.0, "true_stress": 200e6},
            {"plastic_strain": 0.05, "true_stress": 260e6},
        ]
    },
}


def _card_with_run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    blocks: dict[str, Any],
    *,
    details: str = "MDOI",
    status: str = "published",
    notes: list[str] | None = None,
) -> tuple[Material, PropertyCard, TestRun]:
    """재료 → 시편 → 시험 하나, 그 시험을 근거로 둔 카드."""
    ensure_builtin_test_types(db)
    made = _tree(client, headers, details=details)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    specimen = db.get(Specimen, uuid.UUID(made["specimen"]["id"]))
    assert tensile is not None and specimen is not None
    run = TestRun(
        workspace_id=specimen.workspace_id,
        specimen_id=specimen.id,
        test_type_id=tensile.id,
        seq_no=1,
        record_name=f"LINEAGE_{details}",
        status="parsed",
    )
    db.add(run)
    db.flush()
    card = PropertyCard(
        material_id=uuid.UUID(made["material"]["id"]),
        test_type_id=tensile.id,
        orientation="MD",
        label="계보",
        status=status,
        blocks=blocks,
        source={
            "test_run_ids": [str(run.id)],
            "record_names": [run.record_name],
            "sample_count": 1,
            "notes": notes or [],
        },
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    db.refresh(run)
    material = db.get(Material, card.material_id)
    assert material is not None
    return material, card, run


def _bom(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    return client.post(
        "/api/fitting/decks/bom", json={"units": "mm_n_tonne", **body}, headers=headers
    )


class Test탄성_대체_보고:
    def test_소성_표_없는_카드는_탄성으로_나가되_빠짐없이_적힌다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, card, run = _card_with_run(client, db, admin_headers, ELASTIC_ONLY)
        made = _bom(
            client,
            admin_headers,
            rows=[{"mid": 4, "name": "브래킷", "material_id": str(material.id)}],
        )
        assert made.status_code == 200, made.text
        body = made.json()
        assert "*MAT_ELASTIC" in body["text"]
        assert [(one["mid"], one["kind"], one["format"]) for one in body["fallbacks"]] == [
            (4, "elastic", "dyna_elastic")
        ]
        # 계보 — 서버가 고른 카드 · 재료 · 근거 시험이 줄에 실린다.
        row = body["rows"][0]
        assert row["status"] == "rendered" and row["fallback"] == "elastic"
        assert row["card_code"] == card.code and row["material_code"] == material.code
        assert row["test_run_ids"] == [str(run.id)] and row["test_run_codes"] == [run.code]

    def test_reject_면_그_줄은_빠지고_탄성_재료는_0건(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _, plastic = make_card(db)
        material, _, _ = _card_with_run(client, db, admin_headers, ELASTIC_ONLY)
        made = _bom(
            client,
            admin_headers,
            on_missing_yield="reject",
            rows=[
                {"mid": 1, "name": "필러", "card_id": str(plastic.id)},
                {"mid": 2, "name": "브래킷", "material_id": str(material.id)},
            ],
        )
        assert made.status_code == 200, made.text
        body = made.json()
        assert "*MAT_ELASTIC" not in body["text"]
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in body["text"]
        assert body["fallbacks"] == []
        assert [one["mid"] for one in body["skipped"]] == [2]
        assert "on_missing_yield=reject" in body["skipped"][0]["why"]

    def test_reject_면_다른_카드의_소성_표를_고른다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """확정 카드가 먼저다 — 그 카드가 탄성뿐이면 초안의 소성 표를 두고 탄성으로 나갔다."""
        material, _, _ = _card_with_run(client, db, admin_headers, ELASTIC_ONLY)
        draft = PropertyCard(
            material_id=material.id, label="초안 곡선", status="draft", blocks=PLASTIC
        )
        db.add(draft)
        db.commit()
        rows = [{"mid": 3, "name": "브래킷", "material_id": str(material.id)}]
        elastic = _bom(client, admin_headers, rows=rows).json()
        assert elastic["rows"][0]["fallback"] == "elastic"
        rejected = _bom(client, admin_headers, rows=rows, on_missing_yield="reject").json()
        assert rejected["rows"][0]["card_id"] == str(draft.id)
        assert rejected["rows"][0]["fallback"] is None
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in rejected["text"]

    def test_사람이_고른_탄성_형식은_대체가_아니다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, _, _ = _card_with_run(client, db, admin_headers, ELASTIC_ONLY)
        made = _bom(
            client,
            admin_headers,
            format="dyna_elastic",
            on_missing_yield="reject",
            rows=[{"mid": 5, "name": "브래킷", "material_id": str(material.id)}],
        ).json()
        assert made["fallbacks"] == [] and made["skipped"] == []
        assert "*MAT_ELASTIC" in made["text"]

    def test_문헌_줄의_탄성도_대체로_적히고_reject_면_빠진다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        _, plastic = make_card(db)
        ids = catalog_ids(db, tmp_path)
        rows = [
            {"mid": 1, "name": "필러", "card_id": str(plastic.id)},
            {"mid": 2, "name": "SUS304", "catalog_material_id": str(ids["sus"])},
        ]
        elastic = _bom(client, admin_headers, rows=rows).json()
        assert [(one["mid"], one["kind"]) for one in elastic["fallbacks"]] == [(2, "elastic")]
        assert "곡선 합성" in elastic["fallbacks"][0]["why"]
        assert elastic["rows"][1]["catalog_material_id"] == str(ids["sus"])
        rejected = _bom(client, admin_headers, rows=rows, on_missing_yield="reject").json()
        assert "*MAT_ELASTIC" not in rejected["text"]
        assert [one["mid"] for one in rejected["skipped"]] == [2]
        # 사람이 문헌 형식을 고르면 대체가 아니다.
        chosen = _bom(client, admin_headers, rows=rows, lit_format="dyna_elastic").json()
        assert chosen["fallbacks"] == []

    def test_항복_없이_지은_표도_대체다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, _, _ = _card_with_run(
            client,
            db,
            admin_headers,
            PLASTIC,
            notes=[f"합성 소성 표 — 실측이 아니다. 모델: {synth.YIELD_FROM_UTS_MODEL}"],
        )
        rows = [{"mid": 6, "name": "힌지", "material_id": str(material.id)}]
        made = _bom(client, admin_headers, rows=rows).json()
        assert [one["kind"] for one in made["fallbacks"]] == ["yield_from_uts"]
        rejected = _bom(client, admin_headers, rows=rows, on_missing_yield="reject")
        # 줄이 하나뿐이라 덱이 비면 거절 — 그 까닭이 details 에 실린다.
        assert rejected.status_code == 422, rejected.text
        details = rejected.json()["error"]["details"]
        assert "인장강도를 평탄부로" in details["skipped"][0]["why"]
        assert details["rows"][0]["status"] == "skipped"


BASE_DECK = (
    "*KEYWORD\n"
    "*MAT_PIECEWISE_LINEAR_PLASTICITY\n"
    "$      mid        ro         e        pr      sigy\n"
    "         7   7.80E-9  200000.0      0.30     300.0\n"
    "*MAT_GENERAL_VISCOELASTIC\n"
    "         8   1.10E-9    3000.0\n"
    "*END\n"
)


class Test받은_덱의_값:
    def test_같은_MID_는_받은_덱의_ro_e_pr_로_나간다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _, card = make_card(db)  # E 205 GPa · ν 0.29 · ρ 7850
        made = _bom(
            client,
            admin_headers,
            keep_deck_values=True,
            base_deck=BASE_DECK,
            rows=[
                {"mid": 7, "name": "필러", "card_id": str(card.id)},
                {"mid": 9, "name": "없는 MID", "card_id": str(card.id)},
            ],
        )
        assert made.status_code == 200, made.text
        body = made.json()
        assert body["rows"][0]["kept"] == {"ro": 7.8e-9, "e": 200000.0, "pr": 0.3}
        assert body["rows"][1]["kept"] == {}
        text = body["text"]
        lines = text.splitlines()
        start = lines.index("*MAT_PIECEWISE_LINEAR_PLASTICITY")  # 첫 재료 — MID 7
        first = next(line for line in lines[start + 1 :] if not line.startswith("$"))
        # 고정 10칸 — mid · ro · e · pr 이 받은 덱의 값이다(205000 · 0.29 가 아니다).
        assert first[:10].strip() == "7"
        assert float(first[20:30]) == 200000.0 and float(first[30:40]) == 0.3
        assert "받은 덱의 값으로 둠(MID 7" in text
        assert any(
            "MID 라 MatNexus 의 ro · e · pr 로 냈습니다: 9" in one for one in body["notes"]
        )
        assert any("*MAT_GENERAL_VISCOELASTIC (MID 8)" in one for one in body["notes"])

    def test_LS_DYNA_가_아니거나_덱이_없으면_거절(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _, card = make_card(db)
        rows = [{"mid": 7, "name": "필러", "card_id": str(card.id)}]
        no_deck = _bom(client, admin_headers, keep_deck_values=True, rows=rows)
        assert no_deck.status_code == 422
        assert no_deck.json()["error"]["code"] == "MNX-FITTING-0055"
        abaqus = _bom(
            client,
            admin_headers,
            keep_deck_values=True,
            base_deck=BASE_DECK,
            format="abaqus",
            rows=rows,
        )
        assert abaqus.status_code == 422
        assert abaqus.json()["error"]["code"] == "MNX-FITTING-0055"


class Test계보:
    def test_카드_덱_머리에_재료_번호와_근거_시험(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, card, run = _card_with_run(client, db, admin_headers, PLASTIC)
        deck = client.get(
            f"/api/fitting/cards/{card.id}/export?format=dyna", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text
        assert f"근거: 재료 {material.code} · 시험 {run.code}" in deck.text

    def test_카드의_계보(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, card, run = _card_with_run(client, db, admin_headers, PLASTIC)
        got = client.get(f"/api/fitting/cards/{card.id}/lineage", headers=admin_headers)
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["material_code"] == material.code
        assert [one["code"] for one in body["test_runs"]] == [run.code]
        assert body["default_mid"] == export.solver_id_from(str(card.id))
        assert body["test_type"] == "tensile"

    def test_덱_글자에서_MID_로_카드와_문헌_재료를_찾는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        _, card, run = _card_with_run(client, db, admin_headers, PLASTIC)
        ids = catalog_ids(db, tmp_path)
        made = _bom(
            client,
            admin_headers,
            rows=[
                {"mid": 55, "name": "필러", "card_id": str(card.id)},
                {"mid": 56, "name": "SUS304", "catalog_material_id": str(ids["sus"])},
            ],
        ).json()
        found = client.post(
            "/api/fitting/decks/lineage", json={"deck": made["text"]}, headers=admin_headers
        )
        assert found.status_code == 200, found.text
        by_mid = {one["mid"]: one for one in found.json()["materials"]}
        assert by_mid[55]["card"]["card_code"] == card.code
        assert by_mid[55]["card"]["test_runs"][0]["code"] == run.code
        assert by_mid[56]["catalog_material_id"] == str(ids["sus"])
        only = client.post(
            "/api/fitting/decks/lineage",
            json={"deck": made["text"], "mid": 56},
            headers=admin_headers,
        ).json()
        assert [one["mid"] for one in only["materials"]] == [56]

    def test_주석이_없는_덱은_그렇다고_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        deck = "*KEYWORD\n*MAT_ELASTIC\n         3   7.85E-9  205000.0      0.29\n*END\n"
        got = client.post(
            "/api/fitting/decks/lineage", json={"deck": deck}, headers=admin_headers
        ).json()
        assert got["materials"][0]["mid"] == 3
        assert got["materials"][0]["note"].startswith("머리 주석에 출처가 없습니다")
