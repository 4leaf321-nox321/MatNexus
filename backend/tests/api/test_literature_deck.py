"""문헌 덱 — **사내 물성 매핑을 거쳐, 판정한 형식으로** (2026-09-28).

무는 것이 넷이다.

    형식은 판정한다     카드 내보내기와 같은 목록에서 문헌이 채울 수 있는 것만(곡선·JSON 빠짐)
    다른 솔버도 선다     Abaqus 는 재료마다 *MATERIAL, Radioss 는 /UNIT·/END 가 파일에 한 번
    매핑을 거친다        이은 것만 실리고(선팽창계수도), 안 이은 값은 각주가 말한다
    정의판도 같다        기본 형식의 정의판을 켜면 목록에 서고, 코드판과 같은 글자가 나온다

전에는 LS-DYNA 두 형식이 박혀 있었고, 문헌 키를 블록 칸으로 바로 옮기는 표가 사내
매핑과 따로 있었다 — 선팽창계수는 매핑에 이어져 있는데 그 표에 없어 안 실렸다.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from test_catalog import link_builtin, make_snapshot

from app.modules.catalog import importer
from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.fitting.models import ExportProfile
from app.shared import litdeck, literature_material
from matcore.export import template

SEED = (
    Path(__file__).resolve().parents[2] / "seeds" / "export-profiles" / "기본-형식-정의.json"
)

#: 스냅샷에 없는 정의 — (key, 이름, SI 단위). 차원이 사내 항목과 맞아야 기본 연결이 선다.
EXTRA = {
    "thermal.expansion_linear": ("선팽창계수", "1/K"),
    "mechanical.yield_strength": ("항복강도", "Pa"),
    "mechanical.tensile_strength": ("인장강도", "Pa"),
}


def load(db: Session, tmp_path: Path) -> tuple[uuid.UUID, uuid.UUID]:
    """스냅샷(SUS304 · FR-4)을 싣고 기본 연결을 깐다 — (SUS304, FR-4)."""
    importer.run(db, make_snapshot(tmp_path))
    for number, (key, (name, unit)) in enumerate(EXTRA.items(), start=801):
        db.add(
            CatalogDefinition(
                mt_id=number,
                key=key,
                domain=key.split(".", 1)[0],
                name=name,
                si_unit=unit,
                value_type="numeric",
            )
        )
    db.flush()
    link_builtin(db)
    db.commit()
    sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
    fr4 = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 2))
    assert sus is not None and fr4 is not None
    return sus.id, fr4.id


_NEXT = iter(range(900, 999))


def add_value(
    db: Session, material_id: uuid.UUID, key: str, number: float, unit: str, tier: int = 2
) -> None:
    db.add(
        CatalogValue(
            mt_id=next(_NEXT),
            material_id=material_id,
            property_key=key,
            value_num=number,
            unit=unit,
            quality_tier=tier,
        )
    )
    db.commit()


def give_fr4_elastic(db: Session, fr4: uuid.UUID) -> None:
    """FR-4 는 유리전이온도뿐이다 — 두 재료가 한 파일에 서게 탄성 셋을 준다."""
    add_value(db, fr4, "mechanical.youngs_modulus", 20e9, "Pa")
    add_value(db, fr4, "mechanical.poisson_ratio", 0.15, "1")
    add_value(db, fr4, "physical.density", 1850.0, "kg/m^3")


def build(
    client: TestClient,
    headers: dict[str, str],
    fmt: str,
    items: list[tuple[int, uuid.UUID]],
) -> Any:
    return client.post(
        "/api/catalog/deck/build",
        json={
            "items": [{"mid": mid, "catalog_material_id": str(one)} for mid, one in items],
            "format": fmt,
            "units": "si",
        },
        headers=headers,
    )


class Test형식은_판정한다:
    def test_문헌이_채울_수_있는_형식만_솔버와_함께_선다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        listed = client.get("/api/catalog/deck/formats", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        solver = {one["key"]: one["solver"] for one in listed.json()}
        # LS-DYNA 둘만이 아니다 — 솔버마다 선형·열 형식이 선다.
        for key in (
            "dyna_elastic",
            "dyna_thermal",
            "abaqus_elastic",
            "abaqus_thermal",
            "ansys_elastic",
            "nastran_elastic",
            "optistruct_elastic",
            "openradioss_elastic",
        ):
            assert key in solver, key
        assert solver["abaqus_elastic"] == "abaqus"
        assert solver["openradioss_elastic"] == "openradioss"
        # 곡선(소성 표)·점탄성 표를 요구하는 것, 여러 재료를 못 합치는 JSON 은 없다.
        for key in ("dyna", "abaqus", "openradioss", "abaqus_viscoelastic", "json"):
            assert key not in solver, key

    def test_곡선_형식은_이유와_함께_거절한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        sus, _ = load(db, tmp_path)
        refused = build(client, admin_headers, "openradioss", [(1, sus)])
        assert refused.status_code == 422
        message = refused.json()["error"]["message"]
        assert "곡선" in message and "openradioss_elastic" in message

    def test_이름_규약_밖의_정의는_확장자로_솔버를_안다(self) -> None:
        """화면에서 만든 정의는 key 가 `deck_1a2b3c4d` 다 — 앞부분이 솔버가 아니다.
        이름만 믿으면 합칠 때 솔버 규약을 못 찾는다. 정의가 `solver` 를 적으면 그것이
        이긴다."""
        definition = next(
            one["definition"]
            for one in json.loads(SEED.read_text(encoding="utf-8"))["profiles"]
            if one["key"] == "abaqus_elastic_def"
        )
        made = template.renderer_from_definition(
            {**definition, "key": "deck_1a2b3c4d", "label": "사업부 관례"}
        )
        assert litdeck.solver_of(made) == "abaqus"
        told = template.renderer_from_definition(
            {**definition, "key": "deck_1a2b3c4d", "label": "x", "solver": "optistruct"}
        )
        assert litdeck.solver_of(told) == "optistruct"


class Test다른_솔버도_선다:
    def test_Abaqus_는_재료마다_MATERIAL(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        sus, fr4 = load(db, tmp_path)
        give_fr4_elastic(db, fr4)
        made = build(client, admin_headers, "abaqus_elastic", [(1, sus), (2, fr4)])
        assert made.status_code == 200, made.text
        body = made.json()
        assert body["solver"] == "abaqus"
        assert body["filename"] == "matnexus_catalog_elastic_si.inp"
        assert body["material_count"] == 2
        text = body["text"]
        assert text.count("*MATERIAL, NAME=") == 2
        assert "1.930000000000E+11, 2.900000000000E-01" in text  # SUS304 E, nu
        assert "사내 물성 매핑을 거쳐" in text

    def test_Radioss_는_UNIT_과_END_가_파일에_한_번(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """Starter 는 첫 `/END` 에서 읽기를 멈춘다 — 재료마다 남으면 둘째부터 안 읽힌다.

        실측(2026-09-28, OpenRadioss): 전의 합치기로 낸 두 재료 파일에서 둘째 재료를
        가리키는 부품이 「MATERIAL ID DOES NOT EXIST」 였다.
        """
        sus, fr4 = load(db, tmp_path)
        give_fr4_elastic(db, fr4)
        made = build(client, admin_headers, "openradioss_elastic", [(1, sus), (2, fr4)])
        assert made.status_code == 200, made.text
        body = made.json()
        assert body["solver"] == "openradioss" and body["filename"].endswith(".rad")
        lines = body["text"].rstrip("\n").split("\n")
        assert lines.count("/END") == 1 and lines[-1] == "/END"
        assert sum(line.startswith("/UNIT/") for line in lines) == 1
        assert lines.count("#RADIOSS STARTER") == 1
        assert sum(line.startswith("/MAT/LAW1/") for line in lines) == 2
        # 두 재료가 다 /UNIT 뒤, /END 앞에 있다.
        unit = next(i for i, line in enumerate(lines) if line.startswith("/UNIT/"))
        mats = [i for i, line in enumerate(lines) if line.startswith("/MAT/LAW1/")]
        assert unit < mats[0] < mats[1] < len(lines) - 1


class Test매핑을_거친다:
    def test_선팽창계수가_실리고_사내_이름으로_각주가_선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """전의 표(`DECK_SLOTS`)에는 선팽창계수가 없어서, 문헌에 있어도 안 실렸다."""
        sus, _ = load(db, tmp_path)
        add_value(db, sus, "thermal.expansion_linear", 17.3e-6, "1/K")
        made = build(client, admin_headers, "abaqus_elastic", [(1, sus)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        assert "*EXPANSION" in text
        assert "선팽창계수(CTE) = 1.730000E-05" in text

    def test_각주는_블록에_실린_값에만(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """항복강도는 사내 항목과 이어져 옮겨지지만 탄성 덱의 블록에는 없다 — 덱 머리에
        「항복강도 = …」 가 서면 받는 사람은 덱에 들어간 줄 안다(2026-09-28 MCP 점검)."""
        sus, _ = load(db, tmp_path)
        add_value(db, sus, "mechanical.yield_strength", 215e6, "Pa", tier=1)
        made = build(client, admin_headers, "abaqus_elastic", [(1, sus)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        assert "탄성계수 = 1.930000E+11" in text
        assert "항복강도" not in text

    def test_안_이은_값은_안_싣고_각주가_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """매핑 화면에서 연결을 끊으면 덱에서도 빠진다 — 조용히가 아니라 이름을 대고."""
        sus, _ = load(db, tmp_path)
        add_value(db, sus, "thermal.expansion_linear", 17.3e-6, "1/K")
        db.execute(
            delete(PropertyLink).where(PropertyLink.property_key == "thermal.expansion_linear")
        )
        db.commit()
        made = build(client, admin_headers, "abaqus_elastic", [(1, sus)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        assert "*EXPANSION" not in text
        assert "사내 물성 항목과 이어지지 않아 안 실은 문헌 값: 선팽창계수(CTE)" in text

    def test_항복이_인장보다_크면_정합한_짝을_담는다(
        self, db: Session, tmp_path: Path
    ) -> None:
        """대표값은 물성마다 따로 뽑혀 출처가 섞일 수 있다 — 그대로 담으면 항복 > 인장인
        재료가 되고 곡선이 물리적으로 불가능하다. 등급 합이 가장 좋은 정합 짝을 담는다."""
        sus, _ = load(db, tmp_path)
        add_value(db, sus, "mechanical.yield_strength", 215e6, "Pa", tier=1)
        add_value(db, sus, "mechanical.tensile_strength", 200e6, "Pa", tier=1)
        add_value(db, sus, "mechanical.tensile_strength", 520e6, "Pa", tier=3)
        material = db.get(CatalogMaterial, sus)
        assert material is not None
        made = literature_material.virtual(db, material, synthesize=True)
        declared = {
            row["item"]: row["points"][0]["value_si"]
            for row in made.material.declared_properties or []
        }
        assert declared["항복강도"] == 215e6
        assert declared["인장강도"] == 520e6
        assert any("정합한 조합(항복 215 / 인장 520 MPa)" in line for line in made.provenance)
        # 합성을 안 켜면 그 말은 덱에 안 선다 — 항복·인장이 덱에 안 쓰인다.
        plain = literature_material.virtual(db, material)
        assert not any("정합한 조합" in line for line in plain.provenance)
        # 가상 재료는 DB 에 없다 — 덱을 낼 때마다 재료가 생기면 안 된다.
        assert made.material not in db


class Test정의판도_같다:
    def test_정의판을_켜면_목록에_서고_코드판과_같은_글자다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        sus, fr4 = load(db, tmp_path)
        give_fr4_elastic(db, fr4)
        seed = next(
            one
            for one in json.loads(SEED.read_text(encoding="utf-8"))["profiles"]
            if one["key"] == "openradioss_elastic_def"
        )
        db.add(
            ExportProfile(
                key=seed["key"],
                label=seed["label"],
                definition=seed["definition"],
                is_active=True,
            )
        )
        db.commit()
        listed = client.get("/api/catalog/deck/formats", headers=admin_headers).json()
        assert {"key": "openradioss_elastic_def", "solver": "openradioss"}.items() <= next(
            one for one in listed if one["key"] == "openradioss_elastic_def"
        ).items()

        items = [(1, sus), (2, fr4)]
        code = build(client, admin_headers, "openradioss_elastic", items)
        defined = build(client, admin_headers, "openradioss_elastic_def", items)
        assert code.status_code == 200 and defined.status_code == 200, defined.text
        # 합치기(한 /UNIT · 한 /END)까지 같다 — 정의판도 솔버 규약으로 합쳐진다.
        assert defined.json()["text"] == code.json()["text"]
