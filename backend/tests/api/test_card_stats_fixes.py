"""카드 · 통계 결함 수정(2026-11-15) — **조용히 섞이던 것들.**

잰 E 와 적은 E(T)        시험으로 잰 E 가 있으면 재료에 적어 둔 E(T) 표를 탄성 블록에 안 붙인다
시험 온도                23 ℃ 와 80 ℃ 시험이 한 평균 · 대표 곡선 · 카드가 되지 않는다
낡은 채택 결과            옛 치수 · 옛 원본으로 낸 결과는 통계 · 카드에 경고, 채택은 확인
묶음 카드의 E            묶을 때 쓴 결과에서 읽는다(지금 채택이 아니라)
묶음이 쓰는 결과          지우기 · 배치 되돌리기가 막는다
이방성 짝 카드            짝 카드(MD)의 탄성이 덱에 쓰인다
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.fitting.models import PropertyCard
from app.modules.grouping.models import GroupResult
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


def _steps(modulus: float = 200e9, area: float | str = 12.12e-6) -> list[dict[str, Any]]:
    """진응력 · 진소성변형률까지 내는 레시피 — 탄성계수는 직접 넣는다(`test_fitting.STEPS`)."""
    return [
        {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": area}},
        {
            "plugin": "curve.sort_unique",
            "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
        },
        {"plugin": "tensile.strength", "options": {}},
        {
            "plugin": "tensile.elastic_modulus",
            "options": {"method": "manual", "manual_modulus": modulus},
        },
        {"plugin": "tensile.proof_stress", "options": {"youngs_modulus": "@youngs_modulus"}},
        {
            "plugin": "tensile.true_plastic",
            "options": {"youngs_modulus": "@youngs_modulus", "proof_stress": "@proof_stress"},
        },
    ]


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    created = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"FIX-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "poisson_ratio": 0.3,
            "density": 7850,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    return dict(created.json())


def _run(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    material_id: str,
    *,
    celsius: float | None = None,
    orientation: str = "MD",
) -> str:
    """시험 하나를 올린다 — 온도를 주면 시험 조건 `temperature` 로(°C 로 넣어 K 로 담긴다)."""
    sample = client.post(
        f"/api/materials/{material_id}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": orientation},
        headers=headers,
    ).json()
    data = {"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"}
    if celsius is not None:
        data["conditions"] = json.dumps({"temperature": celsius})
        data["condition_units"] = json.dumps({"temperature": "degC"})
    created = client.post(
        "/api/test-runs",
        data=data,
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    assert services.parse_run(db, uuid.UUID(run_id)) == "parsed"
    return run_id


def _process(
    client: TestClient,
    headers: dict[str, str],
    run_id: str,
    steps: list[dict[str, Any]] | None = None,
    *,
    adopt: bool = True,
) -> str:
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": steps or _steps()},
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    result_id = str(stored.json()["id"])
    if adopt:
        took = client.post(
            f"/api/processing/results/{result_id}/adopt",
            params={"confirm_warnings": True},
            headers=headers,
        )
        assert took.status_code == 200, took.text
    return result_id


def _adopted_run(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    material_id: str,
    *,
    celsius: float | None = None,
    orientation: str = "MD",
) -> str:
    run_id = _run(client, headers, db, material_id, celsius=celsius, orientation=orientation)
    _process(client, headers, run_id)
    return run_id


def _groups(client: TestClient, headers: dict[str, str], material_id: str) -> list[Any]:
    body = client.get(f"/api/statistics/materials/{material_id}", headers=headers)
    assert body.status_code == 200, body.text
    return list(body.json()["groups"])


# --- 시험 온도로 묶음을 가른다 ---------------------------------------------------------------


class Test시험_온도_묶음:
    """23 ℃ 5건과 80 ℃ 3건이 한 평균 · 대표 곡선 · 카드가 되던 것(2026-11-15)."""

    def test_온도가_다르면_따로_묶고_서로를_말한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        for celsius in (23.0, 23.0, 80.0, 80.0, 80.0):
            _adopted_run(client, admin_headers, db, material["id"], celsius=celsius)
        groups = _groups(client, admin_headers, material["id"])
        assert [round(one["temperature_k"], 2) for one in groups] == [296.15, 353.15]
        assert [one["sample_count"] for one in groups] == [2, 3]
        assert all(
            any("시험 온도가 다른 시험은 따로 묶었습니다" in note for note in one["notes"])
            for one in groups
        )

    def test_첫_값과_2K_안이면_한_묶음이고_대표는_중앙값이다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        for celsius in (23.0, 24.0, 25.0):
            _adopted_run(client, admin_headers, db, material["id"], celsius=celsius)
        [group] = _groups(client, admin_headers, material["id"])
        assert group["temperature_k"] == pytest.approx(297.15)
        assert group["sample_count"] == 3
        assert not any("따로 묶었습니다" in note for note in group["notes"])

    def test_미기재는_따로_한_묶음이고_상온으로_단정하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        _adopted_run(client, admin_headers, db, material["id"], celsius=23.0)
        _adopted_run(client, admin_headers, db, material["id"], celsius=None)
        groups = _groups(client, admin_headers, material["id"])
        assert [one["temperature_k"] for one in groups][1] is None
        assert groups[0]["temperature_k"] == pytest.approx(296.15)
        # 미기재 묶음은 `null` 로 고른다.
        preview = client.post(
            "/api/fitting/preview",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "temperature_k": None,
                "families": ["swift"],
            },
            headers=admin_headers,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["sample_count"] == 1
        assert preview.json()["temperature_k"] is None

    def test_온도가_하나면_안_보내도_전과_같다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        for _ in range(2):
            _adopted_run(client, admin_headers, db, material["id"], celsius=None)
        [group] = _groups(client, admin_headers, material["id"])
        assert group["temperature_k"] is None
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "옛 화면",
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        assert card.json()["source"]["sample_count"] == 2
        assert card.json()["source"]["temperature_k"] is None

    def test_온도가_둘이면_골라야_하고_고른_온도의_시험만_쓴다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        room = [
            _adopted_run(client, admin_headers, db, material["id"], celsius=23.0)
            for _ in range(2)
        ]
        hot = [
            _adopted_run(client, admin_headers, db, material["id"], celsius=80.0)
            for _ in range(3)
        ]
        asked = {
            "material_id": material["id"],
            "test_type_key": "tensile",
            "orientation": "MD",
        }

        refused = client.post(
            "/api/fitting/preview",
            json={**asked, "families": ["swift"]},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        error = refused.json()["error"]
        assert error["code"] == "MNX-STATISTICS-0007"
        assert "23 °C" in error["message"] and "80 °C" in error["message"]
        refused_card = client.post(
            "/api/fitting/cards", json={**asked, "label": "섞임"}, headers=admin_headers
        )
        assert refused_card.status_code == 422, refused_card.text

        preview = client.post(
            "/api/fitting/preview",
            json={**asked, "families": ["swift"], "temperature_k": 353.15},
            headers=admin_headers,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["sample_count"] == 3

        # ±2 K 로 맞춘다 — 사람이 적은 79.5 ℃ 도 80 ℃ 묶음이다.
        card = client.post(
            "/api/fitting/cards",
            json={**asked, "label": "인장시험 MD · 80 °C", "temperature_k": 352.65},
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        source = card.json()["source"]
        assert source["temperature_k"] == pytest.approx(353.15)
        assert sorted(source["test_run_ids"]) == sorted(hot)
        assert not set(source["test_run_ids"]) & set(room)

        # 없는 온도 · 없는 미기재 묶음은 「그 묶음이 없다」.
        for missing in (400.0, None):
            gone = client.post(
                "/api/fitting/preview",
                json={**asked, "families": ["swift"], "temperature_k": missing},
                headers=admin_headers,
            )
            assert gone.status_code == 404, gone.text

    def test_분포와_반복_시편_통계도_온도로_고른다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        for celsius in (23.0, 23.0, 80.0, 80.0):
            _adopted_run(client, admin_headers, db, material["id"], celsius=celsius)
        url = f"/api/statistics/materials/{material['id']}/distributable"
        base = {"test_type_key": "tensile", "orientation": "MD"}
        assert client.get(url, params=base, headers=admin_headers).status_code == 422
        picked = client.get(
            url, params={**base, "temperature_k": "296.15"}, headers=admin_headers
        )
        assert picked.status_code == 200, picked.text
        assert all(one["count"] == 2 for one in picked.json())
        bad = client.get(url, params={**base, "temperature_k": "상온"}, headers=admin_headers)
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-STATISTICS-0008"
        # 쿼리로는 `null` 을 못 보낸다 — `none` 이 미기재 묶음(여기엔 없다).
        none = client.get(url, params={**base, "temperature_k": "none"}, headers=admin_headers)
        assert none.status_code == 404

        saved = client.post(
            "/api/statistics/ensembles",
            json={"material_id": material["id"], **base, "temperature_k": 353.15},
            headers=admin_headers,
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["temperature_k"] == pytest.approx(353.15)
        assert saved.json()["sample_count"] == 2
        listed = client.get(
            "/api/statistics/ensembles",
            params={"material_id": material["id"]},
            headers=admin_headers,
        ).json()
        assert listed[0]["temperature_k"] == pytest.approx(353.15)


def test_온도_묶음은_첫_값에_묶고_미기재는_따로_맨_뒤다() -> None:
    from app.modules.statistics.services import temperature_bins

    found = temperature_bins([296.0, 353.15, None, 298.0, 298.5, 296.5])
    # 296 · 296.5 · 298 은 첫 값(296)과 2 K 안, 298.5 는 2.5 K 라 새 묶음.
    assert found == [(296.5, [0, 5, 3]), (298.5, [4]), (353.15, [1]), (None, [2])]
    assert temperature_bins([None, None]) == [(None, [0, 1])]
    assert temperature_bins([]) == []


# --- 잰 E 가 있으면 적어 둔 E(T) 표를 안 붙인다 ----------------------------------------------


@pytest.fixture
def axis(db: Session) -> None:
    from app.modules.vocabulary.definitions import (
        ensure_builtin_axis_fields,
        ensure_builtin_property_items,
        ensure_builtin_vocabularies,
    )

    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
    ensure_builtin_property_items(db)
    db.commit()


def _declare_modulus_table(
    client: TestClient, headers: dict[str, str], material_id: str
) -> None:
    saved = client.patch(
        f"/api/materials/{material_id}",
        json={
            "declared_properties": [
                {
                    "item": "탄성계수",
                    "points": [
                        {"value": 206, "temperature_k": 293.15},
                        {"value": 170, "temperature_k": 673.15},
                    ],
                    "input_unit": "GPa",
                    "source": "standard",
                    "reference": "EN 1993-1-2 표 3.1",
                }
            ]
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text


def test_잰_E_가_있으면_적어_둔_온도표를_탄성_블록에_안_붙인다(
    client: TestClient,
    admin_headers: dict[str, str],
    db: Session,
    material: Any,
    axis: None,
) -> None:
    """값 칸은 잰 195 GPa, 표는 적은 206/170 GPa 라 표를 받는 솔버와 안 받는 솔버가 다른 E 로
    돌았다. 잰 E 가 이긴다 — 표도 그 E 와 다르면 안 된다."""
    _declare_modulus_table(client, admin_headers, material["id"])
    for _ in range(2):
        run_id = _run(client, admin_headers, db, material["id"])
        _process(client, admin_headers, run_id, _steps(modulus=195e9))
    card = client.post(
        "/api/fitting/cards",
        json={
            "material_id": material["id"],
            "test_type_key": "tensile",
            "orientation": "MD",
            "label": "잰 E",
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    elastic = card.json()["blocks"]["elastic"]
    assert elastic["values"]["youngs_modulus"] == pytest.approx(195e9)
    assert elastic["values"]["youngs_modulus_source"] == "measured"
    assert not any("youngs_modulus" in row for row in elastic.get("rows") or []), elastic.get(
        "rows"
    )
    assert any(
        "온도별 탄성계수 표는 싣지 않았습니다" in line
        for line in card.json()["source"]["notes"]
    )

    # 잰 E 가 없는 카드(적어 둔 값만)는 지금대로 표를 든다.
    declared = client.post(
        "/api/fitting/cards/declared",
        json={"material_id": material["id"], "label": "적은 값"},
        headers=admin_headers,
    )
    assert declared.status_code == 201, declared.text
    rows = declared.json()["blocks"]["elastic"]["rows"]
    assert [row["youngs_modulus"] for row in rows] == [
        pytest.approx(206e9),
        pytest.approx(170e9),
    ]


# --- 낡은 채택 결과 --------------------------------------------------------------------------


@pytest.fixture
def stale_run(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> dict[str, str]:
    """시편 치수(@specimen_area)로 처리 · 채택한 뒤 **시편 두께를 고친** 시험."""
    run_id = _run(client, admin_headers, db, material["id"])
    run = db.get(TestRun, uuid.UUID(run_id))
    assert run is not None
    # 파일이 잰 치수(a0 · b0)를 비운다 — 안 비우면 시편 값이 아니라 그 값으로 돈다.
    run.dimensions = {}
    db.commit()
    specimen_id = str(run.specimen_id)
    saved = client.patch(
        f"/api/specimens/{specimen_id}",
        json={"thickness": 1.0, "width": 12.5, "length_unit": "mm"},
        headers=admin_headers,
    )
    assert saved.status_code == 200, saved.text
    result_id = _process(client, admin_headers, run_id, _steps(area="@specimen_area"))
    fixed = client.patch(
        f"/api/specimens/{specimen_id}",
        json={"thickness": 1.2, "length_unit": "mm"},
        headers=admin_headers,
    )
    assert fixed.status_code == 200, fixed.text
    return {"run_id": run_id, "result_id": result_id}


def test_옛_치수로_낸_채택_결과는_낡았다고_어디서나_말한다(
    client: TestClient,
    admin_headers: dict[str, str],
    material: Any,
    stale_run: dict[str, str],
) -> None:
    listed = client.get(
        "/api/processing/results",
        params={"test_run_id": stale_run["run_id"]},
        headers=admin_headers,
    ).json()
    [item] = listed
    assert item["stale"] is True
    stale = [one for one in item["warnings"] if one["label"] == "낡은 결과"]
    assert len(stale) == 1 and "시편 초기 단면적" in stale[0]["message"]
    assert "+20.00 %" in stale[0]["message"]

    [group] = _groups(client, admin_headers, material["id"])
    assert any("채택 결과가 낡은 시험 1건" in note for note in group["notes"]), group["notes"]

    preview = client.post(
        "/api/fitting/preview",
        json={
            "material_id": material["id"],
            "test_type_key": "tensile",
            "orientation": "MD",
            "families": ["swift"],
        },
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    assert any(one["label"] == "낡은 결과" for one in preview.json()["warnings"])
    card = client.post(
        "/api/fitting/cards",
        json={
            "material_id": material["id"],
            "test_type_key": "tensile",
            "orientation": "MD",
            "label": "낡은 근거",
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    assert any(one["label"] == "낡은 결과" for one in card.json()["source"]["warnings"])


def test_낡은_결과는_확인해야_채택된다(
    client: TestClient, admin_headers: dict[str, str], stale_run: dict[str, str]
) -> None:
    result_id = stale_run["result_id"]
    gone = client.delete(f"/api/processing/results/{result_id}/adopt", headers=admin_headers)
    assert gone.status_code == 204, gone.text

    refused = client.post(f"/api/processing/results/{result_id}/adopt", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MNX-PROCESSING-0020"
    assert "낡은 결과" in refused.json()["error"]["message"]

    many = client.post(
        "/api/processing/adopt-many",
        json={"items": [{"test_run_id": stale_run["run_id"], "result_id": result_id}]},
        headers=admin_headers,
    ).json()
    assert many["items"][0]["status"] == "failed"

    took = client.post(
        f"/api/processing/results/{result_id}/adopt",
        params={"confirm_warnings": True},
        headers=admin_headers,
    )
    assert took.status_code == 200, took.text


def test_치수가_그대로면_낡지_않았다(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> None:
    run_id = _adopted_run(client, admin_headers, db, material["id"])
    [item] = client.get(
        "/api/processing/results", params={"test_run_id": run_id}, headers=admin_headers
    ).json()
    assert item["stale"] is False
    assert not any(one["label"] == "낡은 결과" for one in item["warnings"])


# --- 묶음 카드: 묶을 때 쓴 결과에서 E 를 읽는다 · 묶음이 쓰는 결과는 못 지운다 ---------


def _temperature_group(
    client: TestClient, headers: dict[str, str], run_ids: list[str], **extra: Any
) -> dict[str, Any]:
    made = client.post(
        "/api/groups",
        json={
            "plugin_id": "tensile.temperature_family",
            "run_ids": run_ids,
            "options": {"levels": "0.01"},
            **extra,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


@pytest.fixture
def grouped(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> dict[str, Any]:
    run_ids = [
        _adopted_run(client, admin_headers, db, material["id"], celsius=celsius)
        for celsius in (20.0, 50.0, 80.0)
    ]
    return {"run_ids": run_ids, "group": _temperature_group(client, admin_headers, run_ids)}


def _group_card(client: TestClient, headers: dict[str, str], group_id: str) -> dict[str, Any]:
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": group_id, "label": "온도 묶음"},
        headers=headers,
    )
    assert card.status_code == 201, card.text
    return dict(card.json())


def test_묶음은_쓴_결과를_늘_남기고_카드는_그_결과의_E_를_쓴다(
    client: TestClient, admin_headers: dict[str, str], db: Session, grouped: dict[str, Any]
) -> None:
    members = grouped["group"]["members"]
    assert all(one.get("result_id") for one in members), members
    assert not any(one.get("unadopted") for one in members)

    # 묶은 뒤 한 시험의 채택을 E 100 GPa 결과로 옮긴다.
    moved = grouped["run_ids"][0]
    _process(client, admin_headers, moved, _steps(modulus=100e9))
    card = _group_card(client, admin_headers, grouped["group"]["id"])
    assert card["blocks"]["elastic"]["values"]["youngs_modulus"] == pytest.approx(200e9)
    warned = [one for one in card["source"]["warnings"] if one["label"] == "묶음 근거"]
    assert len(warned) == 1 and "묶은 뒤 채택이 바뀌었습니다" in warned[0]["message"]

    # 옛 묶음(쓴 결과 기록이 없는 것)은 전처럼 지금 채택을 읽는다.
    row = db.get(GroupResult, uuid.UUID(grouped["group"]["id"]))
    assert row is not None
    row.members = [
        {key: value for key, value in one.items() if key != "result_id"} for one in row.members
    ]
    db.commit()
    old = _group_card(client, admin_headers, grouped["group"]["id"])
    assert old["blocks"]["elastic"]["values"]["youngs_modulus"] == pytest.approx(
        (100e9 + 200e9 + 200e9) / 3
    )
    assert not old["source"]["warnings"]


def test_미채택으로_고른_결과의_E_가_카드에_선다(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> None:
    run_ids = [
        _adopted_run(client, admin_headers, db, material["id"], celsius=celsius)
        for celsius in (20.0, 50.0, 80.0)
    ]
    chosen = {
        run_id: _process(client, admin_headers, run_id, _steps(modulus=150e9), adopt=False)
        for run_id in run_ids
    }
    group = _temperature_group(client, admin_headers, run_ids, results=chosen)
    assert {one["result_id"] for one in group["members"]} == set(chosen.values())
    card = _group_card(client, admin_headers, group["id"])
    # 전에는 채택(200 GPa)을 읽어 묶음 값과 다른 결과의 E 가 섰다.
    assert card["blocks"]["elastic"]["values"]["youngs_modulus"] == pytest.approx(150e9)
    assert not [one for one in card["source"]["warnings"] if one["label"] == "묶음 근거"]


def test_묶음이_쓰는_결과는_지우기도_배치_되돌리기도_막는다(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> None:
    run_ids = [
        _adopted_run(client, admin_headers, db, material["id"], celsius=celsius)
        for celsius in (20.0, 50.0, 80.0)
    ]
    chosen = {
        run_id: _process(client, admin_headers, run_id, adopt=False) for run_id in run_ids
    }
    _temperature_group(client, admin_headers, run_ids, results=chosen)
    target = chosen[run_ids[0]]
    refused = client.delete(f"/api/processing/results/{target}", headers=admin_headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MNX-PROCESSING-0024"
    undone = client.post(
        "/api/processing/batch/undo",
        json={"items": [{"result_id": target}]},
        headers=admin_headers,
    ).json()
    assert undone["items"][0]["status"] == "failed"
    assert "묶음" in undone["items"][0]["error"]

    # 묶음이 안 쓰는 결과는 지금처럼 지운다.
    spare = _process(client, admin_headers, run_ids[1], adopt=False)
    assert (
        client.delete(f"/api/processing/results/{spare}", headers=admin_headers).status_code
        == 204
    )


# --- 이방성 짝 카드: 탄성은 짝 카드에서 ------------------------------------------------------

CURVE = [(0.0, 350e6), (0.02, 455e6), (0.1, 560e6), (0.4, 700e6), (1.0, 790e6)]


def test_이방성_카드는_짝_카드의_탄성으로_덱을_낸다(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> None:
    """옛 이방성 카드(묶음이 세 방향 평균 E 를 물려준 것)도 짝과 낼 때는 짝의 E 를 쓴다."""
    aniso = PropertyCard(
        material_id=uuid.UUID(material["id"]),
        label="이방성 r",
        status="draft",
        blocks={
            "anisotropy": {"values": {"r_0": 1.8, "r_45": 1.4, "r_90": 2.1}},
            # 세 방향 시험의 평균 E — 어느 방향의 물성도 아니다.
            "elastic": {
                "values": {"youngs_modulus": 150e9, "poisson_ratio": 0.25, "density": 7000.0}
            },
        },
    )
    md = PropertyCard(
        material_id=uuid.UUID(material["id"]),
        label="인장 MD",
        status="draft",
        orientation="MD",
        blocks={
            "elastic": {
                "values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}
            },
            "table": {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE]},
        },
    )
    db.add_all([aniso, md])
    db.commit()
    paired = client.get(
        f"/api/fitting/cards/{aniso.id}/export",
        params={"format": "abaqus_hill", "units": "si", "with_card": str(md.id)},
        headers=admin_headers,
    )
    assert paired.status_code == 200, paired.text
    # *ELASTIC 은 짝 카드(MD)의 E · ν, *DENSITY 도 짝의 것이다.
    lines = paired.text.splitlines()
    elastic_at = lines.index("*ELASTIC, TYPE=ISOTROPIC")
    assert lines[elastic_at + 1] == "2.100000000000E+11, 3.000000000000E-01"
    assert "7.850000000000E+03" in paired.text
    assert "1.500000000000E+11" not in paired.text
    assert "짝 카드의 탄성을 씁니다" in paired.text


def test_새_이방성_묶음_카드는_세_방향_평균_탄성을_싣지_않는다(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
) -> None:
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    made = client.post(
        "/api/test-runs/import",
        json={
            "sample_id": sample["id"],
            "test_type": "tensile",
            "values": ["시편\t방향\tr_value", "1\tMD\t1.8", "2\tDD\t1.4", "3\tTD\t2.1"],
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert made.status_code == 200, made.text
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]
    group = client.post(
        "/api/groups",
        json={"plugin_id": "anisotropy.r_family", "run_ids": [run["id"] for run in runs]},
        headers=admin_headers,
    )
    assert group.status_code == 201, group.text
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": group.json()["id"], "label": "이방성", "density": 7800.0},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    assert "elastic" not in card.json()["blocks"]
    assert any("짝 카드" in line for line in card.json()["source"]["notes"])
    assert any(
        "넣은 푸아송비 · 밀도도 싣지 않았습니다" in line
        for line in card.json()["source"]["notes"]
    )


def test_운영_점검_보고서도_같은_판정을_쓴다(db: Session, stale_run: dict[str, str]) -> None:
    """`scripts/ops_report.py` 1절이 공용 판정(`shared/result_staleness`)을 쓴다 — 출력 꼴은
    전과 같다(`specimen_area 1.25e-05 → 1.5e-05(+20.00 %)`)."""
    import importlib.util
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "ops_report_for_test", scripts / "ops_report.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    head, lines = module.reprocess_candidates(db)
    assert "1건" in head
    assert any("specimen_area 1.25e-05 → 1.5e-05(+20.00 %)" in line for line in lines), lines
