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

import itertools
import json
import uuid
from pathlib import Path
from typing import Any, ClassVar

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from test_catalog import link_builtin, make_snapshot

from app.modules.catalog import importer
from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.fitting.models import ExportProfile
from app.shared import litdeck, literature_material
from matcore import export
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


# 끝을 두지 않는다 — 99개로 끊었더니 시험이 늘어 한 워커에 몰리면 `StopIteration` 이 났다
# (2026-10-23). 시험마다 표를 비우므로 번호가 커져도 겹치지 않는다.
_NEXT = itertools.count(900)


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


class Test전기_광학:
    """문헌 덱에 전기 · 광학(2026-10-08). 전에는 탄성 · 열만 지어 AEDT · CST · n·k 표 같은
    형식을 문헌 재료로 아예 못 냈다.

    주파수 · 파장을 타는 항목은 **축 값마다 대표 하나씩** 표로 — 대표값 하나만 실으면 Dk 의
    분산이 통째로 빠진다. 여러 온도에 걸치면 한 온도의 점만 쓰고 뺀 수를 말한다. 각주는
    **그 덱이 읽는 블록의 값에만** — LS-DYNA 탄성 덱 머리에 유전율이 서면 안 된다.
    """

    KEYS = (
        ("electrical.dielectric_constant", "유전율"),
        ("electrical.dissipation_factor", "유전손실"),
        ("optical.refractive_index", "굴절률"),
    )

    def _load(self, db: Session, tmp_path: Path) -> uuid.UUID:
        _, fr4 = load(db, tmp_path)
        for number, (key, name) in enumerate(self.KEYS, start=850):
            db.add(
                CatalogDefinition(
                    mt_id=number,
                    key=key,
                    domain=key.split(".", 1)[0],
                    name=name,
                    si_unit="1",
                    value_type="numeric",
                )
            )
        db.flush()
        ensure_builtin_property_links(db)
        db.commit()
        give_fr4_elastic(db, fr4)
        return fr4

    def _at(
        self,
        db: Session,
        material: uuid.UUID,
        key: str,
        number: float,
        conditions: dict[str, Any],
        tier: int = 2,
    ) -> None:
        db.add(
            CatalogValue(
                mt_id=next(_NEXT),
                material_id=material,
                property_key=key,
                value_num=number,
                unit="1",
                quality_tier=tier,
                conditions=conditions,
            )
        )
        db.commit()

    def test_주파수_표로_싣고_다른_온도의_값은_빼고_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path)
        dk = "electrical.dielectric_constant"
        # 키 이름이 셋이다 — 같은 표(`standard_conditions.UNIT_KEYS`)로 읽는다.
        self._at(db, fr4, dk, 4.5, {"frequency_hz": 1e6, "temperature_c": 23})
        self._at(db, fr4, dk, 4.3, {"frequency_ghz": 1, "temperature_c": 23})
        self._at(db, fr4, dk, 4.35, {"frequency_MHz": 1000, "temperature_c": 23}, tier=3)
        self._at(db, fr4, dk, 4.2, {"frequency_hz": 1e10, "temperature_c": 23})
        self._at(db, fr4, dk, 4.9, {"frequency_hz": 1e9, "temperature_c": 100})
        df = "electrical.dissipation_factor"
        self._at(db, fr4, df, 0.015, {"frequency_hz": 1e6, "temperature_c": 23})
        self._at(db, fr4, df, 0.018, {"frequency_hz": 1e10, "temperature_c": 23})

        formats = {
            one["key"]
            for one in client.get("/api/catalog/deck/formats", headers=admin_headers).json()
        }
        assert {"aedt", "cst", "nk_table"} <= formats

        made = build(client, admin_headers, "aedt", [(1, fr4)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        assert "pwl($MNX1_permittivity,Freq)" in text
        # 1 GHz 는 등급이 좋은 4.3 이 대표다(같은 주파수의 4.35 는 tier 3).
        # 100 °C 의 4.9 는 빠진다.
        rows = [line.strip() for line in text.splitlines() if line.strip().startswith("Y(")]
        assert rows[0] == "Y('4.5', '4.3', '4.2')"
        assert "다른 온도에서 잰 값 1개는 안 실었습니다" in text
        assert "비유전율 = 4.300000E+00 (주파수 1e+09 Hz)" in text

        # 같은 재료를 LS-DYNA 탄성 덱으로 — 유전율은 덱이 안 읽으니 각주도 없다.
        dyna = build(client, admin_headers, "dyna_elastic", [(1, fr4)])
        assert dyna.status_code == 200, dyna.text
        assert "비유전율" not in dyna.json()["text"]
        assert "유전손실" not in dyna.json()["text"]

    def test_파장별_굴절률이_n_k_표가_된다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path)
        n = "optical.refractive_index"
        for nm, value in ((486.1, 1.59), (587.6, 1.585), (656.3, 1.582)):
            self._at(db, fr4, n, value, {"wavelength_nm": nm})
        made = build(client, admin_headers, "nk_table", [(1, fr4)])
        assert made.status_code == 200, made.text
        body = [
            line for line in made.json()["text"].splitlines() if line and line[0].isdigit()
        ]
        assert len(body) == 3, made.json()["text"]

    def test_한_주파수뿐이면_값_하나로_싣는다(self, db: Session, tmp_path: Path) -> None:
        """점이 하나면 표가 아니다 — 전처럼 대표값 하나와 그 주파수."""
        fr4 = self._load(db, tmp_path)
        self._at(db, fr4, "electrical.dielectric_constant", 4.4, {"frequency_hz": 1e9})
        material = db.get(CatalogMaterial, fr4)
        assert material is not None
        deck = litdeck.literature_deck(db, material, 1)
        assert not isinstance(deck, str)
        electrical = deck.blocks["electrical"]
        assert electrical["values"]["relative_permittivity"] == 4.4
        assert electrical["values"]["relative_permittivity_frequency_hz"] == 1e9
        assert not electrical.get("rows")


class Test문헌_Anand:
    """문헌 재료의 Anand 벌 → ANSYS `TB,RATE,,,,ANAND`(확장 `anand`, 2026-10-08).

    카탈로그에는 9항이 한 키(`mechanical.anand_constant`)에 항 이름 · 단위를 조건으로 들고
    있다. 문헌 덱은 그 벌을 모델 파라미터 블록으로 싣고, 덱이 항마다 단위를 읽어 옮긴다.
    """

    TERMS = (
        ("s0", 23.65, "MPa"),
        ("Q/R", 9580.0, "K"),
        ("A", 3175.0, "1/s"),
        ("xi", 4.0, "1"),
        ("m", 0.263, "1"),
        ("h0", 183000.0, "MPa"),
        ("s_hat", 31.3, "MPa"),
        ("n", 0.011, "1"),
        ("a", 1.77, "1"),
    )

    def test_벌이_덱이_되고_단위는_덱의_계로_옮긴다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        from app.modules.catalog import parameters

        _, fr4 = load(db, tmp_path)
        give_fr4_elastic(db, fr4)
        db.add(
            CatalogDefinition(
                mt_id=870,
                key="mechanical.anand_constant",
                domain="mechanical",
                name="Anand 점소성 상수",
                si_unit="1",
                value_type="numeric",
            )
        )
        db.flush()
        for name, value, unit in self.TERMS:
            db.add(
                CatalogValue(
                    mt_id=next(_NEXT),
                    material_id=fr4,
                    property_key="mechanical.anand_constant",
                    value_num=value,
                    unit="1",
                    quality_tier=2,
                    conditions={
                        "term": name,
                        "model": "anand",
                        "set_id": "basit2015",
                        "unit_of_term": unit,
                    },
                )
            )
        db.commit()
        parameters.forget()  # 「이 키가 파라미터형인가」 캐시 — 시험 사이에 남는다

        formats = {
            one["key"]
            for one in client.get("/api/catalog/deck/formats", headers=admin_headers).json()
        }
        assert "ansys_anand" in formats
        made = build(client, admin_headers, "ansys_anand", [(1, fr4)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        assert "TB,RATE,MNX_MAT,,,ANAND" in text
        tbdata = [
            float(one)
            for line in text.splitlines()
            if line.startswith("TBDATA,")
            for one in line.split(",")[2:]
        ]
        # SI 로 냈다 — 응력 셋은 Pa 로 옮긴다.
        assert tbdata[0] == 23.65e6 and tbdata[5] == 183000.0e6 and tbdata[1] == 9580.0
        assert "파라미터 벌 anand/basit2015 = 9항" in text


class Test초탄성_벌:
    """문헌 초탄성 벌 → 초탄성 블록(2026-10-08) — 문헌 덱과 사내 카드가 같은 규칙.

    벌이 여럿이면 문헌 덱은 정한 차례(등급 · 조건 없음 · 항이 많은 식)로 하나를 고르고 나머지를
    말한다. 사내 카드는 사람이 고른 벌만 쓰고, 둘을 고르면 거절한다.
    """

    KEY = "mechanical.hyperelastic_coefficient"
    #: (모델, set_id, 항들) — 계수는 Pa, 단위 칸(`unit_of_term`)은 비어 있다(문헌 그대로).
    SETS = (
        ("neo_hookean", "a2020", (("mu", 600000.0),)),
        ("yeoh_3", "b2021", (("C10", 300000.0), ("C20", -2000.0), ("C30", 150.0))),
        ("ogden_N3", "c2022", (("mu1", 1.0e5), ("mu2", 2.0e5), ("mu3", 3.0e5))),
    )

    def _load(self, db: Session, tmp_path: Path) -> uuid.UUID:
        from app.modules.catalog import parameters

        _, fr4 = load(db, tmp_path)
        give_fr4_elastic(db, fr4)
        db.add(
            CatalogDefinition(
                mt_id=880,
                key=self.KEY,
                domain="mechanical",
                name="초탄성 계수",
                si_unit="Pa",
                value_type="numeric",
            )
        )
        db.flush()
        for model, set_id, terms in self.SETS:
            for name, value in terms:
                db.add(
                    CatalogValue(
                        mt_id=next(_NEXT),
                        material_id=fr4,
                        property_key=self.KEY,
                        value_num=value,
                        unit="Pa",
                        quality_tier=2,
                        conditions={"term": name, "model": model, "set_id": set_id},
                    )
                )
        db.commit()
        parameters.forget()
        return fr4

    def test_문헌_덱은_하나를_고르고_나머지를_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path)
        made = build(client, admin_headers, "abaqus_hyperelastic", [(1, fr4)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        # 항이 많은 식(Yeoh)이 앞선다 — 계수는 SI 그대로(Pa).
        assert "*HYPERELASTIC, YEOH" in text
        assert "초탄성 = Yeoh — 문헌 벌 yeoh_3/b2021" in text
        assert "다른 초탄성 벌 1개(neo_hookean/a2020)" in text
        assert "덱이 받는 식이 아닙니다: ogden_N3" in text

    def test_사내_카드는_고른_벌을_초탄성으로_싣고_둘이면_거절한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path)
        made = client.post(
            "/api/materials",
            json={
                "family": "Polymer",
                "category": "Rubber",
                "grade": f"HY-{uuid.uuid4().hex[:6]}",
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        material = made.json()["id"]
        adopted = {}
        for model, set_id, _ in self.SETS[:2]:
            got = client.post(
                f"/api/materials/{material}/parameter-sets",
                json={
                    "property_key": self.KEY,
                    "catalog_material_id": str(fr4),
                    "model": model,
                    "set_id": set_id,
                },
                headers=admin_headers,
            )
            assert got.status_code == 201, got.text
            adopted[model] = got.json()["id"]

        card = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": material,
                "label": "문헌 초탄성",
                "parameter_set_ids": [adopted["neo_hookean"]],
            },
            headers=admin_headers,
        )
        assert card.status_code in (200, 201), card.text
        hyper = card.json()["blocks"]["hyperelastic"]
        assert hyper["values"]["family"] == "neo_hookean"
        # μ = 600 kPa → C10 = μ/2. 단위 칸이 비어 정의의 Pa 로 읽었다.
        assert hyper["rows"] == [{"name": "c10", "value": 300000.0, "si_unit": "Pa"}]
        assert "abaqus_hyperelastic" in card.json()["available_formats"]

        both = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": material,
                "label": "둘",
                "parameter_set_ids": list(adopted.values()),
            },
            headers=admin_headers,
        )
        assert both.status_code == 422
        assert both.json()["error"]["code"] == "MNX-FITTING-0046"


class Test초탄성_벌_고르기:
    """**모드와 큰 변형 안정성을 본다**(2026-10-23).

    전에는 등급 · 조건 · 식이 같으면 이름표(set_id 글자)가 정했다 — Ecoflex 00-20 의 압축
    Yeoh 가 uuid 순서로 뽑혔고 인장 33 % 에서 불안정했다. 계수는 그 실측 그대로다.
    """

    KEY = Test초탄성_벌.KEY
    #: 압축 곡선(0.5~25 %)에서 맞춘 Yeoh — 이름표가 앞선다(`a-…`).
    COMPRESSION = ("a-compression", "compression", (18815.5, 18948.8, -41042.4))
    #: 인장 곡선(7~354 %)에서 맞춘 Yeoh.
    TENSION = ("b-tension", "uniaxial tension", (21000.0, 897.4, -0.5306))

    def _load(
        self, db: Session, tmp_path: Path, sets: tuple[tuple[str, str, Any], ...]
    ) -> uuid.UUID:
        from app.modules.catalog import parameters

        _, fr4 = load(db, tmp_path)
        give_fr4_elastic(db, fr4)
        db.add(
            CatalogDefinition(
                mt_id=880,
                key=self.KEY,
                domain="mechanical",
                name="초탄성 계수",
                si_unit="Pa",
                value_type="numeric",
            )
        )
        db.flush()
        for set_id, mode, coefficients in sets:
            for name, value in zip(("C10", "C20", "C30"), coefficients, strict=True):
                db.add(
                    CatalogValue(
                        material_id=fr4,
                        property_key=self.KEY,
                        value_num=value,
                        unit="Pa",
                        quality_tier=3,
                        method="measured",
                        # 출처마다 모드 칸 이름이 다르다 — `mode` 와 `deformation_mode`.
                        conditions={
                            "term": name,
                            "model": "yeoh_3",
                            "set_id": set_id,
                            ("mode" if mode == "compression" else "deformation_mode"): mode,
                        },
                    )
                )
        db.commit()
        parameters.forget()
        return fr4

    def test_이름표가_앞서도_불안정한_압축_벌보다_인장_벌을_고른다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path, (self.COMPRESSION, self.TENSION))
        made = build(client, admin_headers, "abaqus_hyperelastic", [(1, fr4)])
        assert made.status_code == 200, made.text
        text = made.json()["text"]
        assert "문헌 벌 yeoh_3/b-tension" in text and "단축 인장 데이터" in text
        assert "한 모드(단축 인장)로 맞춘 계수입니다" in text
        # 밀린 벌은 모드와 깨지는 자리를 함께 말한다.
        assert "yeoh_3/a-compression · 단축 압축 · 인장 33 %" in text
        assert "주의:" not in text

    def test_같은_모드면_안정한_벌이_앞선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """모드가 같으면 안정성만 남는다 — 이름표가 앞선 불안정한 벌이 뽑히지 않는다."""
        unstable = ("a-tension-short", "tension", self.COMPRESSION[2])
        fr4 = self._load(db, tmp_path, (unstable, self.TENSION))
        text = build(client, admin_headers, "abaqus_hyperelastic", [(1, fr4)]).json()["text"]
        assert "문헌 벌 yeoh_3/b-tension" in text

    def test_둘_다_안정하면_인장_벌이_압축_벌보다_앞선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """안정성이 같으면 모드가 가른다 — 덱 기본값은 어떤 하중인지 모른다."""
        stable_compression = ("a-compression", "compression", (18815.5, 500.0, 10.0))
        fr4 = self._load(db, tmp_path, (stable_compression, self.TENSION))
        text = build(client, admin_headers, "abaqus_hyperelastic", [(1, fr4)]).json()["text"]
        assert "문헌 벌 yeoh_3/b-tension" in text
        assert "yeoh_3/a-compression · 단축 압축)" in text

    def test_벌이_불안정한_것뿐이면_쓰되_어디서_깨지는지_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path, (self.COMPRESSION,))
        text = build(client, admin_headers, "abaqus_hyperelastic", [(1, fr4)]).json()["text"]
        assert "문헌 벌 yeoh_3/a-compression" in text
        assert "주의: 이 초탄성 계수는 인장 33 % · 압축 29 % · 등이축 17 %" in text

    def test_사내_카드는_고른_벌을_바꾸지_않고_깨지는_자리를_근거에_적는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        fr4 = self._load(db, tmp_path, (self.COMPRESSION, self.TENSION))
        material = client.post(
            "/api/materials",
            json={
                "family": "Polymer",
                "category": "Rubber",
                "grade": f"HY-{uuid.uuid4().hex[:6]}",
            },
            headers=admin_headers,
        ).json()["id"]
        adopted = client.post(
            f"/api/materials/{material}/parameter-sets",
            json={
                "property_key": self.KEY,
                "catalog_material_id": str(fr4),
                "model": "yeoh_3",
                "set_id": "a-compression",
            },
            headers=admin_headers,
        )
        assert adopted.status_code == 201, adopted.text
        card = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": material,
                "label": "압축 Yeoh",
                "parameter_set_ids": [adopted.json()["id"]],
            },
            headers=admin_headers,
        )
        assert card.status_code in (200, 201), card.text
        body = card.json()
        assert body["blocks"]["hyperelastic"]["rows"][2]["value"] == -41042.4
        assert any(
            note.startswith("주의: 이 초탄성 계수는 인장 33 %")
            for note in body["source"]["notes"]
        )


