"""크리프 · 응력완화 — **표준 CSV 를 올려 곡선에서 카드 · 덱까지**(2026-10-12).

새 기본 시험 종류 둘은 장비 실파일이 아직 없어서, 기본 형식 프로파일이 「MatNexus 표준 CSV」 를
읽는다(첫 줄 열 이름, 둘째 줄 단위). 여기서 지키는 것:

    단위       시간 h · 변형률 % 로 적은 파일이 SI(s · 1)로 들어와 최소 크리프 속도가 맞는가
    사슬       응력완화 곡선 → E(t) → 시간 영역 Prony → 점탄성 카드(E = 순간 탄성률, ν · 밀도는
               물려받음) → 점탄성 덱
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.tests.models import TestRun

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _upload(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    test_type: str,
    fixture: str,
    conditions: str,
    count: int = 1,
) -> tuple[str, list[str]]:
    """같은 재료의 시편 `count` 개에 같은 파일을 올린다 — 묶음은 시험 2건 이상이다."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "Adhesive", "grade": "EPOXY-1"},
        headers=headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    run_ids: list[str] = []
    for _ in range(count):
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "NA"},
            headers=headers,
        ).json()
        created = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": test_type,
                "conditions": conditions,
            },
            files={"file": (fixture, (FIXTURES / fixture).read_bytes())},
            headers=headers,
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
        run_ids.append(run_id)
    return material["id"], run_ids


def _adopt(
    client: TestClient, headers: dict[str, str], run_id: str, plugin: str
) -> dict[str, Any]:
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": [{"plugin": plugin, "options": {}}]},
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
    )
    assert adopted.status_code == 200, adopted.text
    body: dict[str, Any] = stored.json()
    return body


def test_표준_CSV_의_시간_h_변형률_퍼센트가_SI_로_들어와_최소_속도가_맞다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    detected = client.post(
        "/api/test-types/detect",
        files={"file": ("creep.csv", (FIXTURES / "creep_standard.csv").read_bytes())},
        headers=admin_headers,
    )
    assert detected.status_code == 200, detected.text
    assert detected.json()["profile_key"] == "mnx_creep_csv"
    _, (run_id,) = _upload(
        client,
        db,
        admin_headers,
        "creep",
        "creep_standard.csv",
        '{"applied_stress": 20000000, "temperature": 398.15}',
    )
    result = _adopt(client, admin_headers, run_id, "creep.rate")
    rate = next(one["value"] for one in result["scalars"] if one["key"] == "min_creep_rate")
    # 0.005 %/h = 5e-5 / 3600 s.
    assert rate == pytest.approx(5e-5 / 3600, rel=0.03)


