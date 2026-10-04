"""채택 검토대 — 여러 시험의 결과를 **한 번에 읽고, 견주고, 건별로 채택한다**(ADR 0058).

채택은 「이 시험의 물성은 이것」 이라는 선언이라 통계 · 카드 · 덱이 그것을 읽는다. 여럿을
한 번에 바꾸는 길이 생기면 한 건씩 바꾸던 규칙이 느슨해지기 쉽다 — 그래서 여기서 무는 것은
그 규칙들이다.

    한 번에 읽는다               시험 스무 건을 스무 번 부르지 않는다 · 차례를 지킨다
    고칠 수 있는 사람만          남의 부서 시험은 막히고, 막힌 까닭이 그 줄에 온다
    그 시험의 결과만             남의 시험 결과를 채택하는 뒷문이 되면 안 된다
    요약값 표가 따라온다          채택이 바뀌면 통계가 읽는 값도 바뀐다
    되돌린다                     `null` 이면 채택 전으로 — 결과는 안 지운다
    하나가 막혀도 나머지는 된다   건별로 커밋하고 건별로 말한다
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry
from app.modules.processing.schemas import OVERVIEW_MAX
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestSummary

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
]


@pytest.fixture
def runs(client: TestClient, admin_headers: dict[str, str], db: Session) -> list[str]:
    """같은 재료의 인장 시험 셋 — 읽힌 채로, 아직 처리 전."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "BOARD",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    ids: list[str] = []
    for _ in range(3):
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
        ids.append(str(created["id"]))
    return ids