class Test문헌_속도_의존:
    """문헌 Cowper-Symonds 짝 → 속도 블록(요약만) → 단일 곡선 덱이 그 비로 늘린다(2026-10-08).

    **C 와 p 는 같은 출처 · 같은 조건의 짝만** — 물성마다 대표를 따로 고르면 다른 논문의 C 와
    p 가 섞여 속도 효과가 자릿수째 틀린다.
    """

    def _material(self, db: Session, tmp_path: Path, *, same_source: bool) -> CatalogMaterial:
        from app.modules.catalog.models import CatalogSource

        sus, _ = load(db, tmp_path)
        add_value(db, sus, "mechanical.yield_strength", 215e6, "Pa")
        add_value(db, sus, "mechanical.tensile_strength", 520e6, "Pa")
        for number, (key, name, unit) in enumerate(
            (
                ("mechanical.cowper_symonds_c", "Cowper-Symonds C", "1/s"),
                ("mechanical.cowper_symonds_p", "Cowper-Symonds p", "1"),
            ),
            start=890,
        ):
            db.add(
                CatalogDefinition(
                    mt_id=number,
                    key=key,
                    domain="mechanical",
                    name=name,
                    si_unit=unit,
                    value_type="numeric",
                )
            )
        first = CatalogSource(kind="journal", title="A 논문", year=2001)
        second = CatalogSource(kind="journal", title="B 논문", year=2002)
        db.add_all([first, second])
        db.flush()
        cited = {"reference_strain_rate_s": 0.001}
        for key, value, source in (
            ("mechanical.cowper_symonds_c", 40.4, first),
            ("mechanical.cowper_symonds_p", 5.0, first if same_source else second),
        ):
            db.add(
                CatalogValue(
                    mt_id=next(_NEXT),
                    material_id=sus,
                    property_key=key,
                    value_num=value,
                    unit="1",
                    quality_tier=2,
                    source_id=source.id,
                    conditions=cited,
                )
            )
        db.commit()
        material = db.get(CatalogMaterial, sus)
        assert material is not None
        return material

    def test_같은_출처의_짝이면_C_P_칸에_싣는다(self, db: Session, tmp_path: Path) -> None:
        material = self._material(db, tmp_path, same_source=True)
        target = litdeck.find_format(db, "dyna")
        deck = litdeck.literature_deck(db, material, 7, synthesize=True, target=target)
        assert not isinstance(deck, str), deck
        assert deck.blocks["rate_table"]["values"] == {
            "model": "cowper_symonds",
            "cs_d": 40.4,
            "cs_p": 5.0,
            "reference_rate": 0.001,
        }
        assert any(line.startswith("Cowper-Symonds D = 40.4 1/s") for line in deck.provenance)
        text = export.render(target, deck, export.SYSTEMS[0]).text
        lines = [line for line in text.splitlines() if not line.startswith("$")]
        card2 = lines[lines.index("*MAT_PIECEWISE_LINEAR_PLASTICITY") + 2]
        assert float(card2[0:10]) == 40.4 and float(card2[10:20]) == 5.0

    def test_출처가_다르면_짝이_아니라_안_싣는다(self, db: Session, tmp_path: Path) -> None:
        material = self._material(db, tmp_path, same_source=False)
        deck = litdeck.literature_deck(
            db, material, 7, synthesize=True, target=litdeck.find_format(db, "dyna")
        )
        assert not isinstance(deck, str), deck
        assert "rate_table" not in deck.blocks


