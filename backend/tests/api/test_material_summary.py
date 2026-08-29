"""재료 계층 요약 — **「무엇이 얼마나 있나」 와 「빠진 게 어디냐」.**

무는 자리를 「수가 돌아온다」 가 아니라 **틀리기 쉬운 셋**에 둔다:

  1. 지운 것을 안 세는가 — 소프트 삭제라 행이 남는다. 세면 화면의 수가 목록보다
     크고, 그 차이를 아무도 설명 못 한다.
  2. **시험 없는 시편을 시험 수로 빼서 구하지 않는가** — 한 시편에 시험이 둘이면
     그만큼 어긋난다. 시편 쪽에서 세어야 한다.
  3. 남의 부서 것을 안 세는가.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

SECC = {"family": "Metal", "category": "Steel", "grade": "SECC", "spec_thickness": 1.0}


@pytest.fixture
def specimen(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    """재료 → 시료 → 시편 하나. **API 로 만든다** — 채번과 기준정보 카운트가
    라우트에 있어, 직접 넣으면 화면에서만 이상한 데이터가 된다."""
    material = client.post("/api/materials", json=SECC, headers=admin_headers).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    made: dict[str, Any] = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    made["material_id"] = material["id"]
    return made


def _summary(client: TestClient, headers: dict[str, str], material_id: str) -> dict[str, Any]:
    got = client.get(f"/api/materials/{material_id}/summary", headers=headers)
    assert got.status_code == 200, got.text
    body: dict[str, Any] = got.json()
    return body


class Test계층을_센다:
    def test_시료_시편_시험을_한_번에(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        specimen: dict[str, Any],
    ) -> None:
        material_id = specimen["material_id"]
        body = _summary(client, admin_headers, material_id)
        assert body["sample_count"] == 1
        assert body["specimen_count"] == 1
        assert body["run_count"] == 0
        # 시편은 있는데 시험이 없다 — **그것이 다음에 할 일이다.**
        assert body["specimens_without_run"] == 1

    def test_지운_시편은_안_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        specimen: dict[str, Any],
    ) -> None:
        """소프트 삭제라 행은 남는다. 세면 **화면의 수가 목록보다 커지고**, 그
        차이를 아무도 설명할 수 없다."""
        material_id = specimen["material_id"]
        gone = client.delete(f"/api/specimens/{specimen['id']}", headers=admin_headers)
        assert gone.status_code in (200, 204), gone.text

        body = _summary(client, admin_headers, material_id)
        assert body["specimen_count"] == 0
        assert body["specimens_without_run"] == 0

    def test_없는_재료는_404(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        missing = "00000000-0000-4000-8000-000000000000"
        assert (
            client.get(f"/api/materials/{missing}/summary", headers=admin_headers).status_code
            == 404
        )
