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
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.materials.models import Material
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

#: 시편 치수를 숫자로 직접 준다 — 이 파일이 보는 것은 계산이 아니라 **남았는가** 다.
STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "tensile.strength", "options": {}},
]


def _actions(client: TestClient, headers: dict[str, str], action: str) -> list[dict[str, Any]]:
    got: list[dict[str, Any]] = client.get(
        "/api/audit", params={"action": action, "limit": 200}, headers=headers
    ).json()
    return got


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


class Test쓰는_길마다_남는다:
    """**값 수정 하나만 막아 둔 것이 구멍이었다**(2026-09-18).

    `VALUES_CHANGED_BY_CLIENT` 를 넣을 때 답하려던 질문은 「이거 사람이 확인한 거
    맞나」 였는데, 정작 AI 가 더 많이 하는 일 — 물성 카드 만들기·처리 실행·레시피와
    형식 저장 — 은 그대로 빠져나갔다. 한 군데라도 새면 그 표로 센 숫자는 모자란
    것이 아니라 **틀린 것**이 된다: 「AI 는 아무것도 안 했다」 로 읽힌다.

    네 길 모두 같은 규칙이다 — **사람이 화면에서 한 것은 안 남는다.**
    """

    def test_AI_가_만든_물성_카드가_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """카드는 되돌릴 수 있다. 그래도 남기는 이유는 **덱이 해석에 들어간 뒤**에
        「이 카드 사람이 만든 거 맞나」 가 물어지기 때문이다."""
        material = Material(
            record_name=f"AUD_CARD_{uuid.uuid4().hex[:6]}",
            family="Metal",
            category="Steel",
            grade="AUD",
            poisson_ratio=0.3,
            density_si=7850.0,
            declared_properties=[
                {
                    "item": "탄성계수",
                    "points": [{"temperature_k": None, "value_si": 200e9}],
                    "input_unit": "GPa",
                    "source": "literature",
                    "reference": "핸드북",
                }
            ],
        )
        db.add(material)
        db.commit()

        made = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": str(material.id), "label": "AI 가 만든 카드"},
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert made.status_code == 201, made.text

        mine = [
            one
            for one in _actions(client, admin_headers, "card.created_by_client")
            if one["target_id"] == made.json()["id"]
        ]
        assert mine, "AI 가 카드를 만들었는데 감사에 안 남았다"
        assert mine[0]["client"] == "mcp"
        assert mine[0]["target_label"] == "AI 가 만든 카드"

    def test_사람이_만든_카드는_안_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = Material(
            record_name=f"AUD_HAND_{uuid.uuid4().hex[:6]}",
            family="Metal",
            category="Steel",
            grade="AUD",
            poisson_ratio=0.3,
            density_si=7850.0,
            declared_properties=[
                {
                    "item": "탄성계수",
                    "points": [{"temperature_k": None, "value_si": 200e9}],
                    "input_unit": "GPa",
                    "source": "literature",
                    "reference": "핸드북",
                }
            ],
        )
        db.add(material)
        db.commit()

        made = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": str(material.id), "label": "사람이 만든 카드"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        assert not [
            one
            for one in _actions(client, admin_headers, "card.created_by_client")
            if one["target_id"] == made.json()["id"]
        ]

    def test_AI_가_저장한_레시피가_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """레시피는 **앞으로 돌아갈 모든 처리**가 따르는 단계 구성이다. 과거의
        결과는 스냅샷이 지켜 주지만 앞으로의 것은 아무도 안 지킨다."""
        ensure_builtin_test_types(db)
        db.commit()
        key = f"aud_{uuid.uuid4().hex[:6]}"
        made = client.post(
            "/api/processing/recipes",
            json={
                "key": key,
                "label": "AI 가 만든 레시피",
                "test_type_key": "tensile",
                "steps": STEPS,
            },
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert made.status_code == 201, made.text

        mine = [
            one
            for one in _actions(client, admin_headers, "recipe.saved_by_client")
            if one["target_id"] == made.json()["id"]
        ]
        assert mine and mine[0]["changes"]["created"] is True

        fixed = client.put(
            f"/api/processing/recipes/{key}",
            json={
                "label": "AI 가 고친 레시피",
                "test_type_key": "tensile",
                "steps": STEPS,
                "expected_revision": made.json()["revision"],
            },
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert fixed.status_code == 200, fixed.text
        again = [
            one
            for one in _actions(client, admin_headers, "recipe.saved_by_client")
            if one["target_id"] == made.json()["id"]
        ]
        assert len(again) == 2, "고친 것도 남아야 한다 — 단계를 통째로 갈아 끼운다"
        assert again[0]["changes"]["created"] is False

    def test_AI_가_저장한_형식이_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """형식이 틀리면 값이 **안 들어오는 게 아니라 다른 값이 들어온다.**"""
        ensure_builtin_test_types(db)
        db.commit()
        key = f"aud_{uuid.uuid4().hex[:6]}"
        made = client.post(
            "/api/formats",
            json={
                "key": key,
                "label": "AI 가 만든 형식",
                "test_type_key": "tensile",
                "definition": {
                    "match": {"extensions": [".csv"]},
                    "columns": {"Force": {"channel": "force"}},
                },
            },
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert made.status_code == 201, made.text

        mine = _actions(client, admin_headers, "format.saved_by_client")
        assert mine, "AI 가 형식을 저장했는데 감사에 안 남았다"
        assert mine[0]["target_label"].endswith(f"({key})")
        assert mine[0]["client"] == "mcp"

    def test_사람이_저장한_형식은_안_남는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        ensure_builtin_test_types(db)
        db.commit()
        made = client.post(
            "/api/formats",
            json={
                "key": f"aud_{uuid.uuid4().hex[:6]}",
                "label": "사람이 만든 형식",
                "test_type_key": "tensile",
                "definition": {
                    "match": {"extensions": [".csv"]},
                    "columns": {"Force": {"channel": "force"}},
                },
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        assert not _actions(client, admin_headers, "format.saved_by_client")


@pytest.fixture
def run_id(client: TestClient, admin_headers: dict[str, str], db: Session) -> str:
    """파싱까지 끝난 인장 시험 하나."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "AUDP",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
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
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


class Test처리_실행:
    """「이 결과 누가 돌렸지」 — `request_context` 가 이 말을 적어 둔 그 질문이다.

    결과 자체는 단계·버전·실행 환경을 통째로 들고 있어 **무엇으로** 나왔는지는
    안다. 빠진 것은 **길** 하나였다: 같은 토큰으로 AI 가 돌린 것과 사람이 돌린
    것이 구별되지 않았다.
    """

    def test_AI_가_돌린_처리가_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert stored.status_code == 201, stored.text

        mine = [
            one
            for one in _actions(client, admin_headers, "processing.run_by_client")
            if one["target_id"] == stored.json()["id"]
        ]
        assert mine and mine[0]["client"] == "mcp"

    def test_사람이_돌린_처리는_안_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        )
        assert stored.status_code == 201, stored.text
        assert not _actions(client, admin_headers, "processing.run_by_client")

    def test_배치는_한_줄로_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        """**건별로 남기면 한 번 돌린 것이 표 50줄이 된다.** 그러면 이 표에서
        정작 찾을 것(계정·삭제)을 못 찾는다 — 그것이 이 표의 원래 규칙이다."""
        done = client.post(
            "/api/processing/batch",
            json={"test_run_ids": [run_id], "steps": STEPS, "adopt": False},
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert done.status_code == 200, done.text
        assert done.json()["succeeded"] == 1

        mine = _actions(client, admin_headers, "processing.run_by_client")
        assert len(mine) == 1, "배치 한 번은 감사 한 줄이다"
        assert mine[0]["changes"]["succeeded"] == 1
        assert mine[0]["target_id"] is None

    def test_돌려_보기만_한_배치는_안_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        """`dry_run` 은 아무것도 저장하지 않는다 — 남길 일이 없다."""
        done = client.post(
            "/api/processing/batch",
            json={"test_run_ids": [run_id], "steps": STEPS, "dry_run": True},
            headers={**admin_headers, "X-Client": "mcp"},
        )
        assert done.status_code == 200, done.text
        assert not _actions(client, admin_headers, "processing.run_by_client")
