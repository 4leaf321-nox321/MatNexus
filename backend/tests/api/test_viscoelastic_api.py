"""점탄성 — **DMA 파일을 올려 카드 계수까지 한 줄기로.**

`matcore` 쪽은 답을 아는 합성 곡선으로 이미 검산했다(`test_viscoelastic.py`,
`test_prony.py`). 여기서 보는 것은 그 계산이 **저장소와 이어지는가** 다.

  - 한 시험의 어느 곡선이 온도 스윕인가
  - 온도는 어느 채널에서 어떻게 읽는가(한 스윕 안에서도 흔들린다)
  - 장비가 계산한 TTS 를 원본으로 착각하지 않는가
"""

from __future__ import annotations

import math
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
from app.modules.viscoelastic import services

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"


@pytest.fixture
def dma_run(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    """DMA 파일을 올려 읽힌 시험 하나."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()

    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "EPDM", "grade": "VE01", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": ("Example FreqTemp2.csv", FREQ_TEMP.read_bytes())},
        headers=admin_headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    run: dict[str, Any] = created
    return run


class Test겹칠_후보:
    def test_측정_스윕만_보여_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**장비가 계산한 TTS 는 후보가 아니다.** 그것을 겹치면 마스터커브에
        또 마스터커브를 씌우게 된다."""
        found = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()
        assert len(found["items"]) == 6
        for item in found["items"]:
            assert "TTS" not in (item["label"] or "")

    def test_온도를_대푯값으로_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """한 스윕 안에서도 온도가 흔들린다(실측 -40.00 ~ -40.99). 기준 온도를
        고르려면 스윕마다 값이 하나여야 한다."""
        found = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()
        celsius = sorted(round(item["temperature_k"] - 273.15) for item in found["items"])
        assert celsius == [-40, -30, -20, -10, 0, 10]

    def test_주파수_창을_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**각주파수만 있는 표가 실제로 있다.** 첫 스윕에만 `Frequency` 열이
        있고 나머지 여섯에는 없어서, 각주파수에서 만들어야 한다."""
        found = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()
        for item in found["items"]:
            assert item["minimum_frequency_hz"] > 0
            assert item["maximum_frequency_hz"] > item["minimum_frequency_hz"]


class Test마스터커브:
    def test_사람이_준_이동인자로_겹친다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """장비가 계산해 준 이동인자를 넣는 자리다. 실측 파일은 온도별 곡선이
        거의 같아서(강판) WLF 로는 이동이 0 이 나온다 — 그래서 여기서는 `manual`
        로 경로를 본다."""
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        shifts = {
            str(item["temperature_k"]): -1.0 * index
            for index, item in enumerate(sorted(sweeps, key=lambda x: x["temperature_k"]))
        }
        reference = min(item["temperature_k"] for item in sweeps)
        response = client.post(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves",
            json={
                "reference_temperature_k": reference,
                "method": "manual",
                "manual_shifts": shifts,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        curve = response.json()
        assert curve["method"] == "manual"
        assert len(curve["source_curve_keys"]) == 6
        assert curve["point_count"] > 0
        # 겹쳤으니 한 스윕보다 넓어야 한다.
        window = sweeps[0]["maximum_frequency_hz"] / sweeps[0]["minimum_frequency_hz"]
        widened = curve["maximum_frequency_hz"] / curve["minimum_frequency_hz"]
        assert widened > window

    def test_기준_온도가_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**없는 온도의 곡선을 지어내지 않는다.**"""
        response = client.post(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves",
            json={"reference_temperature_k": 500.0, "method": "wlf"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "잰 온도에 없습니다" in response.json()["error"]["message"]

    def test_점을_읽어_그릴_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = self._make(client, admin_headers, dma_run)
        points = client.get(
            f"/api/viscoelastic/master-curves/{curve['id']}/points", headers=admin_headers
        ).json()
        assert set(points) >= {"frequency", "storage_modulus", "loss_modulus"}
        assert len(points["frequency"]) == curve["point_count"]

    def test_목록에_남는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**만들고 나면 안 고친다.** 기준 온도를 바꾸면 새로 만들고, 둘 다 남는다."""
        self._make(client, admin_headers, dma_run)
        self._make(client, admin_headers, dma_run)
        listed = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves", headers=admin_headers
        ).json()
        assert len(listed) == 2

    @staticmethod
    def _make(
        client: TestClient, headers: dict[str, str], run: dict[str, Any]
    ) -> dict[str, Any]:
        sweeps = client.get(
            f"/api/viscoelastic/runs/{run['id']}/sweeps", headers=headers
        ).json()["items"]
        ordered = sorted(sweeps, key=lambda x: x["temperature_k"])
        shifts = {
            str(item["temperature_k"]): -1.0 * index for index, item in enumerate(ordered)
        }
        response = client.post(
            f"/api/viscoelastic/runs/{run['id']}/master-curves",
            json={
                "reference_temperature_k": ordered[0]["temperature_k"],
                "method": "manual",
                "manual_shifts": shifts,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        created: dict[str, Any] = response.json()
        return created


class TestProny:
    def test_후보를_재고_고른다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        response = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        fit = response.json()
        # **고른 것만 주지 않는다.** 사람이 다시 고를 수 있어야 한다.
        assert len(fit["candidates"]) > 1
        assert fit["bic"] == min(item["bic"] for item in fit["candidates"])
        assert fit["instantaneous_pa"] > fit["equilibrium_pa"]

    def test_항_수를_정해_줄_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        fit = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={"terms": 2},
            headers=admin_headers,
        ).json()
        assert len(fit["terms"]) == 2
        taus = [term["relaxation_time_s"] for term in fit["terms"]]
        assert taus == sorted(taus)

    def test_목록에_남는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={"terms": 2},
            headers=admin_headers,
        )
        listed = client.get(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony", headers=admin_headers
        ).json()
        assert len(listed) == 1


class Test커널과이어진다:
    def test_저장한_곡선이_커널이_낸_것과_같다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma_run: dict[str, Any],
    ) -> None:
        """저장·재읽기에서 값이 틀어지면 **계수만 보고는 절대 못 찾는다.**"""
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        row = services.curve_or_404(db, uuid.UUID(curve["id"]))
        columns = services.read_master_curve(row)
        assert len(columns["frequency"]) == row.point_count
        assert math.isclose(
            float(np.min(columns["frequency"])), row.minimum_frequency_hz, rel_tol=1e-9
        )
        assert float(np.min(columns["storage_modulus"])) > 0
