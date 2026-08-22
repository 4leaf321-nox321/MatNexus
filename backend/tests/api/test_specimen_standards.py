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
    ensure_builtin_axis_fields,
    ensure_builtin_specimen_categories,
    ensure_builtin_vocabularies,
)

SLUG = "specimen_standard"
CATEGORY_SLUG = "specimen_category"


@pytest.fixture
def seeded(db: Session) -> None:
    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
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
        # 판(edition) 은 축이 주므로 늘 있다. 분류가 주는 칸은 없다.
        listed = fields_of(client, admin_headers, SLUG, term_id)
        assert [field["key"] for field in listed] == ["edition"]


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
        assert keys == ["edition", "gauge_length", "total_length"]

    def test_규격이_자기_칸을_더한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**이 파일의 이유.** 환봉 규격에는 직경이 필요하고 평판에는 없다."""
        term_id = self._standard(client, admin_headers, "ASTM E8 R1")
        assert self._add_diameter(client, admin_headers, term_id).status_code == 200

        fields = fields_of(client, admin_headers, SLUG, term_id)
        # 축이 준 판 + 분류가 준 칸 + 이 규격의 칸.
        assert [item["key"] for item in fields] == [
            "edition",
            "gauge_length",
            "total_length",
            "diameter",
        ]
        # 어느 쪽 칸인지 가른다 — 지우려면 갈 곳이 다르다.
        assert [item["inherited"] for item in fields] == [True, True, True, False]

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

    def test_필수라고_표시한_칸이_비면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**필수는 부서가 정한다.** 우리가 기본으로 필수를 박아 두지는 않는다 —
        게이지 길이가 없는 인장 규격이 실제로 여럿이다(D3039 계열은 그립 간
        거리가 곧 게이지다). 다만 필수로 표시한 칸은 비울 수 없어야 한다."""
        term_id = str(
            make(client, admin_headers, value="ASTM E8 R2", parent_value="인장").json()["id"]
        )
        marked = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": [extra("diameter", "직경", required=True)]},
            headers=admin_headers,
        )
        assert marked.status_code == 200, marked.text

        rejected = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"total_length": 0.2}},
            headers=admin_headers,
        )
        assert rejected.status_code == 422
        assert "직경" in rejected.json()["error"]["message"]

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


