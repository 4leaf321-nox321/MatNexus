"""시편 규격 — **이름이 아니라 치수 한 벌이다.**

`ASTM E8 subsize` 는 게이지 길이 25 mm · 평행부 폭 6 mm 를 뜻한다. 그걸 어디에도
안 적어 두면 사람이 규격서를 펴 놓고 시편마다 옮겨 적고, 그러다 한 건이 틀리면
응력이 통째로 어긋나는데 숫자는 그럴듯해 보인다.

그런데 **칸이 시험 종류마다 다르다.** 인장 규격에는 어깨 반경이 있고 DMA 규격
에는 지지 간격이 있다. 하나의 고정된 칸 목록으로 둘을 담으면 절반이 늘 비고,
그 빈 칸이 "안 쟀다" 인지 "이 규격에 없는 값" 인지 구별되지 않는다.

여기서 지키는 것은 그 갈림이다 — 스키마를 시험 종류가 정하고, 스키마 밖의 값은
서버가 거절한다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.vocabulary.definitions import ensure_builtin_vocabularies

SLUG = "specimen_standard"


@pytest.fixture
def seeded(db: Session) -> None:
    ensure_builtin_vocabularies(db)
    ensure_builtin_test_types(db)
    db.commit()


def make(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    return client.post(f"/api/vocabularies/{SLUG}/terms", json=body, headers=headers)


class TestSchema:
    def test_시험_종류가_자기_칸을_선언한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**목록을 프론트에 적지 않는다.** 화면이 이 응답으로 폼을 그린다."""
        found = client.get(
            f"/api/vocabularies/{SLUG}/specimen-fields?kind=tensile", headers=admin_headers
        )
        assert found.status_code == 200, found.text
        keys = [item["key"] for item in found.json()]
        assert "gauge_length" in keys
        assert "shoulder_radius" in keys

    def test_인장과_DMA_는_칸이_다르다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """이 파일의 이유. 하나의 칸 목록으로는 둘을 담을 수 없다."""
        tensile = {
            item["key"]
            for item in client.get(
                f"/api/vocabularies/{SLUG}/specimen-fields?kind=tensile", headers=admin_headers
            ).json()
        }
        dma = {
            item["key"]
            for item in client.get(
                f"/api/vocabularies/{SLUG}/specimen-fields?kind=dma_sweep",
                headers=admin_headers,
            ).json()
        }
        assert tensile != dma
        # 인장에만 있는 것 / DMA 에만 있는 것이 둘 다 있어야 진짜로 다른 것이다.
        assert "shoulder_radius" in tensile - dma
        assert "span" in dma - tensile
        # 두께·폭처럼 겹치는 칸은 있다. 그게 정상이다.
        assert {"width", "thickness"} <= tensile & dma

    def test_고를_수_있는_종류를_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**상태 코드를 본다.** 처음에는 `json()` 만 보다가 500 을 놓쳤다 —
        `SELECT DISTINCT` 에 정렬 열이 select 에 없어서 Postgres 가 거절하고
        있었는데, 시험은 그 응답의 본문만 읽고 통과했다."""
        found = client.get(f"/api/vocabularies/{SLUG}/kinds", headers=admin_headers)
        assert found.status_code == 200, found.text
        keys = [item["key"] for item in found.json()]
        assert keys == ["tensile", "dma_sweep"]
        # 키가 아니라 이름을 함께 준다.
        assert found.json()[0]["label"] == "인장시험"

    def test_속성을_안_쓰는_축은_종류가_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        found = client.get("/api/vocabularies/manufacturer/kinds", headers=admin_headers)
        assert found.status_code == 200
        assert found.json() == []

    def test_속성을_안_쓰는_축은_칸이_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        found = client.get(
            "/api/vocabularies/manufacturer/specimen-fields?kind=tensile",
            headers=admin_headers,
        )
        assert found.json() == []

    def test_축이_속성을_쓰는지_목록이_말한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """화면이 "치수 칸을 그릴까" 를 이걸로 정한다."""
        listed = client.get("/api/vocabularies", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        axes = {item["slug"]: item["attribute_source"] for item in listed.json()}
        assert axes[SLUG] == "test_type"
        assert axes["manufacturer"] is None


class TestCreate:
    def test_치수를_갖는_규격을_만든다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        created = make(
            client,
            admin_headers,
            value="ASTM E8 subsize",
            kind="tensile",
            # **SI 로 보낸다.** 규격서는 mm 로 적혀 있지만 저장은 m 다.
            attributes={"gauge_length": 0.025, "width": 0.006},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["kind"] == "tensile"
        # 키가 아니라 이름을 준다 — `dma_sweep` 은 사람이 읽는 말이 아니다.
        assert body["kind_label"] == "인장시험"
        assert body["attributes"]["gauge_length"] == 0.025

    def test_그_종류에_없는_칸은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**오타 하나가 조용히 새 속성이 되면 아무도 못 찾는다.**"""
        rejected = make(
            client,
            admin_headers,
            value="이상한 규격",
            kind="tensile",
            attributes={"gauge_length": 0.025, "width": 0.006, "span": 0.05},
        )
        assert rejected.status_code == 422
        assert "span" in rejected.json()["error"]["message"]

    def test_필수_치수가_비면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """게이지 길이 없는 인장 규격은 규격이 아니다."""
        rejected = make(
            client,
            admin_headers,
            value="반쪽 규격",
            kind="tensile",
            attributes={"width": 0.006},
        )
        assert rejected.status_code == 422
        assert "게이지 길이" in rejected.json()["error"]["message"]

    def test_없는_시험_종류는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        rejected = make(client, admin_headers, value="오타 규격", kind="tensil")
        assert rejected.status_code == 422

    def test_속성을_안_쓰는_축에는_속성을_못_넣는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        rejected = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "포스코", "attributes": {"gauge_length": 0.025}},
            headers=admin_headers,
        )
        assert rejected.status_code == 422

    def test_종류_없이도_이름만_만들_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**피커를 막지 않는다.** 시편을 등록하다 규격 이름을 처음 치는 사람이
        치수를 다 아는 것은 아니다. 치수는 관리 화면에서 나중에 채운다."""
        created = make(client, admin_headers, value="사내 규격 A")
        assert created.status_code == 201
        assert created.json()["kind"] is None
        assert created.json()["attributes"] == {}

    def test_이미_있는_값의_치수를_덮어쓰지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """피커는 이름만 치고 낙관적으로 보낸다. 그때 조용히 덮어쓰면 남이 채운
        규격 치수가 사라진다."""
        make(
            client,
            admin_headers,
            value="JIS 5호",
            kind="tensile",
            attributes={"gauge_length": 0.05, "width": 0.025},
        )
        again = make(client, admin_headers, value="JIS 5호")
        assert again.status_code == 201
        assert again.json()["attributes"]["gauge_length"] == 0.05


class TestUpdate:
    def _term(self, client: TestClient, headers: dict[str, str]) -> str:
        created = make(
            client,
            headers,
            value="ASTM E8",
            kind="tensile",
            attributes={"gauge_length": 0.05, "width": 0.0125},
        )
        return str(created.json()["id"])

    def test_치수를_고친다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = self._term(client, admin_headers)
        updated = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"gauge_length": 0.05, "width": 0.0125, "thickness": 0.001}},
            headers=admin_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["attributes"]["thickness"] == 0.001

    def test_종류를_바꾸면_예전_칸은_안_따라간다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**스키마가 바뀌면 값도 바뀐다.** 인장 치수를 든 채로 DMA 가 되면
        그 값들은 스키마 밖이고, 남겨 두면 화면이 못 보여 주는 유령이 된다."""
        term_id = self._term(client, admin_headers)
        moved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"kind": "dma_sweep"},
            headers=admin_headers,
        )
        # 새 스키마의 필수 칸이 비었으므로 거절된다 — 조용히 비우지 않는다.
        assert moved.status_code == 422

        together = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "kind": "dma_sweep",
                "attributes": {"free_length": 0.02, "width": 0.005, "thickness": 0.001},
            },
            headers=admin_headers,
        )
        assert together.status_code == 200
        assert together.json()["kind"] == "dma_sweep"
        assert "gauge_length" not in together.json()["attributes"]

    def test_이름을_고쳐도_치수는_그대로다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = self._term(client, admin_headers)
        renamed = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"value": "ASTM E8 (2024)"},
            headers=admin_headers,
        )
        assert renamed.status_code == 200
        assert renamed.json()["attributes"]["gauge_length"] == 0.05


