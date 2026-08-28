"""묶음 — **여러 시험을 묶어 만든 것이 행으로 남고, 카드까지 가는가.**

계산 자체는 `tests/unit/test_groups_prony.py` 가 본다. 여기서 보는 것은 그것이
**저장소와 이어지는가** 다(점탄성 API 시험과 같은 갈래).

무는 자리를 고를 때 「만들어진다」 보다 **「고른 것과 쓴 것이 다를 때 그 차이가
남는가」**·**「섞으면 막는가」** 를 우선한다. 앞엣것은 눈에 보이고, 뒤엣것은
조용히 틀린다 — 다른 재료의 시편을 묶은 계수는 어느 재료의 것도 아니다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"

PLUGIN = "viscoelastic.prony_group"


def _material(client: TestClient, headers: dict[str, str], grade: str) -> dict[str, Any]:
    made: dict[str, Any] = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "EPDM", "grade": grade, "spec_thickness": 1.0},
        headers=headers,
    ).json()
    return made


def _run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    material: dict[str, Any],
    *,
    orientation: str = "MD",
) -> dict[str, Any]:
    """그 재료 아래 DMA 시험 하나. 시편도 함께 만든다."""
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": orientation},
        headers=headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": ("Example FreqTemp2.csv", FREQ_TEMP.read_bytes())},
        headers=headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    run: dict[str, Any] = created
    return run


def _master_curve(client: TestClient, headers: dict[str, str], run: dict[str, Any]) -> None:
    """그 시험의 마스터커브. **묶으려면 먼저 겹쳐야 한다.**"""
    sweeps = client.get(f"/api/viscoelastic/runs/{run['id']}/sweeps", headers=headers).json()[
        "items"
    ]
    shifts = {
        str(item["temperature_k"]): -1.0 * index
        for index, item in enumerate(sorted(sweeps, key=lambda x: x["temperature_k"]))
    }
    response = client.post(
        f"/api/viscoelastic/runs/{run['id']}/master-curves",
        json={
            "reference_temperature_k": min(item["temperature_k"] for item in sweeps),
            "method": "manual",
            "manual_shifts": shifts,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


@pytest.fixture
def two_runs(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    """한 재료 아래 마스터커브까지 만든 시험 둘."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()

    material = _material(client, admin_headers, "VG01")
    runs = [_run(client, db, admin_headers, material) for _ in range(2)]
    for run in runs:
        _master_curve(client, admin_headers, run)
    return {"material": material, "runs": runs}


