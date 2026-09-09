"""감사 기록이 **어느 길로 들어왔는지** 남긴다 — 사람인가 AI 인가.

MCP 서버는 진작부터 `X-Client: mcp` 를 보내고 있었는데 백엔드가 안 읽었다. 쓰기
도구가 둘뿐일 때는 티가 안 났지만, 처리 실행까지 열면 감사 로그에서 **「이 결과
누가 돌렸지」 를 못 답한다.**

무는 것 넷:

    헤더를 남긴다              MCP 로 들어온 변경에 `mcp` 가 붙는다
    화면에서 한 것은 빈 값이다  기본이 사람이다
    모르는 이름은 버린다        감사 열이 아무 글자나 담으면 그 열로는 못 센다
    걸러 볼 수 있다            「AI 가 한 것만」 이 물음이 되어야 한다
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _material(client: TestClient, headers: dict[str, str]) -> str:
    made = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": f"AUD-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _delete(client: TestClient, headers: dict[str, str], material_id: str) -> None:
    """감사에 남는 일 하나 — 삭제는 되돌리기 어려운 축이라 기록된다."""
    dropped = client.delete(f"/api/materials/{material_id}", headers=headers)
    assert dropped.status_code in (200, 204), dropped.text


class TestClientMark:
    def test_MCP_로_들어오면_그렇게_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material_id = _material(client, admin_headers)
        _delete(client, {**admin_headers, "X-Client": "mcp"}, material_id)

        entries = client.get(
            "/api/audit", params={"target_id": material_id}, headers=admin_headers
        ).json()
        assert entries, "삭제가 감사에 안 남았다"
        assert entries[0]["client"] == "mcp"

    def test_화면에서_한_것은_빈_값이다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**기본이 사람이다.** 표시가 붙는 쪽이 예외여야 한다."""
        material_id = _material(client, admin_headers)
        _delete(client, admin_headers, material_id)

        entries = client.get(
            "/api/audit", params={"target_id": material_id}, headers=admin_headers
        ).json()
        assert entries[0]["client"] == ""

    def test_모르는_이름은_버린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """아무 글자나 담기면 그 열로는 아무것도 셀 수 없다.

        한글은 아예 못 보낸다(HTTP 헤더는 latin-1) — 그러니 막을 것은 「아는 것처럼
        생겼는데 우리가 모르는 이름」 이다.
        """
        material_id = _material(client, admin_headers)
        _delete(client, {**admin_headers, "X-Client": "some-other-tool"}, material_id)

        entries = client.get(
            "/api/audit", params={"target_id": material_id}, headers=admin_headers
        ).json()
        assert entries[0]["client"] == ""

    def test_AI_가_한_것만_걸러_본다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**이것이 이 열을 두는 이유다** — 물음이 되어야 한다."""
        by_ai = _material(client, admin_headers)
        by_hand = _material(client, admin_headers)
        _delete(client, {**admin_headers, "X-Client": "mcp"}, by_ai)
        _delete(client, admin_headers, by_hand)

        only_ai = client.get(
            "/api/audit", params={"client": "mcp", "limit": 200}, headers=admin_headers
        ).json()
        found = {one["target_id"] for one in only_ai}
        assert by_ai in found
        assert by_hand not in found

        only_web = client.get(
            "/api/audit", params={"client": "web", "limit": 200}, headers=admin_headers
        ).json()
        assert by_hand in {one["target_id"] for one in only_web}


class TestValueChange:
    """**값을 고친 것도 남는다 — 사람이 아닐 때만.**

    실측(2026-09-10)으로 드러난 구멍이다. 진짜 AI 세션에 「문헌값을 사내 재료에
    담아 달라」 고 했더니 9건을 담았는데, **감사에 아무것도 안 남았다.** 값 수정은
    원래 감사 대상이 아니어서다(`shared/audit.py`: 되돌릴 수 없거나 권한이 실린
    것만 — 값마다 남기면 정작 찾을 것을 못 찾는다).

    그 규칙은 그대로 둔다. 화면에서 사람이 고친 것은 지금도 안 남는다. **사람이
    아닌 길로 들어온 것만** 예외다 — 반년 뒤에 물어질 질문이 「이 값 어디서
    났나」(값 자체에 출처가 붙는다)가 아니라 **「이거 사람이 확인한 거 맞나」**
    이기 때문이다.
    """

    def test_AI_가_값을_고치면_남는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material_id = _material(client, admin_headers)
        changed = client.patch(
            f"/api/materials/{material_id}",
            json={"alias": "AI 가 고침"},
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert changed.status_code == 200, changed.text

        entries = client.get(
            "/api/audit", params={"target_id": material_id}, headers=admin_headers
        ).json()
        mine = [one for one in entries if one["action"] == "values.changed_by_client"]
        assert mine, "AI 가 값을 고쳤는데 감사에 안 남았다"
        assert mine[0]["client"] == "mcp"
        assert "alias" in mine[0]["changes"]["fields"]

    def test_사람이_고친_것은_안_남는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**규칙을 안 뒤집는다.** 값마다 남기면 감사 로그가 못 쓰게 된다."""
        material_id = _material(client, admin_headers)
        changed = client.patch(
            f"/api/materials/{material_id}",
            json={"alias": "사람이 고침"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text

        entries = client.get(
            "/api/audit", params={"target_id": material_id}, headers=admin_headers
        ).json()
        assert not [one for one in entries if one["action"] == "values.changed_by_client"]
