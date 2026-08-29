"""수집 체계 소프트 삭제 — **지운 것이 이름을 붙들지 않는가.**

무는 자리를 「지워진다」 가 아니라 셋에 둔다:

  1. 목록에서 빠지는가 (안 빠지면 지운 정의가 업로드 폼에 그대로 뜬다)
  2. **같은 key 로 다시 만들 수 있는가** — 재료가 여기서 터졌다(2026-08-28 이관
     사고). 그냥 유니크면 지운 행이 key 를 붙드는데 화면 어디에도 그것이 없어,
     빠져나갈 길이 아예 없었다. 부분 인덱스로 풀었고 여기서 그것을 못으로 박는다.
  3. 되살릴 때 자리가 차 있으면 **사람이 읽을 말**로 막는가 — 안 막으면 DB 가
     막고 500 이 되며, 화면은 "서버 오류" 만 적는다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

TYPE: dict[str, Any] = {
    "key": "peel",
    "label": "박리",
    "abbr": "PL",
    "channels": [
        {"key": "force", "label": "하중", "dimension": "force", "si_unit": "N"},
        {"key": "stroke", "label": "변위", "dimension": "length", "si_unit": "m"},
    ],
}


def _make(client: TestClient, headers: dict[str, str], key: str = "peel") -> None:
    made = client.post("/api/test-types", json={**TYPE, "key": key}, headers=headers)
    assert made.status_code == 201, made.text


def _keys(client: TestClient, headers: dict[str, str]) -> list[str]:
    got = client.get("/api/test-types?include_inactive=true", headers=headers)
    return [one["key"] for one in got.json()]


class Test시험_정의:
    def test_지우면_목록에서_빠진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _make(client, admin_headers)
        assert "peel" in _keys(client, admin_headers)
        assert client.delete("/api/test-types/peel", headers=admin_headers).status_code == 204
        assert "peel" not in _keys(client, admin_headers)

    def test_지운_key_로_다시_만들_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**여기가 재료에서 터진 자리다.** 소프트 삭제인데 유니크가 지운 행까지
        세면, 같은 key 로 다시 만들 수 없으면서 화면 어디에도 그것이 없다."""
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        again = client.post("/api/test-types", json=TYPE, headers=admin_headers)
        assert again.status_code == 201, again.text

    def test_휴지통에_이름과_함께_뜬다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # 「무엇을 지웠나」 에 key 가 아니라 사람이 읽는 이름으로 답해야 한다.
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        rows = client.get("/api/trash?kind=test_type", headers=admin_headers).json()
        assert [(one["kind_label"], one["name"]) for one in rows] == [("시험 정의", "박리")]

    def test_되살리면_목록으로_돌아온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        item = client.get("/api/trash?kind=test_type", headers=admin_headers).json()[0]
        back = client.post(f"/api/trash/test_type/{item['id']}/restore", headers=admin_headers)
        assert back.status_code == 200, back.text
        assert "peel" in _keys(client, admin_headers)

    def test_자리가_차_있으면_사람이_읽을_말로_막는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**DB 에 맡기면 500 이다.** 부분 인덱스가 막긴 하는데, 그때 화면에
        뜨는 것은 "서버 오류가 발생했습니다" 라 무엇이 걸렸는지 알 수 없다."""
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        item = client.get("/api/trash?kind=test_type", headers=admin_headers).json()[0]
        _make(client, admin_headers)  # 같은 key 를 살아 있는 것이 다시 차지한다

        blocked = client.post(
            f"/api/trash/test_type/{item['id']}/restore", headers=admin_headers
        )
        assert blocked.status_code == 409, blocked.text
        # **무엇이 걸렸는지 이름으로 말한다.** key 만 주면 사람은 그것이 어느
        # 정의인지 목록에서 다시 찾아야 한다.
        assert "박리" in blocked.json()["error"]["message"]

    def test_되살릴_수_없다는_것을_목록에서_미리_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # 눌러 보고 알게 하지 않는다 — 목록이 이미 이유를 들고 있다.
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        _make(client, admin_headers)
        row = client.get("/api/trash?kind=test_type", headers=admin_headers).json()[0]
        assert row["blocked"]

    def test_영영_지우면_행이_사라진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        item = client.get("/api/trash?kind=test_type", headers=admin_headers).json()[0]
        gone = client.delete(
            f"/api/trash/test_type/{item['id']}?confirm=true", headers=admin_headers
        )
        assert gone.status_code == 200, gone.text
        assert client.get("/api/trash?kind=test_type", headers=admin_headers).json() == []


class Test섞이지_않는다:
    def test_종류를_안_주면_한_표에_모아_낸다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """재료 계층과 수집 체계가 한 목록에 선다. **사람은 「무엇을 지웠나」 를
        종류별로 묻지 않는다** — 그것이 휴지통을 하나로 둔 이유다."""
        _make(client, admin_headers)
        client.delete("/api/test-types/peel", headers=admin_headers)
        rows = client.get("/api/trash", headers=admin_headers).json()
        assert any(one["kind"] == "test_type" for one in rows)

    def test_모르는_종류는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # 오타를 조용히 「전부」 로 읽으면, 거른 줄 알고 본 목록이 전부다.
        got = client.get("/api/trash?kind=connectors", headers=admin_headers)
        assert got.status_code == 422, got.text


PROFILE: dict[str, Any] = {
    "key": "acme_csv",
    "label": "ACME CSV",
    "test_type_key": "peel",
    "definition": {
        # **지문이 있어야 한다.** 없으면 모든 파일에 맞아 다른 장비 것까지 읽는다.
        "match": {"extensions": [".csv"], "header_any": ["Force"]},
        "columns": {"Force": {"channel": "force"}},
    },
    "priority": 10,
}

RECIPE: dict[str, Any] = {
    "key": "smooth5",
    "label": "5점 평활",
    "test_type_key": "peel",
    "steps": [
        {"plugin": "curve.sort_unique", "options": {"x": "force", "duplicate_policy": "mean"}}
    ],
}


@pytest.fixture
def peel(client: TestClient, admin_headers: dict[str, str]) -> None:
    """프로파일과 레시피가 가리킬 시험 정의."""
    _make(client, admin_headers)


class Test인풋_파일_정의:
    """**시험 정의와 같은 규칙, 같은 코드다.** 그러니 무는 자리도 같아야 한다 —
    한쪽만 고치면 다른 쪽이 옛 동작으로 남고, 그 차이는 지워 보기 전까지 안 드러난다."""

    def test_지우면_빠지고_같은_key_로_다시_만들_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], peel: None
    ) -> None:
        made = client.post("/api/formats", json=PROFILE, headers=admin_headers)
        assert made.status_code == 201, made.text
        assert client.delete("/api/formats/acme_csv", headers=admin_headers).status_code == 204

        listed = client.get("/api/formats", headers=admin_headers).json()
        assert "acme_csv" not in [one["key"] for one in listed]

        again = client.post("/api/formats", json=PROFILE, headers=admin_headers)
        assert again.status_code == 201, again.text

    def test_휴지통에서_되살아난다(
        self, client: TestClient, admin_headers: dict[str, str], peel: None
    ) -> None:
        client.post("/api/formats", json=PROFILE, headers=admin_headers)
        client.delete("/api/formats/acme_csv", headers=admin_headers)
        item = client.get("/api/trash?kind=format_profile", headers=admin_headers).json()[0]
        assert item["kind_label"] == "인풋 파일 정의"
        back = client.post(
            f"/api/trash/format_profile/{item['id']}/restore", headers=admin_headers
        )
        assert back.status_code == 200, back.text
        listed = client.get("/api/formats", headers=admin_headers).json()
        assert "acme_csv" in [one["key"] for one in listed]


class Test레시피:
    def test_지우면_빠지고_같은_key_로_다시_만들_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], peel: None
    ) -> None:
        made = client.post("/api/processing/recipes", json=RECIPE, headers=admin_headers)
        assert made.status_code == 201, made.text
        gone = client.delete("/api/processing/recipes/smooth5", headers=admin_headers)
        assert gone.status_code == 204, gone.text

        listed = client.get("/api/processing/recipes", headers=admin_headers).json()
        assert "smooth5" not in [one["key"] for one in listed]

        again = client.post("/api/processing/recipes", json=RECIPE, headers=admin_headers)
        assert again.status_code == 201, again.text

    def test_휴지통에서_되살아난다(
        self, client: TestClient, admin_headers: dict[str, str], peel: None
    ) -> None:
        client.post("/api/processing/recipes", json=RECIPE, headers=admin_headers)
        client.delete("/api/processing/recipes/smooth5", headers=admin_headers)
        item = client.get("/api/trash?kind=recipe", headers=admin_headers).json()[0]
        assert item["kind_label"] == "레시피"
        back = client.post(f"/api/trash/recipe/{item['id']}/restore", headers=admin_headers)
        assert back.status_code == 200, back.text
        listed = client.get("/api/processing/recipes", headers=admin_headers).json()
        assert "smooth5" in [one["key"] for one in listed]