class TestBaseFieldsAreNotRequired:
    """**"그 분류면 예외 없이 갖는다" 가 생각보다 잘 깨진다.**

    처음에는 인장의 게이지 길이와 DMA 의 자유길이·폭·두께를 필수로 두었다.
    ASTM·ISO 규격표가 그것을 반증했다.

        인장  D3039·D3518·D5766 은 게이지 길이를 시편에 새기지 않는다 —
              그립 간 거리가 곧 게이지다. D1708·D5083·D2290·D412 링도 없다.

        DMA   자유길이·폭·두께 셋을 다 갖는 파트는 ISO 6721-4(인장) 하나뿐이다.
              D4065 는 "specimen size is not fixed by this practice" 라고
              문장으로 못 박는다.

    필수로 두면 그런 규격은 **저장 자체가 안 된다.**
    """

    def test_기본_칸은_필수가_아니다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        listed = fields_of(
            client,
            admin_headers,
            CATEGORY_SLUG,
            category_id(client, admin_headers, "인장"),
        )
        assert [field["key"] for field in listed if field["is_required"]] == []

    def test_게이지_길이_없는_인장_규격을_저장한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """D3039 — 그립 간 거리가 곧 게이지라 표점을 안 새긴다."""
        created = make(client, admin_headers, value="ASTM D3039", parent_value="인장")
        assert created.status_code == 201, created.text

        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{created.json()['id']}",
            json={
                "extra_fields": [
                    {
                        "key": "grip_separation",
                        "label": "그립 간 거리",
                        "dimension": "length",
                        "si_unit": "m",
                        "is_required": False,
                        "help": None,
                    }
                ],
                "attributes": {"grip_separation": 0.138},
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["attributes"]["grip_separation"] == 0.138

    def test_치수를_아예_안_주는_DMA_규격도_저장한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """ASTM D5418 은 매트릭스가 전 항목 "없음" 이다 — 장비 클램프에 위임한다."""
        created = make(client, admin_headers, value="ASTM D5418", parent_value="DMA")
        assert created.status_code == 201, created.text

        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{created.json()['id']}",
            json={"attributes": {}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text


class TestRoles:
    """**기본 칸을 선언하는 쪽인지는 축이 정한다.**

    화면이 그것을 값의 상태로 가늠했다 — 상위 값이 비어 있으면 분류로 봤다.
    그런데 **분류를 아직 안 정한 규격**이 있다. 그런 규격에 칸을 만들면 규격의
    칸이 아니라 분류 기본 칸 표로 들어갔고, 들어간 뒤에는 손댈 길이 없었다 —
    규격 화면은 자기 칸으로 안 보고 분류 화면에는 그 값이 안 뜬다.
    """

    def test_규격에는_기본_칸을_못_만든다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = str(make(client, admin_headers, value="분류 없는 규격").json()["id"])
        refused = client.put(
            f"/api/vocabularies/{SLUG}/terms/{term_id}/fields",
            json={"fields": [{"key": "aaa", "label": "111"}]},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-VOCABULARY-0025"

    def test_분류에는_만들_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        saved = client.put(
            f"/api/vocabularies/{CATEGORY_SLUG}/terms/"
            f"{category_id(client, admin_headers, '인장')}/fields",
            json={"fields": [{"key": "gauge_length", "label": "게이지 길이"}]},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text


class TestDimensions:
    """**길이만 다루던 시절이 끝났다.**

    D3039 의 탭 베벨각은 7° 또는 90°(각도), D5766 의 w/d 는 비율(무차원),
    C1557·D897 은 단면적을 직접 준다(면적).
    """

    def _standard(self, client: TestClient, headers: dict[str, str]) -> str:
        created = make(client, headers, value="ASTM D3039 0deg", parent_value="인장")
        assert created.status_code == 201, created.text
        return str(created.json()["id"])

    def test_각도_칸을_만든다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = self._standard(client, admin_headers)
        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "extra_fields": [
                    {
                        "key": "tab_bevel",
                        "label": "탭 베벨각",
                        "dimension": "angle",
                        "si_unit": "rad",
                        "is_required": False,
                        "help": None,
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        listed = fields_of(client, admin_headers, SLUG, term_id)
        bevel = next(field for field in listed if field["key"] == "tab_bevel")
        assert bevel["dimension"] == "angle" and bevel["si_unit"] == "rad"

    def test_차원과_저장_단위가_어긋나면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**단면적 칸을 길이로 만들면 10의 6제곱 배 틀린다** — 조용히."""
        term_id = self._standard(client, admin_headers)
        refused = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "extra_fields": [
                    {
                        "key": "section_area",
                        "label": "단면적",
                        "dimension": "area",
                        "si_unit": "m",
                        "is_required": False,
                        "help": None,
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-VOCABULARY-0022"

    def test_칸을_지워도_다음_저장이_막히지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**뺀 칸의 값은 남긴다**(칸을 되살리면 다시 보인다). 그런데 그 값이
        스키마 밖이라고 다음 저장을 422 로 막으면, 칸을 지운 사람이 그 규격에
        아무것도 못 하게 된다."""
        term_id = self._standard(client, admin_headers)
        client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": [extra("diameter", "직경")]},
            headers=admin_headers,
        )
        client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"diameter": 0.0125}},
            headers=admin_headers,
        )

        dropped = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": []},
            headers=admin_headers,
        )
        assert dropped.status_code == 200, dropped.text

        # 칸이 없어진 뒤에도 값을 고칠 수 있어야 한다.
        again = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"gauge_length": 0.05, "diameter": 0.0125}},
            headers=admin_headers,
        )
        assert again.status_code == 200, again.text
        # 값은 남아 있다 — 칸을 되살리면 다시 보인다.
        assert again.json()["attributes"]["diameter"] == 0.0125

    def test_스키마_밖의_새_값은_여전히_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """남겨 두는 것은 **이미 있던 값**뿐이다. 오타는 그대로 막는다."""
        term_id = self._standard(client, admin_headers)
        refused = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"gauge_length": 0.05, "gage_length": 0.05}},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert "gage_length" in refused.json()["error"]["message"]

    def test_단위표에_있는_차원은_다_쓸_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**좁힐 근거가 없었다.** 시편에 붙는 값이 길이·면적·각도로 끝난다는
        보장이 없다 — ISO 6721-10 은 시료를 3~5 g 으로 준다."""
        term_id = self._standard(client, admin_headers)
        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "extra_fields": [
                    {
                        "key": "charge",
                        "label": "시료량",
                        "dimension": "mass",
                        "si_unit": "kg",
                        "is_required": False,
                        "help": None,
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text

    def test_모르는_차원은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """오타가 조용히 새 차원이 되면 저장 단위 검사가 통째로 헐거워진다."""
        term_id = self._standard(client, admin_headers)
        refused = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "extra_fields": [
                    {
                        "key": "sweep",
                        "label": "길이",
                        "dimension": "lenght",
                        "si_unit": "m",
                        "is_required": False,
                        "help": None,
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-VOCABULARY-0021"


class TestKinds:
    """**규격은 치수만 갖지 않는다.**

    판(문자)·모드(선택)·단부 형식(선택)이 있고, 숫자 칸만 두면 그것들이 값
    이름에 섞여 `D638 Type I` 과 `D638-22 Type I` 이 별개 값으로 갈린다 —
    애초에 풀려던 병이 되돌아온다.
    """

    def test_판은_축이_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**분류마다 적으면 새 분류에서 빠뜨린다.** 판은 모든 규격이 갖는다."""
        term_id = str(make(client, admin_headers, value="분류 없는 규격").json()["id"])
        listed = fields_of(client, admin_headers, SLUG, term_id)
        edition = next(field for field in listed if field["key"] == "edition")
        assert edition["kind"] == "text" and edition["inherited"] is True

    def test_판을_문자로_적는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """`D638-22` 는 숫자가 아니다 — 숫자 규칙을 대면 거절된다."""
        term_id = str(make(client, admin_headers, value="ASTM D638").json()["id"])
        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"edition": "D638-22"}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["attributes"]["edition"] == "D638-22"

    def test_모드는_DMA_분류가_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**모드가 곧 시편 형상이다.** DMA 규격은 대개 치수를 안 정한다."""
        term_id = str(
            make(client, admin_headers, value="ASTM D5418", parent_value="DMA").json()["id"]
        )
        listed = fields_of(client, admin_headers, SLUG, term_id)
        mode = next(field for field in listed if field["key"] == "mode")
        assert mode["kind"] == "choice"
        assert "이중 캔틸레버" in mode["choices"]

        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"mode": "이중 캔틸레버"}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text

    def test_목록에_없는_선택은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = str(
            make(client, admin_headers, value="ASTM D5023", parent_value="DMA").json()["id"]
        )
        refused = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"attributes": {"mode": "삼점굽힘"}},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text

    def test_단부_형식은_그_규격만의_선택_칸이다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """E8 환봉만 갖는다 — 분류에 두면 평판 규격에도 빈 칸이 생긴다."""
        term_id = str(
            make(client, admin_headers, value="ASTM E8 R1", parent_value="인장").json()["id"]
        )
        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "extra_fields": [
                    {
                        "key": "grip_end",
                        "label": "단부 형식",
                        "kind": "choice",
                        "choices": ["나사", "숄더", "평행", "버튼헤드"],
                    }
                ],
                "attributes": {"grip_end": "숄더"},
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["attributes"]["grip_end"] == "숄더"

    def test_선택_칸에_고를_값이_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """빈 목록은 아무것도 못 고르게 한다 — 그럴 거면 문자 칸이다."""
        term_id = self._standard(client, admin_headers)
        refused = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"extra_fields": [{"key": "grip_end", "label": "단부", "kind": "choice"}]},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-VOCABULARY-0024"

    def _standard(self, client: TestClient, headers: dict[str, str]) -> str:
        created = make(client, headers, value="ASTM E8 sub2", parent_value="인장")
        assert created.status_code == 201, created.text
        return str(created.json()["id"])


class TestSymbols:
    """**규격서와 도면은 뜻이 아니라 글자로 적혀 있다.**

    같은 글자가 규격마다 다른 뜻이다 — E8 의 `D` 는 직경, D638 의 `D` 는 그립 간
    거리다. 그래서 키는 뜻으로 짓고 글자는 따로 담는다.
    """

    def test_규격이_자기_글자로_덮어쓴다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """게이지 길이는 **분류**가 선언한 칸인데 글자는 규격마다 다르다 —
        E8·D638 은 `G`, ISO 527-2 는 `L₀`."""
        term_id = str(
            make(client, admin_headers, value="ISO 527-2", parent_value="인장").json()["id"]
        )
        saved = client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={"field_symbols": {"gauge_length": "L0"}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text

        listed = fields_of(client, admin_headers, SLUG, term_id)
        gauge = next(field for field in listed if field["key"] == "gauge_length")
        assert gauge["symbol"] == "L0"

    def test_안_덮으면_칸이_가진_글자다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        term_id = str(
            make(client, admin_headers, value="ASTM E8 R3", parent_value="인장").json()["id"]
        )
        client.patch(
            f"/api/vocabularies/{SLUG}/terms/{term_id}",
            json={
                "extra_fields": [
                    {"key": "diameter", "label": "직경", "symbol": "D"},
                ]
            },
            headers=admin_headers,
        )
        listed = fields_of(client, admin_headers, SLUG, term_id)
        assert next(f for f in listed if f["key"] == "diameter")["symbol"] == "D"


class TestCatalog:
    """표준 규격 가져오기 — **칸과 기호는 심고, 치수 값은 안 심는다.**

    근거 문서가 2차 출처라(본문이 유료다) 숫자를 심으면 검증 안 된 값이 시스템의
    정본이 된다 — 실제로 출처끼리 어긋난 곳이 있다(D5766 전체 길이가 152 mm 와
    250 mm 로). 칸과 기호는 판이 바뀌어도 그대로다.
    """

    def _catalog(self, client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
        found = client.get("/api/vocabularies/specimen-standards/catalog", headers=headers)
        assert found.status_code == 200, found.text
        return {item["key"]: item for item in found.json()}

    def test_치수_값은_안_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**이 카탈로그가 주는 것은 구조지 숫자가 아니다.**"""
        catalog = self._catalog(client, admin_headers)
        assert "attributes" not in catalog["astm_e8_sheet"]

    def test_기호를_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**같은 글자가 규격마다 다른 뜻이다.** E8 의 D 는 직경, D638 의 D 는
        그립 간 거리다. 그리고 장비 파일의 항목 이름이 곧 그 글자다."""
        catalog = self._catalog(client, admin_headers)
        e8 = {item["key"]: item for item in catalog["astm_e8_round"]["fields"]}
        d638 = {item["key"]: item for item in catalog["astm_d638_type1"]["fields"]}
        assert e8["diameter"]["symbol"] == "D"
        assert d638["grip_separation"]["symbol"] == "D"
        assert "diameter" not in d638

    def test_가져오면_칸과_단면적_식이_함께_온다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        made = client.post(
            "/api/vocabularies/specimen-standards/import",
            json={"keys": ["astm_e8_round"]},
            headers=admin_headers,
        )
        assert made.status_code == 200, made.text
        (term,) = made.json()
        assert term["parent_value"] == "인장"
        assert term["cross_section"] == "circle"
        assert term["attributes"] == {}

        listed = fields_of(client, admin_headers, SLUG, term["id"])
        keys = {item["key"] for item in listed}
        # 축이 준 판 + 분류가 준 게이지 길이 + 이 규격의 칸.
        assert {"edition", "gauge_length", "diameter", "grip_end"} <= keys

    def test_비율_조건도_함께_온다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """DMA 는 숫자를 안 주고 비만 주는 파트가 대부분이다."""
        made = client.post(
            "/api/vocabularies/specimen-standards/import",
            json={"keys": ["iso_6721_3"]},
            headers=admin_headers,
        )
        assert made.status_code == 200, made.text
        (term,) = made.json()
        (check,) = term["ratio_checks"]
        assert check["numerator"] == "length" and check["minimum"] == 50

    def test_이미_있는_이름은_건너뛴다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**덮어쓰면 사람이 넣어 둔 치수가 사라진다.**"""
        client.post(
            "/api/vocabularies/specimen-standards/import",
            json={"keys": ["astm_e8_sheet"]},
            headers=admin_headers,
        )
        again = client.post(
            "/api/vocabularies/specimen-standards/import",
            json={"keys": ["astm_e8_sheet"]},
            headers=admin_headers,
        )
        assert again.status_code == 200, again.text
        assert again.json() == []

        catalog = self._catalog(client, admin_headers)
        assert catalog["astm_e8_sheet"]["taken"] is True