def test_응력완화_곡선이_Prony_점탄성_카드와_덱이_된다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    material_id, run_ids = _upload(
        client,
        db,
        admin_headers,
        "stress_relaxation",
        "relaxation_standard.csv",
        '{"held_strain": 0.005, "temperature": 296.15}',
        count=2,
    )
    for run_id in run_ids:
        _adopt(client, admin_headers, run_id, "relaxation.modulus")
    group = client.post(
        "/api/groups",
        json={"plugin_id": "relaxation.prony", "run_ids": run_ids},
        headers=admin_headers,
    )
    assert group.status_code == 201, group.text
    values = group.json()["values"]
    assert values["equilibrium_pa"] == pytest.approx(1e9, rel=0.03)
    assert values["instantaneous_pa"] == pytest.approx(4e9, rel=0.03)

    card = client.post(
        "/api/fitting/cards/from-group",
        json={
            "group_result_id": group.json()["id"],
            "label": "완화 Prony",
            "poisson_ratio": 0.4,
            "density": 1150.0,
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    blocks = card.json()["blocks"]
    assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(
        values["instantaneous_pa"]
    )
    assert blocks["elastic"]["values"]["poisson_ratio"] == 0.4
    assert blocks["elastic"]["values"]["youngs_modulus_source"] == "group:relaxation.prony"
    assert blocks["viscoelastic"]["rows"]
    deck = client.get(
        f"/api/fitting/cards/{card.json()['id']}/export?format=abaqus_viscoelastic&units=si",
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert "*VISCOELASTIC" in deck.text
    assert material_id
    # **잰 시간 범위 · 맞춘 온도를 덱에**(2026-11-14, VOC 52) — 응력완화는 마스터커브가 아니다.
    assert "점탄성: 시간 0.1 ~ 1e+04 s 에서 잰 값" in deck.text
    assert "the temperature the Prony was fitted at" in deck.text
    assert "master curve" not in deck.text


def test_시험_온도가_비면_온도_채널의_중앙값으로_채우고_점검에_남긴다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """VOC 52(2026-11-14) — 조건이 비면 카드에 기준 온도가 안 서서 덱이 몇 도의 값인지
    못 말했다."""
    _, (run_id,) = _upload(
        client,
        db,
        admin_headers,
        "stress_relaxation",
        "relaxation_standard.csv",
        '{"held_strain": 0.005}',
    )
    run = db.get(TestRun, uuid.UUID(run_id))
    assert run is not None
    assert run.conditions["temperature"] == pytest.approx(296.15)
    found = [one for one in run.checks if one["code"] == "condition_from_channel"]
    assert len(found) == 1 and "23.0 °C" in found[0]["message"]


def _master_curve_for(db: Session, run_id: str, *, scale: float = 1.0) -> None:
    """그 시험(DMA)에 **응력완화 고정물과 같은 재료**의 대표 마스터커브를 둔다 — 고정물의
    E(t) = 1 + 2·e^(-t/10) + 1·e^(-t/1000) GPa 를 주파수 영역으로 옮긴 것(기준 23 °C, WLF)."""
    from app.modules.viscoelastic.models import MasterCurve
    from app.shared import filestore
    from matcore import curves as curvekit
    from matcore.parsers import Channel

    frequency = np.geomspace(1e-3, 1e3, 120)
    omega = 2 * np.pi * frequency
    storage = np.full_like(omega, 1e9)
    loss = np.zeros_like(omega)
    for modulus, tau in ((2e9, 10.0), (1e9, 1000.0)):
        wt = omega * tau
        storage += modulus * wt**2 / (1 + wt**2)
        loss += modulus * wt / (1 + wt**2)
    channels = [
        Channel(key="frequency", label="주파수", si_unit="Hz", values=tuple(frequency)),
        Channel(
            key="storage_modulus",
            label="저장 탄성률",
            si_unit="Pa",
            values=tuple(storage * scale),
        ),
        Channel(
            key="loss_modulus", label="손실 탄성률", si_unit="Pa", values=tuple(loss * scale)
        ),
    ]
    stored = filestore.write_bytes(
        curvekit.to_parquet(channels),
        relative_dir=f"master-curves/{run_id}",
        filename=f"{uuid.uuid4().hex}.parquet",
    )
    db.add(
        MasterCurve(
            test_run_id=uuid.UUID(run_id),
            source_curve_keys=[],
            reference_temperature_k=296.15,
            method="wlf",
            parameters={"c1": 8.86, "c2": 101.6},
            shifts=[
                {"temperature_k": t, "log10_a_t": -8.86 * (t - 296.15) / (101.6 + t - 296.15)}
                for t in (276.15, 296.15, 316.15)
            ],
            notes=[],
            storage_path=stored.relative_path,
            point_count=len(frequency),
            minimum_frequency_hz=float(frequency[0]),
            maximum_frequency_hz=float(frequency[-1]),
            is_primary=True,
        )
    )
    db.commit()


def _coupled_runs(
    client: TestClient, db: Session, headers: dict[str, str], *, scale: float = 1.0
) -> list[str]:
    """같은 재료에 응력완화 시험 하나(채택) + DMA 시험 하나(대표 마스터커브)."""
    material_id, (relaxation,) = _upload(
        client,
        db,
        headers,
        "stress_relaxation",
        "relaxation_standard.csv",
        '{"held_strain": 0.005, "temperature": 296.15}',
    )
    _adopt(client, headers, relaxation, "relaxation.modulus")
    sample = client.post(f"/api/materials/{material_id}/samples", json={}, headers=headers)
    specimen = client.post(
        f"/api/samples/{sample.json()['id']}/specimens",
        json={"orientation": "NA"},
        headers=headers,
    ).json()
    dma = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": ("dma.csv", (FIXTURES / "dma_freq_temp.csv").read_bytes())},
        headers=headers,
    )
    assert dma.status_code == 202, dma.text
    _master_curve_for(db, dma.json()["id"], scale=scale)
    return [relaxation, dma.json()["id"]]


def test_응력완화와_DMA_마스터커브를_이어_카드를_만든다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """2026-11-15(VOC 52 · ADR 0087 1단계) — 묶음이 두 종류의 시험을 종류마다의 규칙으로
    모으고,
    카드는 응력완화 시험의 것으로 선다(`card_test_type`)."""
    kinds = client.get(
        "/api/groups/kinds", params={"applies_to": "stress_relaxation"}, headers=admin_headers
    )
    assert kinds.status_code == 200, kinds.text
    coupled = next(one for one in kinds.json() if one["id"] == "relaxation.dma_coupled")
    assert coupled["needs_by_type"] == {
        "stress_relaxation": "adopted_result",
        "dma_sweep": "master_curve",
    }

    run_ids = _coupled_runs(client, db, admin_headers)
    group = client.post(
        "/api/groups",
        json={"plugin_id": "relaxation.dma_coupled", "run_ids": run_ids},
        headers=admin_headers,
    )
    assert group.status_code == 201, group.text
    values = group.json()["values"]
    assert values["overlap_ratio"] == pytest.approx(1.0, abs=0.03)
    assert values["instantaneous_pa"] == pytest.approx(4e9, rel=0.05)
    assert values["time_min"] < 0.1  # 응력완화의 첫 측정(0.1 s)보다 짧은 시간까지
    # 이 재료의 선형 한계가 없다 — 막지 않고 말한다.
    assert any("선형 구간 근거가 없습니다" in one for one in group.json()["warnings"])

    card = client.post(
        "/api/fitting/cards/from-group",
        json={
            "group_result_id": group.json()["id"],
            "label": "이은 Prony",
            "poisson_ratio": 0.4,
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    body = card.json()
    # 카드의 시험 종류는 응력완화다 — DMA 는 짧은 시간을 메운 근거다.
    assert body["test_type_key"] == "stress_relaxation"
    shown = body["blocks"]["viscoelastic"]["values"]
    assert shown["overlap_ratio"] == pytest.approx(values["overlap_ratio"])
    assert shown["dma_join_time_s"] == pytest.approx(values["dma_join_time_s"])
    assert body["blocks"]["elastic"]["values"]["youngs_modulus"] == pytest.approx(
        values["instantaneous_pa"]
    )


def test_겹친_구간이_크게_다르면_이유를_대고_묶지_않는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    run_ids = _coupled_runs(client, db, admin_headers, scale=2.0)
    group = client.post(
        "/api/groups",
        json={"plugin_id": "relaxation.dma_coupled", "run_ids": run_ids},
        headers=admin_headers,
    )
    assert group.status_code == 422, group.text
    assert "잇지 않습니다" in group.text


def test_받지_않는_시험_종류는_이름을_대고_막는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    _, run_ids = _upload(
        client,
        db,
        admin_headers,
        "creep",
        "creep_standard.csv",
        '{"applied_stress": 20000000, "temperature": 398.15}',
    )
    group = client.post(
        "/api/groups",
        json={"plugin_id": "relaxation.dma_coupled", "run_ids": run_ids},
        headers=admin_headers,
    )
    assert group.status_code == 422, group.text
    assert "creep" in group.text