class Test고를_수_있는_묶음:
    def test_레지스트리가_목록을_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**화면이 목록을 적어 두면** 새 물성을 붙일 때 화면도 고쳐야 한다."""
        found = client.get("/api/groups/kinds", headers=admin_headers).json()
        mine = next(item for item in found if item["id"] == PLUGIN)
        assert {one["name"] for one in mine["params"]} == {
            "method",
            "terms",
            "representative",
        }

    def test_고를_값도_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        found = client.get("/api/groups/kinds", headers=admin_headers).json()
        mine = next(item for item in found if item["id"] == PLUGIN)
        method = next(one for one in mine["params"] if one["name"] == "method")
        assert set(method["choices"]) == {"pooled", "averaged", "representative"}


class Test묶어서_남긴다:
    def test_행으로_남는다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        made = client.post(
            "/api/groups",
            json={
                "plugin_id": PLUGIN,
                "run_ids": [run["id"] for run in two_runs["runs"]],
                "options": {"method": "pooled"},
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        body = made.json()
        assert body["values"]["equilibrium_pa"] > 0
        assert body["detail"]["terms"]

        listed = client.get(
            f"/api/groups/materials/{two_runs['material']['id']}", headers=admin_headers
        ).json()
        assert [one["id"] for one in listed] == [body["id"]]

    def test_그때_고른_것을_그대로_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        """**불변이다.** 「왜 이 값이 이래」 에 답하려면 그때의 방법과 구성원이
        남아 있어야 한다."""
        body = client.post(
            "/api/groups",
            json={
                "plugin_id": PLUGIN,
                "run_ids": [run["id"] for run in two_runs["runs"]],
                "options": {"method": "pooled", "terms": 3},
            },
            headers=admin_headers,
        ).json()
        assert body["options"] == {"method": "pooled", "terms": 3}
        assert len(body["members"]) == 2
        assert all(item["label"] for item in body["members"])

    def test_쓴_것을_따로_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        """**대표를 고르면 둘을 골라도 하나만 쓴다.** 그 차이가 안 보이면
        「둘을 묶었다」 가 거짓말이 된다."""
        for run in two_runs["runs"]:
            curve = client.get(
                f"/api/viscoelastic/runs/{run['id']}/master-curves", headers=admin_headers
            ).json()[0]
            client.post(
                f"/api/viscoelastic/master-curves/{curve['id']}/prony",
                json={},
                headers=admin_headers,
            )

        body = client.post(
            "/api/groups",
            json={
                "plugin_id": PLUGIN,
                "run_ids": [run["id"] for run in two_runs["runs"]],
                "options": {"method": "representative"},
            },
            headers=admin_headers,
        ).json()
        assert len(body["members"]) == 2
        assert len(body["used"]) == 1

    def test_하나만_주면_스키마가_막는다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        response = client.post(
            "/api/groups",
            json={"plugin_id": PLUGIN, "run_ids": [two_runs["runs"][0]["id"]]},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text


class Test섞으면_막는다:
    def test_재료가_다르면_막는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**다른 재료의 시편을 묶은 계수는 어느 재료의 것도 아니다.** 카드는
        재료에 붙는다."""
        ensure_builtin_test_types(db)
        ensure_builtin_format_profiles(db)
        db.commit()

        runs = [
            _run(client, db, admin_headers, _material(client, admin_headers, grade))
            for grade in ("VX01", "VX02")
        ]
        for run in runs:
            _master_curve(client, admin_headers, run)

        response = client.post(
            "/api/groups",
            json={"plugin_id": PLUGIN, "run_ids": [run["id"] for run in runs]},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "재료" in response.json()["error"]["message"]

    def test_마스터커브가_없으면_먼저_겹치라고_한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**「못 한다」 만으로는 못 빠져나간다.** 무엇을 먼저 해야 하는지까지."""
        ensure_builtin_test_types(db)
        ensure_builtin_format_profiles(db)
        db.commit()

        material = _material(client, admin_headers, "VY01")
        runs = [_run(client, db, admin_headers, material) for _ in range(2)]
        response = client.post(
            "/api/groups",
            json={"plugin_id": PLUGIN, "run_ids": [run["id"] for run in runs]},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "먼저 겹치세요" in response.json()["error"]["message"]

    def test_모르는_묶음은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        response = client.post(
            "/api/groups",
            json={
                "plugin_id": "tensile.strength",
                "run_ids": [run["id"] for run in two_runs["runs"]],
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text


class Test카드까지_간다:
    def test_묶음에서_카드를_만든다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        """**여기까지 와야 쓸 수 있다.** 묶어 놓고 카드로 못 가면 만든 뜻이 없다."""
        group = client.post(
            "/api/groups",
            json={
                "plugin_id": PLUGIN,
                "run_ids": [run["id"] for run in two_runs["runs"]],
                "options": {"method": "pooled"},
            },
            headers=admin_headers,
        ).json()

        made = client.post(
            "/api/fitting/cards/viscoelastic",
            json={
                "group_result_id": group["id"],
                "label": "EPDM 묶음 점탄성",
                "poisson_ratio": 0.45,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        card = made.json()
        # **표본 수가 덱까지 따라가야 한다.** 1건인지 둘을 묶은 것인지가
        # 「이 물성 어디서 났나」 의 답이다.
        assert card["source"]["sample_count"] == 2
        assert card["source"]["group_result_id"] == group["id"]
        assert card["source"]["group_method"] == "pooled"

    def test_둘_다_주면_막는다(
        self, client: TestClient, admin_headers: dict[str, str], two_runs: dict[str, Any]
    ) -> None:
        """**카드의 근거가 둘이 되면 안 된다.** 나중에 「이 값이 어디서 났나」 에
        답이 둘이 된다."""
        group = client.post(
            "/api/groups",
            json={
                "plugin_id": PLUGIN,
                "run_ids": [run["id"] for run in two_runs["runs"]],
            },
            headers=admin_headers,
        ).json()
        curve = client.get(
            f"/api/viscoelastic/runs/{two_runs['runs'][0]['id']}/master-curves",
            headers=admin_headers,
        ).json()[0]
        fit = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={},
            headers=admin_headers,
        ).json()

        response = client.post(
            "/api/fitting/cards/viscoelastic",
            json={
                "group_result_id": group["id"],
                "prony_fit_id": fit["id"],
                "label": "둘 다",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text

    def test_아무것도_안_주면_막는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"label": "근거 없음"},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
