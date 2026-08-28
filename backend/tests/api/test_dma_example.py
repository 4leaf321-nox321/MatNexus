"""예제 DMA — **되찾은 값이 넣은 값과 맞는가.**

다른 DMA 시험들은 실파일(`dma_freq_temp.csv`)을 쓴다. 그건 읽히는지·안 터지는지는
보여 주지만 **나온 값이 맞는지는 못 본다** — 정답을 모르기 때문이다.

여기 파일은 3항 일반화 Maxwell 로 만들었다(`scripts/make_example_dma.py`). 그래서
계수를 정답과 견줄 수 있고, **실제로 그 견주기가 결함을 잡았다** — 묶음 평균이
τ 격자를 주파수 창에서 뽑는 바람에 E∞ 가 0 이 됐다(v1.135.0). 단위 시험은 정답 τ 를
직접 줘서 맞는지 봤기 때문에 그 자리가 시험 밖에 있었다.

**그래서 이 시험은 「돌아간다」 를 안 본다.** 넣은 숫자가 돌아오는지만 본다.
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
TEMP_SWEEPS = sorted(FIXTURES.glob("example_dma_temp_sweep_*.csv"))
STRAIN_SWEEP = FIXTURES / "example_dma_strain_sweep.csv"

#: `scripts/make_example_dma.py` 가 넣은 값. **두 곳에 적는 것이 맞다** — 시험이
#: 생성기를 import 하면 같은 실수를 함께 하게 된다.
TRUE_EQUILIBRIUM_PA = 5.0e6
TRUE_TAUS_S = (1.0e-2, 1.0e0, 1.0e2)
TRUE_INSTANTANEOUS_PA = 5.0e6 + 2.0e8 + 8.0e8 + 3.0e8
TRUE_STRAIN_PLATEAU_PA = 1.20e9

REFERENCE_K = 293.15


def _upload(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    sample: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "NA"},
        headers=headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": (path.name, path.read_bytes())},
        headers=headers,
    ).json()
    # **제 손으로 읽는다.** 올리기는 큐에 넣을 뿐이고 시험 환경에는 워커가 없다.
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    run: dict[str, Any] = created
    return run


@pytest.fixture
def sample(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "EPDM", "grade": "EX", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    made: dict[str, Any] = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    return made


class Test변형률_스윕:
    """평탄부의 높이가 E — **인장의 탄성계수와 같은 자리.**"""

    def test_넣은_평탄값을_되찾는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        run = _upload(client, db, admin_headers, sample, STRAIN_SWEEP)
        stored = client.post(
            "/api/processing/results",
            json={
                "test_run_id": run["id"],
                "steps": [{"plugin": "dma.lve_modulus", "options": {}}],
            },
            headers=admin_headers,
        )
        assert stored.status_code == 201, stored.text
        values = {one["key"]: one["value"] for one in stored.json()["scalars"]}

        # 평탄부 **평균**이라 넣은 값보다 조금 낮다. 2 % 안이면 맞다.
        assert values["youngs_modulus"] == pytest.approx(TRUE_STRAIN_PLATEAU_PA, rel=0.02)
        assert values["lve_point_count"] >= 3

    def test_탄성_블록이_받는_이름으로_낸다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        """**카드가 인장에서 왔는지 DMA 에서 왔는지 몰라도 되게.** 키를 따로
        두면 블록마다 대응표를 손으로 적어야 한다."""
        run = _upload(client, db, admin_headers, sample, STRAIN_SWEEP)
        stored = client.post(
            "/api/processing/results",
            json={
                "test_run_id": run["id"],
                "steps": [{"plugin": "dma.lve_modulus", "options": {}}],
            },
            headers=admin_headers,
        ).json()
        assert "youngs_modulus" in {one["key"] for one in stored["scalars"]}


class Test온도_스윕:
    """겹쳐서 Prony 로 — **넣은 계수가 돌아오는가.**"""

    def _master_curve(
        self, client: TestClient, headers: dict[str, str], run: dict[str, Any]
    ) -> dict[str, Any]:
        made = client.post(
            f"/api/viscoelastic/runs/{run['id']}/master-curves",
            json={"reference_temperature_k": REFERENCE_K, "method": "wlf"},
            headers=headers,
        )
        assert made.status_code == 201, made.text
        curve: dict[str, Any] = made.json()
        return curve

    def test_겹치면_잰_창보다_넓어진다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        """**그것이 겹치는 이유다.** 한 온도에서는 0.1~20 Hz 밖에 못 본다."""
        run = _upload(client, db, admin_headers, sample, TEMP_SWEEPS[0])
        curve = self._master_curve(client, admin_headers, run)
        widened = curve["maximum_frequency_hz"] / curve["minimum_frequency_hz"]
        assert widened > 1.0e4

    def test_단독_적합이_넣은_계수를_되찾는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        run = _upload(client, db, admin_headers, sample, TEMP_SWEEPS[0])
        curve = self._master_curve(client, admin_headers, run)
        fit = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={"terms": 3},
            headers=admin_headers,
        )
        assert fit.status_code == 201, fit.text
        body = fit.json()

        taus = sorted(term["relaxation_time_s"] for term in body["terms"])
        for got, want in zip(taus, TRUE_TAUS_S, strict=True):
            assert got == pytest.approx(want, rel=0.15)
        assert body["instantaneous_pa"] == pytest.approx(TRUE_INSTANTANEOUS_PA, rel=0.05)


class Test세_방법이_다_말이_되는가:
    """**이 시험이 결함을 잡았다.** 묶음 평균이 τ 격자를 주파수 창에서 뽑는
    바람에 E∞ 가 0 이 됐는데, 곡선은 그대로 지나가서 오류가 안 났다.

    그래서 무는 자리는 「돌아간다」 가 아니라 **「E∞ 가 사라지지 않는가」** 다.
    """

    @pytest.fixture
    def three(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> list[dict[str, Any]]:
        runs = [_upload(client, db, admin_headers, sample, path) for path in TEMP_SWEEPS]
        for run in runs:
            curve = client.post(
                f"/api/viscoelastic/runs/{run['id']}/master-curves",
                json={"reference_temperature_k": REFERENCE_K, "method": "wlf"},
                headers=admin_headers,
            ).json()
            client.post(
                f"/api/viscoelastic/master-curves/{curve['id']}/prony",
                json={"terms": 3},
                headers=admin_headers,
            )
        return runs

    @pytest.mark.parametrize("method", ["pooled", "averaged", "representative"])
    def test_평형_탄성률이_사라지지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        three: list[dict[str, Any]],
        method: str,
    ) -> None:
        """**0.0013 Pa 가 나왔던 자리다.** 그 값이 카드에 실리면 「완화가 끝나면
        힘을 못 받는 재료」 가 된다 — 덱은 멀쩡히 돌고 결과만 틀린다."""
        made = client.post(
            "/api/groups",
            json={
                "plugin_id": "viscoelastic.prony_group",
                "run_ids": [run["id"] for run in three],
                "options": {"method": method, "terms": 3},
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        values = made.json()["values"]

        # **`approx(..., rel=1.0)` 으로 쓰면 안 된다.** 그건 [0, 2배] 라서
        # 0.0013 Pa 도 통과한다 — 잡으려던 바로 그 값이다(사보타주로 확인).
        # 아래위로 3 배 안이면 「사라지지 않았다」 고 말할 수 있다.
        assert TRUE_EQUILIBRIUM_PA / 3 < values["equilibrium_pa"] < TRUE_EQUILIBRIUM_PA * 3
        assert values["instantaneous_pa"] == pytest.approx(TRUE_INSTANTANEOUS_PA, rel=0.1)

    def test_세_방법이_서로_다른_답을_낸다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        three: list[dict[str, Any]],
    ) -> None:
        """**같은 답이 나오면 셋을 둘 이유가 없다.** 예제 시편을 흩어 놓은 것이
        그래서다(0 / +6 / -5 %)."""
        answers = {}
        for method in ("pooled", "averaged", "representative"):
            body = client.post(
                "/api/groups",
                json={
                    "plugin_id": "viscoelastic.prony_group",
                    "run_ids": [run["id"] for run in three],
                    "options": {"method": method, "terms": 3},
                },
                headers=admin_headers,
            ).json()
            answers[method] = body["values"]["equilibrium_pa"]
        assert len(set(answers.values())) == 3, answers