class Test문헌_흡습:
    """문헌 흡습 값 → 흡습 블록 → ANSYS 흡습 스니펫(2026-10-08).

    **고를 것이 둘이다.** 확산계수 키에는 물 말고 용융 Sn 속 Cu 도 살고(대표값을 그대로 쓰면
    솔더의 흡습 확산계수 자리에 Cu 의 값이 선다), 포화 농도는 환경(온도 · 습도)마다 다르다.
    """

    KEYS = (
        ("physical.diffusion_coefficient", "확산계수", "m^2/s"),
        ("physical.moisture_saturation", "포화 수분농도 Csat", "mol/m^3"),
        ("physical.hygroscopic_expansion", "흡습팽창계수 CHE", "m^3/kg"),
    )

    def _material(
        self,
        db: Session,
        tmp_path: Path,
        values: list[tuple[str, float, str, int, dict[str, Any]]],
    ) -> CatalogMaterial:
        """`(키, 값, 출처 이름, 등급, 조건)` 들을 SUS304 자리에 싣는다."""
        from app.modules.catalog.models import CatalogSource

        sus, _ = load(db, tmp_path)
        for number, (key, name, unit) in enumerate(self.KEYS, start=880):
            db.add(
                CatalogDefinition(
                    mt_id=number,
                    key=key,
                    domain="physical",
                    name=name,
                    si_unit=unit,
                    value_type="numeric",
                )
            )
        sources: dict[str, CatalogSource] = {}
        for _, _, title, _, _ in values:
            if title not in sources:
                sources[title] = CatalogSource(kind="journal", title=title, year=2004)
        db.add_all(sources.values())
        db.flush()
        for key, value, title, tier, conditions in values:
            db.add(
                CatalogValue(
                    mt_id=next(_NEXT),
                    material_id=sus,
                    property_key=key,
                    value_num=value,
                    unit="1",
                    quality_tier=tier,
                    source_id=sources[title].id,
                    conditions=conditions,
                )
            )
        db.commit()
        material = db.get(CatalogMaterial, sus)
        assert material is not None
        return material

    WET: ClassVar[dict[str, Any]] = {
        "species": "H2O (moisture)",
        "temperature_c": 85.0,
        "humidity_pct": 85,
    }
    DRY: ClassVar[dict[str, Any]] = {
        "species": "H2O",
        "temperature_c": 30.0,
        "humidity_pct": 60,
    }

    def test_물의_값만_한_환경으로_고르고_몰농도를_질량_농도로_옮긴다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        material = self._material(
            db,
            tmp_path,
            [
                ("physical.diffusion_coefficient", 2.5e-13, "A 논문", 1, self.WET),
                ("physical.diffusion_coefficient", 1.0e-13, "A 논문", 1, self.DRY),
                # 용융 Sn 속 Cu — 종 칸 없이 계를 글로 적었다. 습도도 없다.
                (
                    "physical.diffusion_coefficient",
                    3.16e-9,
                    "솔더 논문",
                    1,
                    {"system": "Cu diffusing in molten Sn", "temperature_c": 250},
                ),
                # 같은 환경 · 등급이 더 좋은 다른 출처 — 확산계수를 낸 출처(A)가 이긴다.
                ("physical.moisture_saturation", 300.0, "B 논문", 1, self.WET),
                ("physical.moisture_saturation", 220.2, "A 논문", 2, self.WET),
                ("physical.moisture_saturation", 150.0, "A 논문", 2, self.DRY),
                # 같은 온도 · 다른 습도 — 등급이 더 좋아도 85 %RH 의 포화 농도가 아니다.
                (
                    "physical.moisture_saturation",
                    212.9,
                    "A 논문",
                    1,
                    {"species": "H2O", "temperature_c": 85.0, "humidity_pct": 60},
                ),
                ("physical.hygroscopic_expansion", 1.7e-4, "C 논문", 1, {"temperature_c": 85}),
            ],
        )
        target = litdeck.find_format(db, "ansys_moisture")
        deck = litdeck.literature_deck(db, material, 7, target=target)
        assert not isinstance(deck, str), deck
        assert deck.blocks["moisture"]["values"] == {
            "moisture_saturation": 220.2 * 0.018015,
            "moisture_diffusivity": 2.5e-13,
            "hygroscopic_expansion": 1.7e-4,
            "temperature": 358.15,
            "humidity": 0.85,
        }
        said = "\n".join(deck.provenance)
        assert "흡습 환경 = 85 °C · RH 85 %" in said
        assert "확산 종이 물이 아닌 확산계수 1개는 안 썼습니다." in said
        assert "다른 환경의 흡습 값은 안 썼습니다: 30 °C · RH 60 %, 85 °C · RH 60 %." in said

        built = build(client, admin_headers, "ansys_moisture", [(7, material.id)])
        assert built.status_code == 200, built.text
        text = built.json()["text"]
        assert "MP,DXX,MNX_MAT,2.500000000000E-13" in text
        assert "MP,CSAT,MNX_MAT,3.966903000000E+00" in text
        assert "MP,BETX,MNX_MAT,1.700000000000E-04" in text

    def test_포화_농도의_환경에_확산계수가_없으면_확산계수의_환경으로(
        self, db: Session, tmp_path: Path
    ) -> None:
        """포화 농도만 맞추고 확산계수가 없는 환경을 고르면 덱이 통째로 안 선다."""
        material = self._material(
            db,
            tmp_path,
            [
                ("physical.diffusion_coefficient", 1.0e-13, "A 논문", 1, self.DRY),
                ("physical.moisture_saturation", 220.2, "A 논문", 1, self.WET),
            ],
        )
        deck = litdeck.literature_deck(
            db, material, 7, target=litdeck.find_format(db, "ansys_moisture")
        )
        assert not isinstance(deck, str), deck
        assert deck.blocks["moisture"]["values"] == {
            "moisture_diffusivity": 1.0e-13,
            "temperature": 303.15,
            "humidity": 0.6,
        }
        assert any("포화 농도는 확산계수와 같은 환경에서" in line for line in deck.provenance)

    def test_물이_아닌_확산계수뿐이면_흡습_블록이_없다(
        self, db: Session, tmp_path: Path
    ) -> None:
        material = self._material(
            db,
            tmp_path,
            [("physical.diffusion_coefficient", 2.0e-11, "A 논문", 1, {"species": "O2"})],
        )
        target = litdeck.find_format(db, "ansys_moisture")
        deck = litdeck.literature_deck(db, material, 7, target=target)
        assert not isinstance(deck, str), deck
        assert "moisture" not in deck.blocks
        assert export.missing_for(deck, target)