def _process(client: TestClient, headers: dict[str, str], run_ids: list[str]) -> list[str]:
    """결과만 쌓는다(채택하지 않는다) — 만든 결과 id 를 차례대로."""
    got = client.post(
        "/api/processing/batch",
        json={"test_run_ids": run_ids, "steps": STEPS, "adopt": False},
        headers=headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["failed"] == 0
    return [str(one["result_id"]) for one in got.json()["items"]]


def _adopt(client: TestClient, headers: dict[str, str], items: list[dict[str, Any]]) -> Any:
    got = client.post("/api/processing/adopt-many", json={"items": items}, headers=headers)
    assert got.status_code == 200, got.text
    return got.json()


def _adopted(client: TestClient, headers: dict[str, str], run_id: str) -> str | None:
    detail = client.get(f"/api/test-runs/{run_id}", headers=headers).json()
    return detail["adopted_result_id"]  # type: ignore[no-any-return]


def _summaries(db: Session, run_id: str) -> int:
    db.expire_all()
    return len(
        db.scalars(
            select(TestSummary).where(
                TestSummary.test_run_id == uuid.UUID(run_id), TestSummary.source == "matnexus"
            )
        ).all()
    )


class Test한_번에_읽는다:
    def test_요청_차례대로_결과와_권한이_온다(
        self, client: TestClient, admin_headers: dict[str, str], runs: list[str]
    ) -> None:
        """**못 보는 시험도 줄을 지킨다** — 빠지면 「스물이 왜 열아홉이지」 가 된다."""
        first = _process(client, admin_headers, [runs[0]])[0]
        second = _process(client, admin_headers, [runs[0], runs[1]])
        gone = str(uuid.uuid4())

        got = client.post(
            "/api/processing/overview",
            json={"test_run_ids": [runs[2], gone, runs[0], runs[1]]},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        rows = got.json()
        assert [one["test_run_id"] for one in rows] == [runs[2], gone, runs[0], runs[1]]
        assert rows[1]["found"] is False

        untouched, _, twice, once = rows
        assert untouched["results"] == []
        assert untouched["test_type_key"] == "tensile"
        assert untouched["material_name"]
        # **최근 것이 앞에** — 다시 돌린 결과가 위에 서야 고르는 자리에서 헷갈리지 않는다.
        assert [one["id"] for one in twice["results"]] == [second[0], first]
        assert len(once["results"]) == 1
        brief = twice["results"][0]
        assert brief["scalars"], "견줄 값이 없다"
        assert brief["step_count"] == len(STEPS)
        assert brief["has_true_stress"] is False
        assert brief["is_adopted"] is False
        assert twice["access"]["can_edit"] is True

    def test_겹쳐_그릴_곡선을_한_번에_준다(
        self, client: TestClient, admin_headers: dict[str, str], runs: list[str]
    ) -> None:
        made = _process(client, admin_headers, runs[:2])
        got = client.post(
            "/api/processing/results/curves",
            json={"result_ids": [*made, str(uuid.uuid4())]},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        lines = got.json()
        # 없는 결과는 빼고 준다 — 무엇이 빠졌는지는 목록이 이미 말한다.
        assert [one["result_id"] for one in lines] == made
        assert [one["test_run_id"] for one in lines] == runs[:2]
        # 축은 결과 탭이 처음 여는 축과 같다 — 공칭이 먼저.
        assert lines[0]["x"] == "strain_engineering"
        assert lines[0]["y"] == "stress_engineering"
        assert lines[0]["points"]

    def test_상한을_서버가_강제한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.post(
            "/api/processing/overview",
            json={"test_run_ids": [str(uuid.uuid4()) for _ in range(OVERVIEW_MAX + 1)]},
            headers=admin_headers,
        )
        assert got.status_code == 422


class Test건별로_채택한다:
    def test_채택하면_요약값_표가_따라온다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        runs: list[str],
    ) -> None:
        made = _process(client, admin_headers, runs[:2])
        body = _adopt(
            client,
            admin_headers,
            [
                {"test_run_id": runs[0], "result_id": made[0]},
                {"test_run_id": runs[1], "result_id": made[1]},
            ],
        )
        assert (body["changed"], body["unchanged"], body["failed"]) == (2, 0, 0)
        assert body["items"][0]["previous_adopted_id"] is None
        assert _adopted(client, admin_headers, runs[0]) == made[0]
        assert _adopted(client, admin_headers, runs[1]) == made[1]
        # **통계가 읽는 자리가 따라와야 한다** — 포인터만 옮기면 값은 옛것이다.
        assert _summaries(db, runs[0]) > 0

    def test_이미_그렇다면_바꾸지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], runs: list[str]
    ) -> None:
        made = _process(client, admin_headers, [runs[0]])
        _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": made[0]}])
        again = _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": made[0]}])
        assert again["items"][0]["status"] == "unchanged"
        assert again["changed"] == 0

    def test_비우면_채택_전으로_돌아간다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        runs: list[str],
    ) -> None:
        """**되돌리기가 이 길이다** — 응답의 `previous_adopted_id` 를 그대로 돌려보낸다."""
        made = _process(client, admin_headers, [runs[0]])
        done = _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": made[0]}])
        before = done["items"][0]["previous_adopted_id"]
        assert before is None

        back = _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": before}])
        assert back["items"][0]["status"] == "ok"
        assert _adopted(client, admin_headers, runs[0]) is None
        # 요약값도 함께 비워진다 — 남으면 채택 안 한 값이 통계에 선다.
        assert _summaries(db, runs[0]) == 0
        # **결과는 지워지지 않는다** — 채택은 고르는 일이지 만드는 일이 아니다.
        listed = client.get(
            f"/api/processing/results?test_run_id={runs[0]}", headers=admin_headers
        ).json()
        assert [one["id"] for one in listed] == made

    def test_다른_것으로_바꾸면_이전_채택을_돌려준다(
        self, client: TestClient, admin_headers: dict[str, str], runs: list[str]
    ) -> None:
        first = _process(client, admin_headers, [runs[0]])[0]
        second = _process(client, admin_headers, [runs[0]])[0]
        _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": first}])
        moved = _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": second}])
        assert moved["items"][0]["previous_adopted_id"] == first
        assert moved["items"][0]["adopted_result_id"] == second

        back = _adopt(client, admin_headers, [{"test_run_id": runs[0], "result_id": first}])
        assert back["items"][0]["status"] == "ok"
        assert _adopted(client, admin_headers, runs[0]) == first

    def test_남의_시험_결과는_못_고르고_나머지는_된다(
        self, client: TestClient, admin_headers: dict[str, str], runs: list[str]
    ) -> None:
        """**채택을 옮기는 뒷문이 되면 안 된다.** 그리고 한 건이 막혀도 다른 건은 된다."""
        made = _process(client, admin_headers, runs[:2])
        body = _adopt(
            client,
            admin_headers,
            [
                {"test_run_id": runs[0], "result_id": made[1]},
                {"test_run_id": runs[1], "result_id": made[1]},
            ],
        )
        wrong, right = body["items"]
        assert wrong["status"] == "failed"
        assert "이 시험의 것이 아닙니다" in (wrong["error"] or "")
        assert right["status"] == "ok"
        assert _adopted(client, admin_headers, runs[0]) is None
        assert _adopted(client, admin_headers, runs[1]) == made[1]

    def test_못_보는_시험은_실패_줄이다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = _adopt(
            client, admin_headers, [{"test_run_id": str(uuid.uuid4()), "result_id": None}]
        )
        assert body["items"][0]["status"] == "failed"
        assert body["failed"] == 1


