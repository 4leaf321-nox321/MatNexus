"""시편 규격 — **이름이 아니라 치수 한 벌이다. 그리고 칸이 규격마다 다르다.**

`ASTM E8 subsize` 는 게이지 길이 25 mm · 평행부 폭 6 mm 를 뜻한다. 그걸 어디에도
안 적어 두면 사람이 규격서를 펴 놓고 시편마다 옮겨 적고, 그러다 한 건이 틀리면
응력이 통째로 어긋나는데 숫자는 그럴듯해 보인다.

**같은 시험 안에서도 시편에 따라 칸이 갈린다.** 인장 평판은 폭·두께를 갖고
환봉은 직경을 갖는다. DMA 3점 굽힘에는 지지 간격이 있고 인장 필름에는 없다
(실측: DMA 실파일 172개 전부에 장비가 적은 `Geometry name` 이 있고 155개가
`3 Point Bending Clamp` 였다).

그래서 두 층이다.

    시편 분류의 기본 칸   그 분류의 규격이면 **예외 없이** 갖는 것
    규격의 추가 칸        그 규격만 갖는 것

여기서 지키는 것은 그 갈림이다 — 기본 칸은 분류가 정하고, 규격은 자기 칸을
더하며, 스키마 밖의 값은 서버가 거절한다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.vocabulary.definitions import (
    ensure_builtin_specimen_categories,
    ensure_builtin_vocabularies,
)

SLUG = "specimen_standard"
CATEGORY_SLUG = "specimen_category"


@pytest.fixture
def seeded(db: Session) -> None:
    ensure_builtin_vocabularies(db)
    ensure_builtin_specimen_categories(db)
    db.commit()


def make(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    return client.post(f"/api/vocabularies/{SLUG}/terms", json=body, headers=headers)


def category_id(client: TestClient, headers: dict[str, str], value: str) -> str:
    listed = client.get(f"/api/vocabularies/{CATEGORY_SLUG}/terms?q={value}", headers=headers)
    assert listed.status_code == 200, listed.text
    return str(next(item for item in listed.json()["items"] if item["value"] == value)["id"])


def fields_of(client: TestClient, headers: dict[str, str], slug: str, term_id: str) -> Any:
    found = client.get(f"/api/vocabularies/{slug}/terms/{term_id}/fields", headers=headers)
    assert found.status_code == 200, found.text
    return found.json()


def extra(key: str, label: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "dimension": "length",
        "si_unit": "m",
        "is_required": required,
        "help": None,
    }


class TestSchema:
    def test_축이_속성을_쓰는지_목록이_말한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """화면이 "치수 칸을 그릴까" 를 이걸로 정한다."""
        listed = client.get("/api/vocabularies", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        axes = {item["slug"]: item for item in listed.json()}
        assert axes[SLUG]["attribute_source"] == "parent"
        # 규격은 분류 아래 산다 — 축 계층 기계를 그대로 쓴다.
        assert axes[SLUG]["parent_slug"] == CATEGORY_SLUG
        assert axes["manufacturer"]["attribute_source"] is None

    def test_분류가_기본_칸을_갖는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        tensile = fields_of(
            client, admin_headers, CATEGORY_SLUG, category_id(client, admin_headers, "인장")
        )
        assert [item["key"] for item in tensile] == ["gauge_length", "total_length"]
        # 분류에서 보는 자기 칸은 **여기서 고칠 수 있다** — 물려받은 것이 아니다.
        assert not any(item["inherited"] for item in tensile)

    def test_인장과_DMA_는_기본_칸이_다르다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        tensile = {
            item["key"]
            for item in fields_of(
                client,
                admin_headers,
                CATEGORY_SLUG,
                category_id(client, admin_headers, "인장"),
            )
        }
        dma = {
            item["key"]
            for item in fields_of(
                client, admin_headers, CATEGORY_SLUG, category_id(client, admin_headers, "DMA")
            )
        }
        assert tensile != dma
        assert "gauge_length" in tensile - dma
        assert "free_length" in dma - tensile

    def test_분류를_안_고른_규격은_칸이_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**피커를 막지 않는다.** 치수를 모른 채 규격 이름부터 적는 일이 있다."""
        term_id = str(make(client, admin_headers, value="사내 규격 A").json()["id"])
        assert fields_of(client, admin_headers, SLUG, term_id) == []


