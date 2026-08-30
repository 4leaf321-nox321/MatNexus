"""휴지통 — **지운 것이 보이고, 되살아나고, 영영 사라진다.**

이 화면이 없어서 실제로 막혔다(2026-08-28). 이관에서 금속 재료를 지운 뒤 같은
이름으로 다시 넣으려다 전부 실패했는데, 막고 있던 그 행이 **화면 어디에도 없어서**
이유를 알 방법이 없었다.

**되돌릴 수 없는 자리라 사보타주 등급이 높다**(AGENTS: 삭제·병합). 그래서 무는
자리를 고를 때 「목록에 뜬다」 보다 **「잘못 되살리지 않는다」·「엉뚱한 것을 안
지운다」** 를 우선한다.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.trash import services
from app.shared.errors import AppError

SECC: dict[str, Any] = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "MDOI",
    "spec_thickness": 1.0,
}


def _tree(
    client: TestClient, headers: dict[str, str], details: str = "MDOI"
) -> dict[str, Any]:
    """재료 → 시료 → 시편 한 벌. **한 시험에서 둘을 만들 때는 `details` 를 가른다** —
    이름이 `등급_details_두께` 라 그대로 두면 두 번째가 409 로 막힌다."""
    material = client.post(
        "/api/materials", json={**SECC, "details": details}, headers=headers
    )
    assert material.status_code == 201, material.text
    material_id = material.json()["id"]
    sample = client.post(
        f"/api/materials/{material_id}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD", "seq_no": 1},
        headers=headers,
    ).json()
    return {"material": material.json(), "sample": sample, "specimen": specimen}


def _trash(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get("/api/trash", headers=headers)
    assert response.status_code == 200, response.text
    rows: list[dict[str, Any]] = response.json()
    return rows


class Test지운_것이_보인다:
    def test_지우면_목록에_뜬다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**이게 없어서 사고가 났다.** 목록에서 사라진 행이 이름을 붙들고 있는데
        그 행을 볼 데가 없으면, 사람은 「이미 있습니다」 를 설명할 수 없다."""
        made = _tree(client, admin_headers)
        client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        rows = _trash(client, admin_headers)
        mine = [row for row in rows if row["id"] == made["specimen"]["id"]]
        assert mine, "지운 시편이 휴지통에 안 보인다"
        assert mine[0]["kind"] == "specimen"
        assert mine[0]["kind_label"] == "시편"

    def test_안_지운_것은_안_뜬다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """살아 있는 것이 섞이면 이 목록은 그냥 전체 목록이 된다."""
        made = _tree(client, admin_headers)
        rows = _trash(client, admin_headers)
        assert not [row for row in rows if row["id"] == made["material"]["id"]]

    def test_아래에_무엇이_딸렸는지_함께_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**되살리기를 누를 근거다.** 화면이 스스로 세면 사람이 본 숫자와
        실제로 돌아오는 것이 어긋난다."""
        made = _tree(client, admin_headers)
        gone = client.post(
            f"/api/materials/{made['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text

        rows = _trash(client, admin_headers)
        material = next(row for row in rows if row["id"] == made["material"]["id"])
        assert material["below"].get("시료") == 1
        assert material["below"].get("시편") == 1

    def test_시스템_관리자만_본다(self, client: TestClient) -> None:
        """지운 것 목록은 **무엇이 있었는지**를 그대로 드러낸다."""
        assert client.get("/api/trash").status_code == 401


class Test되살린다:
    def test_되살리면_다시_보인다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = _tree(client, admin_headers)
        client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        back = client.post(
            f"/api/trash/specimen/{made['specimen']['id']}/restore", headers=admin_headers
        )
        assert back.status_code == 200, back.text

        alive = client.get(
            f"/api/samples/{made['sample']['id']}/specimens", headers=admin_headers
        ).json()
        assert [one for one in alive if one["id"] == made["specimen"]["id"]]
        assert not [
            row for row in _trash(client, admin_headers) if row["id"] == made["specimen"]["id"]
        ]

    def test_아래까지_함께_돌아온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """한 번의 삭제로 함께 죽었으니 함께 살아나야 한다. 재료만 살아나면
        **화면에서 닿을 수 없는 시료·시편**이 남는다."""
        made = _tree(client, admin_headers)
        client.post(
            f"/api/materials/{made['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )

        back = client.post(
            f"/api/trash/material/{made['material']['id']}/restore", headers=admin_headers
        )
        assert back.status_code == 200, back.text
        assert back.json()["counts"].get("시편") == 1

        alive = client.get(
            f"/api/samples/{made['sample']['id']}/specimens", headers=admin_headers
        ).json()
        assert [one for one in alive if one["id"] == made["specimen"]["id"]]

    def test_이름이_이미_차_있으면_막는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**지운 이름을 다시 쓸 수 있게 한 것과 짝이다**(v1.126.0). 그 이름으로
        새 재료가 이미 만들어졌을 수 있고, 그때 조용히 되살리면 살아 있는 쪽이
        다친다 — 유니크가 터지거나 둘 중 하나가 안 보이게 된다."""
        first = client.post("/api/materials", json=SECC, headers=admin_headers).json()
        assert (
            client.delete(f"/api/materials/{first['id']}", headers=admin_headers).status_code
            == 204
        )
        again = client.post("/api/materials", json=SECC, headers=admin_headers)
        assert again.status_code == 201, again.text

        row = next(row for row in _trash(client, admin_headers) if row["id"] == first["id"])
        assert row["blocked"], "막아야 하는데 안 막았다"
        assert "이미 살아 있습니다" in row["blocked"]

        blocked = client.post(
            f"/api/trash/material/{first['id']}/restore", headers=admin_headers
        )
        assert blocked.status_code == 409, blocked.text

    def test_상위가_죽어_있으면_막고_무엇부터인지_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**「안 됨」 만으로는 못 빠져나간다.** 무엇을 먼저 되살려야 하는지까지
        말해야 한다 — 처리 화면에서 「그냥 비활성」 으로 같은 실패를 했다."""
        made = _tree(client, admin_headers)
        client.post(
            f"/api/materials/{made['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )

        row = next(
            row for row in _trash(client, admin_headers) if row["id"] == made["specimen"]["id"]
        )
        assert row["blocked"] and "시료를 먼저" in row["blocked"]

    def test_안_지운_것은_못_되살린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = _tree(client, admin_headers)
        response = client.post(
            f"/api/trash/material/{made['material']['id']}/restore", headers=admin_headers
        )
        assert response.status_code == 409, response.text


class Test영영_지운다:
    def test_확인_없이는_안_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """창에서 물었더라도 서버가 다시 받는다 — 이 길은 API 로도 열려 있고,
        스크립트가 실수로 부르면 그 데이터는 돌아오지 않는다."""
        made = _tree(client, admin_headers)
        client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        response = client.delete(
            f"/api/trash/specimen/{made['specimen']['id']}", headers=admin_headers
        )
        assert response.status_code == 422, response.text
        assert [
            row for row in _trash(client, admin_headers) if row["id"] == made["specimen"]["id"]
        ], "확인을 안 줬는데 지워졌다"

    def test_확인하면_행이_진짜로_사라진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = _tree(client, admin_headers)
        client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        response = client.delete(
            f"/api/trash/specimen/{made['specimen']['id']}?confirm=true", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        assert not [
            row for row in _trash(client, admin_headers) if row["id"] == made["specimen"]["id"]
        ]
        assert (
            client.get(
                f"/api/specimens/{made['specimen']['id']}", headers=admin_headers
            ).status_code
            == 404
        )

    def test_재료_나무를_통째로_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**실측(2026-08-31)으로 드러난 결함이다.** 시편만 지우는 시험뿐이라
        재료를 통째로 지우는 길이 한 번도 안 걸렸고, 그 길은 언제나 500 이었다 —
        `db.delete` 가 표시만 하고 실제 삭제 순서는 flush 가 정하는데, 시료와
        재료 사이에 ORM 관계가 없어 재료를 먼저 지우려다 FK 가 막았다."""
        made = _tree(client, admin_headers)
        client.post(
            f"/api/materials/{made['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )

        response = client.delete(
            f"/api/trash/material/{made['material']['id']}?confirm=true", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        assert not _trash(client, admin_headers)

    def test_살아_있는_것은_못_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**여기가 제일 위험한 자리다.** 휴지통이 살아 있는 행을 지울 수 있으면,
        그것은 휴지통이 아니라 우회로다."""
        made = _tree(client, admin_headers)
        response = client.delete(
            f"/api/trash/specimen/{made['specimen']['id']}?confirm=true", headers=admin_headers
        )
        assert response.status_code == 409, response.text
        assert (
            client.get(
                f"/api/specimens/{made['specimen']['id']}", headers=admin_headers
            ).status_code
            == 200
        )


class TestPurgeMany:
    """**골라서 한꺼번에 영영 지운다.** 되돌릴 수 없는 자리라 무는 데를 고른다 —
    「여러 개가 지워진다」 보다 **「고르지 않은 것이 안 지워진다」·「겹쳐 골라도
    터지지 않는다」** 가 먼저다."""

    def test_고른_것만_지운다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        """**제일 위험한 자리다.** 하나를 더 지우면 그것은 돌아오지 않는다."""
        kept = _tree(client, admin_headers)
        gone = _tree(client, admin_headers, details="TD")
        for made in (kept, gone):
            client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        response = client.post(
            "/api/trash/purge",
            json={
                "items": [{"kind": "specimen", "id": gone["specimen"]["id"]}],
                "confirm": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["purged"] == 1

        left = {row["id"] for row in _trash(client, admin_headers)}
        assert gone["specimen"]["id"] not in left
        assert kept["specimen"]["id"] in left, "고르지 않은 것이 지워졌다"

    def test_확인_없이는_안_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = _tree(client, admin_headers)
        client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        response = client.post(
            "/api/trash/purge",
            json={"items": [{"kind": "specimen", "id": made["specimen"]["id"]}]},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert [
            row for row in _trash(client, admin_headers) if row["id"] == made["specimen"]["id"]
        ], "확인을 안 줬는데 지워졌다"

    def test_위아래를_함께_골라도_터지지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**이것 때문에 서버로 옮겼다.** 화면이 하나씩 부르면 재료를 지운 뒤 시료
        요청이 「없는 행」 으로 터지는데, 그때 재료는 이미 지워져 되돌릴 수 없다."""
        made = _tree(client, admin_headers)
        client.post(
            f"/api/materials/{made['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )

        response = client.post(
            "/api/trash/purge",
            json={
                # **아래를 먼저 적어 보낸다** — 서버가 계층 위부터 정렬하는지 본다.
                "items": [
                    {"kind": "specimen", "id": made["specimen"]["id"]},
                    {"kind": "sample", "id": made["sample"]["id"]},
                    {"kind": "material", "id": made["material"]["id"]},
                ],
                "confirm": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["requested"] == 3
        assert body["purged"] == 1, "재료 하나로 아래가 함께 사라져야 한다"
        assert body["skipped"] == 2

        assert not _trash(client, admin_headers)
        assert (
            client.get(
                f"/api/materials/{made['material']['id']}", headers=admin_headers
            ).status_code
            == 404
        )

    def test_같은_것을_두_번_보내도_한_번만_센다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = _tree(client, admin_headers)
        client.delete(f"/api/specimens/{made['specimen']['id']}", headers=admin_headers)

        ref = {"kind": "specimen", "id": made["specimen"]["id"]}
        response = client.post(
            "/api/trash/purge",
            json={"items": [ref, ref], "confirm": True},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["requested"] == 1
        assert response.json()["purged"] == 1

    def test_하나라도_못_지우면_전부_되돌린다(
        self, client: TestClient, db: Session, admin: Any, admin_headers: dict[str, str]
    ) -> None:
        """**셋만 지워진 채 오류를 보는 것보다 아무것도 안 지워진 편이 낫다** —
        무엇이 남았는지 다시 세어야 하는 상태를 만들지 않는다.

        **HTTP 로는 못 본다.** 운영에서는 요청마다 세션이 따로라 커밋을 못 하고
        닫히면 그대로 롤백되는데(`get_db`), 시험은 세션 하나를 모든 요청이 나눠
        쓰므로 밀어낸 삭제가 다음 요청에도 보인다. 그래서 운영과 같은 경로 —
        서비스를 직접 부르고 롤백 — 로 확인한다.
        """
        dead = _tree(client, admin_headers)
        alive = _tree(client, admin_headers, details="TD")
        client.delete(f"/api/specimens/{dead['specimen']['id']}", headers=admin_headers)

        with pytest.raises(AppError):
            services.purge_many(
                db,
                [
                    ("specimen", uuid.UUID(dead["specimen"]["id"])),
                    # 살아 있는 것 — 휴지통에 없다
                    ("specimen", uuid.UUID(alive["specimen"]["id"])),
                ],
                actor=admin,
            )
        db.rollback()

        assert [
            row for row in _trash(client, admin_headers) if row["id"] == dead["specimen"]["id"]
        ], "터졌는데 앞엣것이 지워져 있다"

    def test_로그인_없이는_못_지운다(self, client: TestClient) -> None:
        response = client.post(
            "/api/trash/purge",
            json={"items": [{"kind": "specimen", "id": str(uuid.uuid4())}], "confirm": True},
        )
        assert response.status_code in (401, 403)

    def test_빈_목록은_받지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/trash/purge", json={"items": [], "confirm": True}, headers=admin_headers
        )
        assert response.status_code == 422
