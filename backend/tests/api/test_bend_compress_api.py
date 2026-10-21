"""굽힘 · 압축 — **장비 파일을 올려 등가 E 카드까지**(2026-10-16).

규격      카탈로그의 굽힘 · 압축 규격이 다 가져와지고(분류 · 칸 · 비율 조건이 맞물린다),
          그 공칭(ISO 178 스팬 64 mm · ISO 7743 직경 29 mm)이 처리의 `@specimen_*` 로 간다
감지      `.tra` 를 인장 · 굽힘 · 압축이 함께 읽는다 — 파일 안의 이름이나 커넥터 귀띔으로만
          고르고, 못 고르면 고르지 않는다. 옛 인장 파일(`Example.tra`)은 그대로 인장이다
사슬      Zwick 굽힘 `.tra` → 굽힘 응력 · 등가 E → 시편 둘을 묶어 카드(탄성 블록의 E)
          Instron 압축 CSV(이름 안 단위 kN) → 압축 응력 · 할선 탄성률 · 25% 응력
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.tests.models import TestType
from app.modules.vocabulary import standards
from app.modules.vocabulary.definitions import (
    ensure_builtin_axis_fields,
    ensure_builtin_specimen_categories,
    ensure_builtin_vocabularies,
)
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared import ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

E_FLEX = 3.0e9
E_RUBBER = 5.0e6


@pytest.fixture
def seeded(db: Session) -> None:
    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
    ensure_builtin_specimen_categories(db)
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()


def _zwick_flexural(
    modulus: float = E_FLEX,
    *,
    span: float = 0.064,
    width: float = 0.010,
    thickness: float = 0.004,
    load_span: float = 0.0,
    top: float = 200.0,
) -> bytes:
    """기본은 ISO 178 공칭(80 x 10 x 4, 스팬 64 mm)의 3점 굽힘. 하중 스팬을 주면 4점의 가운데
    처짐 δ = F·a·(3L² - 4a²) / (48·E·I), a = (L - Lᵢ)/2 — 3점(a = L/2)이면 F·L³ / (48·E·I)."""
    inertia = width * thickness**3 / 12
    arm = (span - load_span) / 2
    force = np.linspace(0, top, 120)
    deflection_mm = force * arm * (3 * span**2 - 4 * arm**2) / (48 * modulus * inertia) * 1e3
    rows = "\n".join(
        f"{f:.6g},{d * 1.02:.6g},{d:.6g}" for f, d in zip(force, deflection_mm, strict=True)
    )
    head = (
        '"Flexural strength",120.5,"MPa"\n'
        '"Standard force","Standard travel","Deflection"\n'
        '"N","mm","mm"\n'
    )
    return (head + rows + "\n").encode()


def _instron_compression() -> bytes:
    """ISO 7743 시험편 A(직경 29 · 높이 12.5 mm)를 30% 까지 — 하중은 kN 으로 이름 안에."""
    area = np.pi * 0.029**2 / 4
    strain = np.linspace(0, 0.3, 151)
    rows = "\n".join(
        f"{i * 0.1:.3f},{s * 12.5:.6g},{E_RUBBER * s * area / 1e3:.6g}"
        for i, s in enumerate(strain)
    )
    return (
        "Time (s),Compressive extension (mm),Compressive load (kN)\n" + rows + "\n"
    ).encode()


def _import(client: TestClient, headers: dict[str, str], *keys: str) -> list[dict[str, Any]]:
    made = client.post(
        "/api/vocabularies/specimen-standards/import",
        json={"items": [{"key": key} for key in keys]},
        headers=headers,
    )
    assert made.status_code == 200, made.text
    return list(made.json())


def _runs(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    *,
    standard: str,
    test_type: str,
    filename: str,
    data: bytes,
    count: int,
) -> list[str]:
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "Module", "grade": "CHIP-1"},
        headers=headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    run_ids: list[str] = []
    for _ in range(count):
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "NA", "standard": standard},
            headers=headers,
        )
        assert specimen.status_code == 201, specimen.text
        created = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen.json()["id"],
                "test_type": test_type,
                "conditions": "{}",
            },
            files={"file": (filename, data)},
            headers=headers,
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
        run_ids.append(run_id)
    return run_ids


def _process(
    client: TestClient, headers: dict[str, str], run_id: str, steps: list[dict[str, Any]]
) -> dict[str, float]:
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": steps},
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
    )
    assert adopted.status_code == 200, adopted.text
    return {one["key"]: one["value"] for one in stored.json()["scalars"]}


class TestStandards:
    def test_카탈로그의_굽힘_압축_규격을_다_가져온다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """분류가 없거나, 비율 조건이 없는 칸을 가리키면 가져오기가 422 로 멈춘다."""
        keys = [
            str(one["key"])
            for one in standards.CATALOG
            if one["category"] in (standards.FLEXURAL, standards.COMPRESSION)
        ]
        assert len(keys) >= 18
        made = _import(client, admin_headers, *keys)
        assert len(made) == len(keys)
        by_value = {term["value"]: term for term in made}
        iso_178 = by_value["ISO 178 (플라스틱 3점 굽힘)"]
        assert iso_178["parent_value"] == "굽힘"
        assert iso_178["cross_section"] == "rectangle"
        assert iso_178["attributes"]["span"] == pytest.approx(0.064)
        rubber = by_value["ISO 7743 시험편 A (고무 압축)"]
        assert rubber["cross_section"] == "circle"
        assert rubber["attributes"] == {"diameter": 0.029, "height": 0.0125}


class TestProcessingDefaults:
    """**규격이 처리 방법을 든다**(2026-10-16) — 처리 화면이 시편의 규격을 보고 채운다."""

    def test_규격을_가져오면_처리_방법도_온다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        made = _import(client, admin_headers, "astm_d790", "iso_178", "iso_7743_a")
        by_value = {term["value"]: term["processing_defaults"] for term in made}
        assert by_value["ASTM D790 (플라스틱 3점 굽힘)"] == {
            "flexural.engineering": {"load_span": None},
            "flexural.modulus": {"method": "tangent"},
        }
        assert by_value["ISO 178 (플라스틱 3점 굽힘)"]["flexural.modulus"] == {
            "method": "chord",
            "minimum_strain": 0.0005,
            "maximum_strain": 0.0025,
        }
        rubber = by_value["ISO 7743 시험편 A (고무 압축)"]
        assert rubber["compression.engineering"] == {"cycle": 4}

    @pytest.mark.parametrize(
        ("body", "said"),
        [
            ({"flexural.guess": {"method": "chord"}}, "등록되지 않은"),
            ({"flexural.modulus": {"speed": 1}}, "옵션이 없습니다"),
            ({"flexural.modulus": {"method": "guess"}}, "중 하나"),
            ({"flexural.modulus": {"maximum_strain": "많이"}}, "수여야"),
            ({"flexural.engineering": {"large_deflection": "yes"}}, "참/거짓"),
        ],
    )
    def test_없는_단계_옵션_값은_저장하지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        seeded: None,
        body: dict[str, Any],
        said: str,
    ) -> None:
        """없는 것을 적으면 처리 화면이 그 값을 둘 자리가 없어 **조용히 버린다** — 저장
        자리에서 거절한다."""
        (term,) = _import(client, admin_headers, "inhouse_flexural_3pt")
        refused = client.patch(
            f"/api/vocabularies/specimen_standard/terms/{term['id']}",
            json={"processing_defaults": body},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-VOCABULARY-0031"
        assert said in refused.json()["error"]["message"]

    def test_고치면_통째로_바뀐다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        (term,) = _import(client, admin_headers, "inhouse_flexural_3pt")
        url = f"/api/vocabularies/specimen_standard/terms/{term['id']}"
        changed = client.patch(
            url,
            json={"processing_defaults": {"flexural.modulus": {"method": "regression"}}},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["processing_defaults"] == {
            "flexural.modulus": {"method": "regression"}
        }
        cleared = client.patch(url, json={"processing_defaults": {}}, headers=admin_headers)
        assert cleared.json()["processing_defaults"] == {}

    def test_규격이_아닌_값에는_못_둔다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], seeded: None
    ) -> None:
        category = db.scalar(
            select(VocabularyTerm)
            .join(Vocabulary, Vocabulary.id == VocabularyTerm.vocabulary_id)
            .where(Vocabulary.slug == "specimen_category", VocabularyTerm.value == "굽힘")
        )
        assert category is not None
        refused = client.patch(
            f"/api/vocabularies/specimen_category/terms/{category.id}",
            json={"processing_defaults": {"flexural.modulus": {"method": "chord"}}},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text

    def test_4점_규격은_기본값만으로_4점으로_돈다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """C1161 형상 B(4 x 3, 스팬 40 · 하중 스팬 20). 화면이 하는 대로 — 기본 순서에 규격의
        처리 기본값을 덮어 — 돌리면 4점 식으로 E 가 돌아온다."""
        _import(client, admin_headers, "astm_c1161_b")
        modulus = 300e9
        (run_id,) = _runs(
            client,
            db,
            admin_headers,
            standard="ASTM C1161 형상 B (세라믹 굽힘 강도)",
            test_type="flexural",
            filename="ceramic.tra",
            data=_zwick_flexural(
                modulus, span=0.040, width=0.004, thickness=0.003, load_span=0.020, top=50.0
            ),
            count=1,
        )
        got = client.get(
            "/api/processing/defaults", params={"test_run_id": run_id}, headers=admin_headers
        )
        assert got.status_code == 200, got.text
        defaults = got.json()
        assert defaults["standard"] == "ASTM C1161 형상 B (세라믹 굽힘 강도)"
        assert defaults["steps"]["flexural.engineering"] == {
            "load_span": "@specimen_load_span"
        }

        starter = {
            "flexural.engineering": {
                "support_span": "@specimen_span",
                "width": "@specimen_width",
                "thickness": "@specimen_thickness",
                "load_span": "@?specimen_load_span",
            },
            "flexural.modulus": {"method": "chord"},
        }
        steps = [
            {"plugin": plugin, "options": {**options, **defaults["steps"].get(plugin, {})}}
            for plugin, options in starter.items()
        ]
        values = _process(client, admin_headers, run_id, steps)
        assert values["flexural_modulus"] == pytest.approx(modulus, rel=1e-3)
        assert values["span_to_depth_ratio"] == pytest.approx(0.040 / 0.003)

    def test_규격이_없으면_비어_있다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        material = client.post(
            "/api/materials",
            json={"family": "Polymer", "category": "Module", "grade": "CHIP-2"},
            headers=admin_headers,
        ).json()
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "NA"},
            headers=admin_headers,
        ).json()
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "flexural", "conditions": "{}"},
            files={"file": ("bend.tra", _zwick_flexural())},
            headers=admin_headers,
        )
        assert created.status_code == 202, created.text
        got = client.get(
            "/api/processing/defaults",
            params={"test_run_id": created.json()["id"]},
            headers=admin_headers,
        ).json()
        assert got == {"standard": None, "steps": {}}


class TestDetect:
    def test_옛_인장_파일은_그대로_인장(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        body = client.post(
            "/api/test-types/detect",
            files={"file": ("Example.tra", (FIXTURES / "Example.tra").read_bytes())},
            headers=admin_headers,
        ).json()
        assert body["test_type_key"] == "tensile"
        assert "work hardening" in body["reason"]

    def test_굽힘_tra_는_굽힘(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        body = client.post(
            "/api/test-types/detect",
            files={"file": ("bend.tra", _zwick_flexural())},
            headers=admin_headers,
        ).json()
        assert body["test_type_key"] == "flexural"

    def test_이름으로_못_가르면_고르지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        plain = b'"Standard force","Standard travel"\n"N","mm"\n0,0\n1,0.1\n2,0.2\n'
        body = client.post(
            "/api/test-types/detect",
            files={"file": ("plain.tra", plain)},
            headers=admin_headers,
        ).json()
        assert body["test_type_key"] is None
        # 인장 · 굽힘 · 압축 · 박리 · 이탈력(2026-10-20) — 넷 다 하중 · 변위 .tra 를 읽는다.
        assert "4개" in body["reason"]

    def test_커넥터가_귀띔하면_그_종류(self, db: Session, seeded: None) -> None:
        plain = b'"Standard force","Standard travel"\n"N","mm"\n0,0\n1,0.1\n2,0.2\n'
        matched = list(
            db.scalars(
                select(TestType)
                .where(TestType.key.in_(["tensile", "flexural", "compression"]))
                .order_by(TestType.sort_order)
            )
        )
        assert ingest.settle(matched, plain) is None
        settled = ingest.settle(matched, plain, "compression")
        assert settled is not None and settled[0].key == "compression"

    def test_Instron_굽힘_압축은_프로파일_지문(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        body = client.post(
            "/api/test-types/detect",
            files={"file": ("raw.csv", _instron_compression())},
            headers=admin_headers,
        ).json()
        assert body["test_type_key"] == "compression"
        assert body["profile_key"] == "instron_bluehill_compression"


class TestSteps:
    def test_인장_목록에는_굽힘_압축_단계가_안_뜬다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """하중 · 변위는 인장도 같다 — 채널로 거르면 인장 시험의 단계 목록에 굽힘 · 압축이
        뜬다(`SAME_SHAPE_AS_TENSILE`)."""

        def ids(test_type: str) -> set[str]:
            got = client.get(
                "/api/processing/steps", params={"test_type": test_type}, headers=admin_headers
            )
            assert got.status_code == 200, got.text
            return {one["id"] for one in got.json()}

        tensile = ids("tensile")
        assert not {one for one in tensile if one.startswith(("flexural.", "compression."))}
        assert {"flexural.engineering", "flexural.modulus", "flexural.strength"} <= ids(
            "flexural"
        )
        assert "compression.indices" in ids("compression")
        assert "flexural.engineering" not in ids("compression")
        # 토우 보정은 인장의 계산을 굽힘 · 압축 열로(2026-10-20) — 각자 제 목록에만.
        assert "compression.toe_compensation" in ids("compression")
        assert "flexural.toe_compensation" in ids("flexural")
        assert "compression.toe_compensation" not in ids("flexural")


class TestChain:
    def test_Zwick_굽힘에서_등가_E_카드까지(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], seeded: None
    ) -> None:
        _import(client, admin_headers, "iso_178")
        run_ids = _runs(
            client,
            db,
            admin_headers,
            standard="ISO 178 (플라스틱 3점 굽힘)",
            test_type="flexural",
            filename="bend.tra",
            data=_zwick_flexural(),
            count=2,
        )
        steps = [
            # 화면이 까는 것과 같다 — 서버는 `@` 기본값을 채우지 않는다.
            {
                "plugin": "flexural.engineering",
                "options": {
                    "support_span": "@specimen_span",
                    "width": "@specimen_width",
                    "thickness": "@specimen_thickness",
                },
            },
            {"plugin": "flexural.modulus", "options": {}},
            {"plugin": "flexural.strength", "options": {}},
        ]
        for run_id in run_ids:
            values = _process(client, admin_headers, run_id, steps)
            # 처짐계(Deflection)가 크로스헤드(Standard travel)보다 먼저다.
            assert values["flexural_modulus"] == pytest.approx(E_FLEX, rel=1e-3)
            assert values["span_to_depth_ratio"] == pytest.approx(16.0)
            assert values["flexural_strength"] == pytest.approx(
                3 * 200 * 0.064 / (2 * 0.010 * 0.004**2), rel=1e-6
            )

        group = client.post(
            "/api/groups",
            json={"plugin_id": "flexural.equivalent", "run_ids": run_ids},
            headers=admin_headers,
        )
        assert group.status_code == 201, group.text
        assert group.json()["values"]["flexural_modulus"] == pytest.approx(E_FLEX, rel=1e-3)
        card = client.post(
            "/api/fitting/cards/from-group",
            json={
                "group_result_id": group.json()["id"],
                "label": "칩 등가 E",
                "poisson_ratio": 0.3,
                "density": 2300.0,
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        blocks = card.json()["blocks"]
        assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(E_FLEX, rel=1e-3)
        assert blocks["reference"]["values"]["flexural_modulus"] == pytest.approx(
            E_FLEX, rel=1e-3
        )
        # **구조 강성 블록**(2026-10-20) — 3점이면 k = 48·E·I / L³, 그 배치와 함께.
        inertia = 0.010 * 0.004**3 / 12
        stiffness = blocks["structural_stiffness"]["values"]
        assert stiffness["stiffness"] == pytest.approx(
            48 * E_FLEX * inertia / 0.064**3, rel=1e-3
        )
        assert stiffness["support_span"] == pytest.approx(0.064)
        assert stiffness["loading"] == "3점 굽힘"

    def test_Instron_압축에서_할선_탄성률과_25퍼센트_응력(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], seeded: None
    ) -> None:
        _import(client, admin_headers, "iso_7743_a")
        (run_id,) = _runs(
            client,
            db,
            admin_headers,
            standard="ISO 7743 시험편 A (고무 압축)",
            test_type="compression",
            filename="raw.csv",
            data=_instron_compression(),
            count=1,
        )
        values = _process(
            client,
            admin_headers,
            run_id,
            [
                {
                    "plugin": "compression.engineering",
                    "options": {"height": "@specimen_height", "area": "@specimen_area"},
                },
                {
                    "plugin": "compression.modulus",
                    "options": {"method": "secant", "maximum_strain": 0.1},
                },
                {"plugin": "compression.indices", "options": {}},
            ],
        )
        assert values["compressive_modulus"] == pytest.approx(E_RUBBER, rel=1e-3)
        assert values["compressive_stress_at_25pct"] == pytest.approx(
            E_RUBBER * 0.25, rel=1e-3
        )
        assert "compressive_stress_at_40pct" not in values

    def test_압축에서_초탄성_카드까지_모드가_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """사용자 보고(2026-10-20): 압축 시험을 초탄성 카드로 내보낼 경로가 없었다."""
        _import(client, admin_headers, "iso_7743_a")
        (run_id,) = _runs(
            client,
            db,
            admin_headers,
            standard="ISO 7743 시험편 A (고무 압축)",
            test_type="compression",
            filename="raw.csv",
            data=_instron_compression(),
            count=1,
        )
        _process(
            client,
            admin_headers,
            run_id,
            [
                {
                    "plugin": "compression.engineering",
                    "options": {"height": "@specimen_height", "area": "@specimen_area"},
                }
            ],
        )
        run = client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()
        made = client.post(
            "/api/fitting/cards",
            json={
                "material_id": run["material_id"],
                "test_type_key": "compression",
                "orientation": "NA",
                "label": "고무 압축 초탄성",
                "family": "neo_hookean_compression",
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        block = made.json()["blocks"]["hyperelastic"]["values"]
        assert block["mode"] == "단축 압축"
        assert block["model"] == "neo_hookean"
        # 이 곡선은 직선(E)이다 — Neo-Hookean 은 압축에서 굳어지므로 30% 까지 맞추면 μ 가 E/3
        # 보다 조금 작게 나온다. 자릿수가 맞는지만 본다.
        assert E_RUBBER / 5 < block["shear_modulus"] < E_RUBBER / 2
        deck = client.get(
            f"/api/fitting/cards/{made.json()['id']}/export",
            params={"format": "json"},
            headers=admin_headers,
        )
        assert deck.status_code == 200, deck.text
        joined = " ".join(deck.json()["provenance"])
        assert "단축 압축 하나로 맞춘 계수" in joined
        assert "단축 인장 하나로" not in joined
        # **고를 수 있다고 한 형식은 다 나와야 한다**(2026-10-20 검토) — Abaqus 만 식 이름 대신
        # `family`(neo_hookean_compression)를 읽어 「매핑이 없는 식」 으로 막혔다. JSON 만 보던
        # 이 시험은 그것을 못 봤다.
        formats = made.json()["available_formats"]
        assert "abaqus_hyperelastic" in formats
        for key in formats:
            got = client.get(
                f"/api/fitting/cards/{made.json()['id']}/export",
                params={"format": key},
                headers=admin_headers,
            )
            assert got.status_code == 200, (key, got.text)

    def test_압축에서_폼_카드와_LS_DYNA_까지(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """사용자 보고(2026-10-20): 폼 소재를 해석 카드로 내보낼 경로가 없었다."""
        _import(client, admin_headers, "iso_7743_a")
        run_ids = _runs(
            client,
            db,
            admin_headers,
            standard="ISO 7743 시험편 A (고무 압축)",
            test_type="compression",
            filename="raw.csv",
            data=_instron_compression(),
            count=2,
        )
        for run_id in run_ids:
            _process(
                client,
                admin_headers,
                run_id,
                [
                    {
                        "plugin": "compression.engineering",
                        "options": {"height": "@specimen_height", "area": "@specimen_area"},
                    }
                ],
            )
        group = client.post(
            "/api/groups",
            json={"plugin_id": "compression.foam", "run_ids": run_ids},
            headers=admin_headers,
        )
        assert group.status_code == 201, group.text
        assert group.json()["values"]["strain_max"] == pytest.approx(0.3, rel=1e-3)
        card = client.post(
            "/api/fitting/cards/from-group",
            json={"group_result_id": group.json()["id"], "label": "PU 폼", "density": 45.0},
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        blocks = card.json()["blocks"]
        rows = blocks["foam_curve"]["rows"]
        assert rows[0] == {"strain": 0.0, "stress": 0.0}
        assert rows[-1]["stress"] == pytest.approx(E_RUBBER * 0.3, rel=1e-3)
        # 직선 곡선이라 처음 기울기가 곧 E 다 — 묶음이 낸 E 가 이긴다.
        assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(
            E_RUBBER, rel=1e-3
        )
        assert blocks["elastic"]["values"]["density"] == pytest.approx(45.0)
        deck = client.get(
            f"/api/fitting/cards/{card.json()['id']}/export",
            params={"format": "dyna_foam"},
            headers=admin_headers,
        )
        assert deck.status_code == 200, deck.text
        assert "*MAT_LOW_DENSITY_FOAM" in deck.text