def _person(
    client: TestClient, admin_headers: dict[str, str], *, slug: str, email: str
) -> dict[str, str]:
    made = client.post(
        "/api/accounts",
        json={"email": email, "display_name": email, "workspace_slug": slug, "role": "member"},
        headers=admin_headers,
    )
    assert made.status_code in (200, 201), made.text
    token = client.post(
        "/api/auth/login",
        json={"email": email, "password": made.json()["temporary_password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class Test고칠_수_있는_사람만:
    def test_남의_부서_시험은_막히고_까닭이_줄에_온다(
        self, client: TestClient, admin_headers: dict[str, str], runs: list[str]
    ) -> None:
        """**여럿을 한 번에 바꾸는 길이라고 판정이 느슨해지지 않는다**(ADR 0035)."""
        made = client.post(
            "/api/workspaces",
            json={"name": "다른 부서", "slug": "board-other"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        outsider = _person(client, admin_headers, slug="board-other", email="out@b.com")
        result = _process(client, admin_headers, [runs[0]])[0]

        seen = client.post(
            "/api/processing/overview", json={"test_run_ids": [runs[0]]}, headers=outsider
        ).json()[0]
        if seen["found"]:
            # 보기는 전원이어도 고치기는 아니다 — 누르기 전에 화면이 안다.
            assert seen["access"]["can_edit"] is False

        body = _adopt(client, outsider, [{"test_run_id": runs[0], "result_id": result}])
        assert body["items"][0]["status"] == "failed"
        assert body["items"][0]["error"]
        assert _adopted(client, admin_headers, runs[0]) is None


class Test남의_시험을_채택하면:
    def test_등록자마다_한_줄로_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        runs: list[str],
    ) -> None:
        """**자료 관리자가 남의 시험 셋을 채택하면 등록자의 이력에 한 줄**(배치와 같다).

        시험마다 커밋하면서 돌며 적으면 시험 수만큼 줄이 생긴다.
        """
        made = client.post(
            "/api/workspaces",
            json={"name": "관리 부서", "slug": "board-steward"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        steward = client.post(
            "/api/accounts",
            json={
                "email": "steward@b.com",
                "display_name": "관리자",
                "workspace_slug": "board-steward",
                "role": "member",
            },
            headers=admin_headers,
        ).json()
        account_id = steward["account"]["id"] if "account" in steward else steward["id"]
        granted = client.post(
            f"/api/accounts/{account_id}/data-manager",
            json={"is_data_manager": True},
            headers=admin_headers,
        )
        assert granted.status_code == 200, granted.text
        token = client.post(
            "/api/auth/login",
            json={"email": "steward@b.com", "password": steward["temporary_password"]},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        results = _process(client, admin_headers, runs)
        before = db.scalar(
            select(AuditEntry.id)
            .where(AuditEntry.action == "data.edited_by_other")
            .order_by(AuditEntry.created_at.desc())
        )
        body = _adopt(
            client,
            headers,
            [
                {"test_run_id": run_id, "result_id": result_id}
                for run_id, result_id in zip(runs, results, strict=True)
            ],
        )
        assert body["changed"] == 3
        db.expire_all()
        lines = [
            one
            for one in db.scalars(
                select(AuditEntry).where(AuditEntry.action == "data.edited_by_other")
            )
            if one.id != before and one.target_table == "test_runs"
        ]
        assert len(lines) == 1, "채택 셋이 시험마다 한 줄로 남았다"
        assert lines[0].changes["count"] == 3