class TestFieldEditing:
    """치수 칸을 **기준정보 화면에서 고친다.**

    칸은 시험 종류의 것이지만, 고치고 싶어지는 자리는 규격을 적다가다 —
    "ASTM E8 에 그립부 길이도 적고 싶은데 칸이 없네" 는 규격 화면에서 나온다.
    """

    def _fields(self, client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
        found = client.get(
            f"/api/vocabularies/{SLUG}/specimen-fields?kind=tensile", headers=headers
        )
        assert found.status_code == 200, found.text
        rows: list[dict[str, Any]] = found.json()
        return rows

    def test_칸을_더한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        current = self._fields(client, admin_headers)
        saved = client.put(
            f"/api/vocabularies/{SLUG}/specimen-fields?kind=tensile",
            json={
                "fields": [
                    {
                        "key": item["key"],
                        "label": item["label"],
                        "dimension": item["dimension"],
                        "si_unit": item["si_unit"],
                        "is_required": item["is_required"],
                        "help": item["help"],
                    }
                    for item in current
                ]
                + [
                    {
                        "key": "grip_length",
                        "label": "그립부 길이",
                        "dimension": "length",
                        "si_unit": "m",
                        "is_required": False,
                        "help": None,
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        assert [item["key"] for item in saved.json()][-1] == "grip_length"

    def test_뺀_칸의_값은_안_지운다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**화면에서 사라질 뿐이다.** 지워 버리면 되살릴 방법이 없다."""
        term_id = str(
            make(
                client,
                admin_headers,
                value="ASTM E8 wide",
                kind="tensile",
                attributes={"gauge_length": 0.05, "width": 0.0125, "shoulder_radius": 0.006},
            ).json()["id"]
        )

        client.put(
            f"/api/vocabularies/{SLUG}/specimen-fields?kind=tensile",
            json={
                "fields": [
                    {
                        "key": "gauge_length",
                        "label": "게이지 길이",
                        "dimension": "length",
                        "si_unit": "m",
                        "is_required": True,
                        "help": None,
                    },
                    {
                        "key": "width",
                        "label": "평행부 폭",
                        "dimension": "length",
                        "si_unit": "m",
                        "is_required": True,
                        "help": None,
                    },
                ]
            },
            headers=admin_headers,
        )

        listed = client.get(
            f"/api/vocabularies/{SLUG}/terms?q=ASTM E8 wide", headers=admin_headers
        ).json()
        term = next(item for item in listed["items"] if item["id"] == term_id)
        # 값은 그대로 있다 — 칸을 되살리면 다시 보인다.
        assert term["attributes"]["shoulder_radius"] == 0.006

    def test_이름이_겹치면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        rejected = client.put(
            f"/api/vocabularies/{SLUG}/specimen-fields?kind=tensile",
            json={
                "fields": [
                    {
                        "key": "gauge_length",
                        "label": "게이지 길이",
                        "dimension": "length",
                        "si_unit": "m",
                        "is_required": True,
                        "help": None,
                    },
                    {
                        "key": "gauge_length",
                        "label": "또 게이지 길이",
                        "dimension": "length",
                        "si_unit": "m",
                        "is_required": False,
                        "help": None,
                    },
                ]
            },
            headers=admin_headers,
        )
        assert rejected.status_code == 422

    def test_속성을_안_쓰는_축에는_칸을_못_만든다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        rejected = client.put(
            "/api/vocabularies/manufacturer/specimen-fields?kind=tensile",
            json={"fields": []},
            headers=admin_headers,
        )
        assert rejected.status_code == 422