class TestInherit:
    def _standard(self, client: TestClient, headers: dict[str, str], value: str) -> str:
        created = make(client, headers, value=value, parent_value="인장")
        assert created.status_code == 201, created.text
        assert created.json()["parent_value"] == "인장"
        return str(created.json()["id"])

    def _add_diameter(self, client: TestClient, headers: dict[str, str], term_id: str) -> Any:
        return client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": [extra("diameter", "직경", required=True)]},
            headers=headers,
        )

    def test_규격이_분류의_칸을_물려받는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = self._standard(client, admin_headers, "ASTM E8 subsize")
        keys = [item["key"] for item in fields_of(client, admin_headers, SLUG, term_id)]
        assert keys == ["gauge_length", "total_length"]

    def test_규격이_자기_칸을_더한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**이 파일의 이유.** 환봉 규격에는 직경이 필요하고 평판에는 없다."""
        term_id = self._standard(client, admin_headers, "ASTM E8 R1")
        assert self._add_diameter(client, admin_headers, term_id).status_code == 200

        fields = fields_of(client, admin_headers, SLUG, term_id)
        assert [item["key"] for item in fields] == ["gauge_length", "total_length", "diameter"]
        # 어느 쪽 칸인지 가른다 — 지우려면 갈 곳이 다르다.
        assert [item["inherited"] for item in fields] == [True, True, False]

    def test_다른_규격은_그_칸을_안_갖는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """직경을 ASTM E8 R1 에 더해도 JIS 5호(평판)에는 안 생긴다."""
        self._add_diameter(
            client, admin_headers, self._standard(client, admin_headers, "ASTM E8 R1")
        )
        flat_id = self._standard(client, admin_headers, "JIS 5호")
        keys = [item["key"] for item in fields_of(client, admin_headers, SLUG, flat_id)]
        assert "diameter" not in keys

    def test_분류의_칸과_같은_키는_못_쓴다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """같은 키가 둘이면 어느 쪽이 이기는지 사람이 알 방법이 없다."""
        term_id = self._standard(client, admin_headers, "겹치는 규격")
        rejected = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": [extra("gauge_length", "게이지 길이(또)")]},
            headers=admin_headers,
        )
        assert rejected.status_code == 422
        assert "gauge_length" in rejected.json()["error"]["message"]


class TestAttributes:
    def _standard(self, client: TestClient, headers: dict[str, str]) -> str:
        created = make(client, headers, value="ASTM E8 subsize", parent_value="인장")
        return str(created.json()["id"])

    def test_치수를_적는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = self._standard(client, admin_headers)
        updated = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            # **SI 로 보낸다.** 규격서는 mm 로 적혀 있지만 저장은 m 다.
            json={"attributes": {"gauge_length": 0.025}},
            headers=admin_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["attributes"]["gauge_length"] == 0.025

    def test_스키마에_없는_치수는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**오타 하나가 조용히 새 속성이 되면 아무도 못 찾는다.**"""
        term_id = self._standard(client, admin_headers)
        rejected = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"gauge_length": 0.025, "span": 0.05}},
            headers=admin_headers,
        )
        assert rejected.status_code == 422
        assert "span" in rejected.json()["error"]["message"]

    def test_필수_치수가_비면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """게이지 길이 없는 인장 규격은 규격이 아니다."""
        term_id = self._standard(client, admin_headers)
        rejected = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"total_length": 0.2}},
            headers=admin_headers,
        )
        assert rejected.status_code == 422
        assert "게이지 길이" in rejected.json()["error"]["message"]

    def test_규격이_더한_칸에도_적을_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = str(
            make(client, admin_headers, value="ASTM E8 R1", parent_value="인장").json()["id"]
        )
        client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": [extra("diameter", "직경", required=True)]},
            headers=admin_headers,
        )
        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"gauge_length": 0.05, "diameter": 0.0125}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["attributes"]["diameter"] == 0.0125

    def test_속성을_안_쓰는_축에는_속성을_못_넣는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        created = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "포스코", "attributes": {"gauge_length": 0.025}},
            headers=admin_headers,
        )
        assert created.status_code == 422


class TestCategoryFields:
    """분류의 **기본 칸**을 고친다. 그 분류의 규격 전부가 따라 바뀐다."""

    def _save(
        self,
        client: TestClient,
        headers: dict[str, str],
        cat: str,
        fields: list[dict[str, Any]],
    ) -> Any:
        return client.put(
            f"/api/vocabularies/{CATEGORY_SLUG}/terms/{cat}/fields",
            json={"fields": fields},
            headers=headers,
        )

    def test_칸을_더하면_그_분류의_규격에_다_생긴다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        cat = category_id(client, admin_headers, "인장")
        standard = str(
            make(client, admin_headers, value="JIS 5호", parent_value="인장").json()["id"]
        )
        current = [
            extra(item["key"], item["label"], required=item["is_required"])
            for item in fields_of(client, admin_headers, CATEGORY_SLUG, cat)
        ]
        saved = self._save(
            client, admin_headers, cat, [*current, extra("grip_width", "그립부 폭")]
        )
        assert saved.status_code == 200, saved.text
        keys = [item["key"] for item in fields_of(client, admin_headers, SLUG, standard)]
        assert "grip_width" in keys

    def test_뺀_칸의_값은_안_지운다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**화면에서 사라질 뿐이다.** 지워 버리면 되살릴 방법이 없다."""
        cat = category_id(client, admin_headers, "인장")
        standard = str(
            make(client, admin_headers, value="ASTM E8", parent_value="인장").json()["id"]
        )
        client.patch(
            f"/api/vocabularies/{SLUG}/terms/{standard}",
            json={"attributes": {"gauge_length": 0.05, "total_length": 0.2}},
            headers=admin_headers,
        )

        self._save(
            client, admin_headers, cat, [extra("gauge_length", "게이지 길이", required=True)]
        )

        listed = client.get(
            f"/api/vocabularies/{SLUG}/terms?q=ASTM E8", headers=admin_headers
        ).json()
        term = next(item for item in listed["items"] if item["id"] == standard)
        # 값은 그대로 있다 — 칸을 되살리면 다시 보인다.
        assert term["attributes"]["total_length"] == 0.2

    def test_이름이_겹치면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        cat = category_id(client, admin_headers, "인장")
        rejected = self._save(
            client,
            admin_headers,
            cat,
            [
                extra("gauge_length", "게이지 길이", required=True),
                extra("gauge_length", "또 게이지 길이"),
            ],
        )
        assert rejected.status_code == 422