class Test고무_합성은_벌이_없을_때만:
    """고무의 초탄성 합성(E → Neo-Hookean)은 **문헌 벌이 없을 때만** — 벌이 있으면 그것이
    이긴다."""

    def test_벌이_있으면_합성하지_않는다(self, db: Session, tmp_path: Path) -> None:
        fr4 = Test초탄성_벌()._load(db, tmp_path)
        material = db.get(CatalogMaterial, fr4)
        assert material is not None
        material.category = "rubber"
        db.commit()
        target = litdeck.find_format(db, "abaqus_hyperelastic")
        deck = litdeck.literature_deck(db, material, 1, synthesize=True, target=target)
        assert not isinstance(deck, str), deck
        assert "합성" not in deck.blocks["hyperelastic"]["values"]["label"]
        assert not any(line.startswith("합성 초탄성") for line in deck.provenance)

    def test_고무가_아니면_합성하지_않는다(self, db: Session, tmp_path: Path) -> None:
        sus, _ = load(db, tmp_path)
        material = db.get(CatalogMaterial, sus)
        assert material is not None and material.category != "rubber"
        target = litdeck.find_format(db, "abaqus_hyperelastic")
        deck = litdeck.literature_deck(db, material, 1, synthesize=True, target=target)
        assert not isinstance(deck, str), deck
        assert "hyperelastic" not in deck.blocks
