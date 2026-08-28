"""장비 커넥터 — **장비 PC 가 보낸 파일이 시험이 되는 길.**

무는 자리를 「받는다」 보다 **되돌릴 수 없거나 조용히 틀리는 것**에 둔다.

- 같은 내용을 두 번 받으면 시험이 둘 생긴다 → 통계가 조용히 두 번 센다.
- 남의 부서에 파일이 들어간다 → 권한 경계가 뚫린다.
- 원본이 두 곳에 남는다 → 정리 잡이 어느 것을 지워야 하는지 모른다.
- 후보가 여럿인데 하나를 찍는다 → 엉뚱한 시편에 곡선이 붙는다.

실제 Zwick 파일(`tests/fixtures/Example.tra`)로 끝에서 끝까지 돌린다.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import handlers, kinds
from app.jobs.models import Job
from app.modules.pipelines import services
from app.modules.pipelines.models import PipelineInboxItem
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

SECC: dict[str, Any] = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "MDOI",
    "spec_thickness": 1.0,
}


@pytest.fixture
def tensile(db: Session) -> None:
    ensure_builtin_test_types(db)
    db.commit()
    handlers.load_all()


@pytest.fixture
def specimen(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    """`SECC_MDOI_1.0__01__MD_01` 하나."""
    material = client.post("/api/materials", json=SECC, headers=admin_headers).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    made: dict[str, Any] = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    return made


@pytest.fixture
def pat(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    """에이전트는 PAT 로 온다 — 사람 세션이 아니다."""
    made = client.post("/api/auth/tokens", json={"name": "인장기-1"}, headers=admin_headers)
    assert made.status_code == 201, made.text
    return {"Authorization": f"Bearer {made.json()['token']}"}


@pytest.fixture
def connector(client: TestClient, pat: dict[str, str], workspace: Any) -> dict[str, Any]:
    made = client.post(
        "/api/pipelines/connectors",
        json={"name": "인장기-1", "hostname": "ZWICK-PC", "workspace_id": str(workspace.id)},
        headers=pat,
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _send(
    client: TestClient,
    headers: dict[str, str],
    connector_id: str,
    *,
    content: bytes | None = None,
    filename: str = "Example.tra",
    hints: str = '{"material_code": "SECC", "orientation": "MD", "specimen": "1"}',
    sha256: str | None = None,
) -> Any:
    data = content if content is not None else TRA.read_bytes()
    return client.post(
        "/api/pipelines/inbox",
        data={
            "connector_id": connector_id,
            "source_key": "zwick_export",
            "client_sha256": sha256 or hashlib.sha256(data).hexdigest(),
            "client_path": r"C:\Zwick\export\Example.tra",
            "mtime": "2026-08-28T05:12:00.000Z",
            "hints": hints,
        },
        files={"file": (filename, data)},
        headers=headers,
    )


def _run_worker(db: Session, kind: str) -> None:
    for job in list(db.scalars(select(Job).where(Job.kind == kind, Job.status == "queued"))):
        job.status = "done"
        handlers.get(kind)(db, job.payload)
        db.commit()


class Test커넥터:
    def test_같은_호스트는_기존_것을_돌려준다(
        self,
        client: TestClient,
        pat: dict[str, str],
        connector: dict[str, Any],
        workspace: Any,
    ) -> None:
        """재설치 뒤 커넥터가 둘이 되면 관리 화면에서 어느 것이 살아 있는지 모른다."""
        again = client.post(
            "/api/pipelines/connectors",
            json={
                "name": "인장기-1 (재설치)",
                "hostname": "ZWICK-PC",
                "workspace_id": str(workspace.id),
            },
            headers=pat,
        )
        assert again.status_code == 201
        assert again.json()["id"] == connector["id"]
        assert again.json()["name"] == "인장기-1 (재설치)"

    def test_구성원이_아니면_만들_수_없다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**남의 부서에 파일을 밀어 넣을 수 없어야 한다.** 그 시작이 커넥터다."""
        from app.modules.accounts.models import User
        from app.modules.auth import security
        from app.modules.workspaces.models import Workspace

        other = Workspace(slug="plastic", name="고분자팀")
        db.add(other)
        stranger = User(
            email="stranger",
            password_hash=security.hash_password("pw12345678"),
            display_name="남",
            status="active",
            home_workspace_id=other.id,
        )
        db.add(stranger)
        db.commit()
        login = client.post(
            "/api/auth/login", json={"email": "stranger", "password": "pw12345678"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        metal = client.get("/api/workspaces", headers=admin_headers).json()
        metal_id = next(w["id"] for w in metal if w["slug"] == "metal")
        response = client.post(
            "/api/pipelines/connectors",
            json={"name": "x", "hostname": "X-PC", "workspace_id": metal_id},
            headers=headers,
        )
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "MNX-PIPE-0005"

    def test_heartbeat_가_대기와_실패를_남긴다(
        self, client: TestClient, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        beat = client.post(
            f"/api/pipelines/connectors/{connector['id']}/heartbeat",
            json={
                "app_version": "0.1.0",
                "sources": [
                    {"key": "zwick_export", "pending": 3, "failed": 1, "last_sent_at": None},
                    {"key": "dma", "pending": 2, "failed": 0, "last_sent_at": None},
                ],
                "next_run_at": "2026-08-28T06:00:00Z",
            },
            headers=pat,
        )
        assert beat.status_code == 200, beat.text
        assert beat.json()["upload_limit_bytes"] == get_settings().max_upload_bytes
        rows = client.get("/api/pipelines/connectors", headers=pat).json()
        mine = next(r for r in rows if r["id"] == connector["id"])
        assert (mine["pending"], mine["failed"]) == (5, 1)
        assert mine["last_seen_at"] is not None

    def test_비활성이면_받지_않는다(
        self, client: TestClient, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        off = client.patch(
            f"/api/pipelines/connectors/{connector['id']}",
            json={"is_active": False},
            headers=pat,
        )
        assert off.status_code == 200 and off.json()["is_active"] is False
        response = _send(client, pat, connector["id"])
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MNX-PIPE-0001"


class Test반입:
    def test_받으면_파일이_수집함에_떨어지고_작업이_생긴다(
        self, client: TestClient, db: Session, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        response = _send(client, pat, connector["id"])
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "received"
        assert body["hints"] == {"material_code": "SECC", "orientation": "MD", "specimen": "1"}
        item = db.get(PipelineInboxItem, uuid.UUID(body["id"]))
        assert item is not None and item.source_path
        assert (get_settings().filestore_dir / item.source_path).exists()
        assert item.source_path.startswith("inbox/")
        queued = db.scalar(select(Job).where(Job.kind == kinds.PIPELINES_PARSE_INBOX))
        assert queued is not None

    def test_해시가_다르면_받지_않고_파일도_안_남긴다(
        self, client: TestClient, db: Session, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        """전송 중 깨진 파일이다. 남겨 두면 나중에 「왜 못 읽지」 가 된다."""
        inbox = get_settings().filestore_dir / "inbox"
        before = set(inbox.rglob("*")) if inbox.exists() else set()
        response = _send(client, pat, connector["id"], sha256="0" * 64)
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "MNX-PIPE-0003"
        assert db.scalar(select(PipelineInboxItem)) is None
        # 파일 저장소는 세션 전체가 나눠 쓴다 — 앞 시험의 파일이 남아 있을 수 있다.
        # 그래서 「이 요청이 아무것도 안 남겼다」 를 본다.
        after = set(inbox.rglob("*")) if inbox.exists() else set()
        assert after == before

    def test_같은_내용은_두_번_받지_않는다(
        self, client: TestClient, db: Session, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        """**서버 원장이 정본이다.** 에이전트가 죽었다 살아나 다시 보내도 하나다."""
        first = _send(client, pat, connector["id"]).json()
        again = _send(client, pat, connector["id"])
        assert again.status_code == 409, again.text
        error = again.json()["error"]
        assert error["code"] == "MNX-PIPE-0004"
        assert error["details"] == {"existing_id": first["id"], "existing_kind": "inbox_item"}
        assert (
            db.scalar(
                select(PipelineInboxItem).where(PipelineInboxItem.id != uuid.UUID(first["id"]))
            )
            is None
        )

    def test_이미_시험이_된_파일도_막는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        """화면에서 올린 것과도 겹치면 안 된다 — 같은 곡선이 두 시험에 붙는다."""
        uploaded = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": ("Example.tra", TRA.read_bytes())},
            headers=admin_headers,
        )
        assert uploaded.status_code == 202
        response = _send(client, pat, connector["id"])
        assert response.status_code == 409
        assert response.json()["error"]["details"]["existing_kind"] == "test_run"

    def test_힌트가_JSON_객체가_아니면_거절한다(
        self, client: TestClient, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        response = _send(client, pat, connector["id"], hints="[1, 2]")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "MNX-PIPE-0006"

    def test_모르는_힌트_키는_버린다(
        self, client: TestClient, pat: dict[str, str], connector: dict[str, Any]
    ) -> None:
        response = _send(
            client, pat, connector["id"], hints='{"material_code": "A", "color": "red"}'
        )
        assert response.status_code == 202
        assert response.json()["hints"] == {"material_code": "A"}


class Test워커:
    def test_후보가_하나면_시험이_되고_원본이_옮겨진다(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        """**여기가 진짜 지키는 것이다.** 원본은 한 곳에만 있어야 하고, 시험은 화면
        업로드와 같은 파싱 길을 타야 한다. (자동 등록을 켠 커넥터)"""
        on = client.patch(
            f"/api/pipelines/connectors/{connector['id']}",
            json={"auto_register": True},
            headers=pat,
        )
        assert on.status_code == 200 and on.json()["auto_register"] is True
        received = _send(client, pat, connector["id"]).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)

        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None
        assert item.status == "registered", item.error
        assert item.source_path is None
        assert item.candidates[0]["specimen_name"] == specimen["record_name"]
        assert "SECC" in item.candidates[0]["reason"]

        run = db.get(TestRun, item.test_run_id)
        assert run is not None
        assert run.specimen_id == uuid.UUID(specimen["id"])
        assert run.source_path and run.source_path.startswith("test-runs/")
        root = get_settings().filestore_dir
        assert (root / run.source_path).exists()
        # 이 항목의 수집함 폴더는 사라졌다 — 원본은 한 곳에만 있다.
        assert not list((root / "inbox").rglob(f"*{item.id}*"))

        # 화면 업로드와 같은 파싱 워커가 읽는다.
        _run_worker(db, kinds.TESTS_PARSE_UPLOAD)
        db.refresh(run)
        assert run.status == "parsed", run.parse_error

    def test_재료_코드가_없으면_찍지_않는다(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        """시편 이름만으로 전 부서를 뒤지면 엉뚱한 재료에 붙는다."""
        received = _send(client, pat, connector["id"], hints='{"specimen": "1"}').json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None and item.status == "needs_specimen"
        assert "재료 코드" in (item.error or "")
        assert item.test_run_id is None
        assert item.source_path  # 원본은 그대로 있다 — 사람이 붙일 때 쓴다

    def test_후보가_여럿이면_사람을_기다리고_관리자에게_알린다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        sample_id = specimen["sample_id"]
        client.post(
            f"/api/samples/{sample_id}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        )
        received = _send(
            client,
            pat,
            connector["id"],
            hints='{"material_code": "SECC", "orientation": "MD"}',
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None and item.status == "needs_specimen"
        assert len(item.candidates) == 2
        notify = db.scalar(
            select(Job).where(
                Job.kind == kinds.NOTIFY_DELIVER,
                Job.payload["event_kind"].astext == "pipelines.needs_specimen",
            )
        )
        assert notify is not None

    def test_읽을_수_없으면_실패로_남긴다(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        tensile: None,
    ) -> None:
        received = _send(
            client, pat, connector["id"], content=b"nonsense", filename="x.unknown"
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None and item.status == "failed"
        assert item.error


class Test사람이_정한다:
    @pytest.fixture
    def waiting(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> dict[str, Any]:
        received: dict[str, Any] = _send(
            client, pat, connector["id"], hints='{"specimen": "1"}'
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        return received

    def test_붙이면_시험이_된다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        waiting: dict[str, Any],
        specimen: dict[str, Any],
    ) -> None:
        response = client.post(
            f"/api/pipelines/inbox/{waiting['id']}/assign",
            json={"specimen_id": specimen["id"]},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "registered" and body["test_run_id"]
        assert body["test_run_name"].startswith(specimen["record_name"])

        # 두 번은 안 된다 — 같은 파일이 두 시험에 붙는다.
        again = client.post(
            f"/api/pipelines/inbox/{waiting['id']}/assign",
            json={"specimen_id": specimen["id"]},
            headers=admin_headers,
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "MNX-PIPE-0007"

    def test_버리면_사유가_남고_원본은_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        waiting: dict[str, Any],
    ) -> None:
        response = client.post(
            f"/api/pipelines/inbox/{waiting['id']}/discard",
            json={"reason": "시험 실패한 파일"},
            headers=admin_headers,
        )
        assert response.status_code == 204, response.text
        item = db.get(PipelineInboxItem, uuid.UUID(waiting["id"]))
        assert item is not None and item.status == "discarded"
        assert item.discard_reason == "시험 실패한 파일"
        assert item.source_path and (get_settings().filestore_dir / item.source_path).exists()

    def test_다시_파싱하면_다시_줄을_선다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        waiting: dict[str, Any],
    ) -> None:
        response = client.post(
            f"/api/pipelines/inbox/{waiting['id']}/retry", headers=admin_headers
        )
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "received"

    def test_목록은_상태로_거른다(
        self, client: TestClient, admin_headers: dict[str, str], waiting: dict[str, Any]
    ) -> None:
        page = client.get(
            "/api/pipelines/inbox?status=needs_specimen", headers=admin_headers
        ).json()
        assert page["total"] == 1 and page["items"][0]["id"] == waiting["id"]
        empty = client.get(
            "/api/pipelines/inbox?status=registered", headers=admin_headers
        ).json()
        assert empty["total"] == 0
        bad = client.get("/api/pipelines/inbox?status=whatever", headers=admin_headers)
        assert bad.status_code == 422

    def test_상세는_후보와_요약을_준다(
        self, client: TestClient, admin_headers: dict[str, str], waiting: dict[str, Any]
    ) -> None:
        detail = client.get(
            f"/api/pipelines/inbox/{waiting['id']}", headers=admin_headers
        ).json()
        assert detail["client_path"].endswith("Example.tra")
        assert detail["summary"]["row_count"] > 0
        assert detail["test_type_key"] == "tensile"
        assert detail["candidates"] == []


class Test승인_대기:
    def test_기본은_승인_대기다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        """**규칙이 틀리게 맞으면 엉뚱한 시편에 시험이 붙는다** — 그래서 기본은
        사람이 한 번 보는 것이다."""
        received = _send(client, pat, connector["id"]).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None and item.status == "suggested"
        assert item.test_run_id is None  # 시험은 아직 없다
        assert item.source_path  # 원본도 아직 수집함에 있다
        assert len(item.candidates) == 1

        # **알림은 묶인다.** 파일 20개 = 알림 20개가 아니라 「승인 대기 N건」 하나.
        notify = [
            j.payload
            for j in db.scalars(select(Job).where(Job.kind == kinds.NOTIFY_DELIVER))
            if str(j.payload.get("key", "")).startswith("suggested:")
        ]
        assert notify and "승인 대기 1건" in str(notify[0]["body"])

        done = client.post(
            f"/api/pipelines/inbox/{received['id']}/approve", headers=admin_headers
        )
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "registered"
        run = db.get(TestRun, uuid.UUID(done.json()["test_run_id"]))
        assert run is not None and run.registered_by_id is not None  # 누가 승인했는지 남는다

    def test_여럿을_한꺼번에_승인하고_막힌_것은_이유와_함께(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        first = _send(client, pat, connector["id"]).json()
        second = _send(client, pat, connector["id"], content=TRA.read_bytes() + b"x").json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        client.post(
            f"/api/pipelines/inbox/{first['id']}/discard",
            json={"reason": "버림"},
            headers=admin_headers,
        )
        response = client.post(
            "/api/pipelines/inbox/approve",
            json={"ids": [first["id"], second["id"]]},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["approved"] == [second["id"]]
        assert first["id"] in body["failed"]

    def test_승인_대기에서_다른_시편으로_바꿔_붙일_수_있다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        other = client.post(
            f"/api/samples/{specimen['sample_id']}/specimens",
            json={"orientation": "TD"},
            headers=admin_headers,
        ).json()
        received = _send(client, pat, connector["id"]).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        moved = client.post(
            f"/api/pipelines/inbox/{received['id']}/assign",
            json={"specimen_id": other["id"]},
            headers=admin_headers,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["test_run_name"].startswith(other["record_name"])


class Test규칙_편집기가_묻는다:
    def test_대조는_워커와_같은_판정을_준다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        workspace: Any,
        specimen: dict[str, Any],
    ) -> None:
        """**여기서 「붙는다」 고 한 것이 반입 뒤에 실제로 붙어야 한다** — 같은 함수다."""
        sample_id = specimen["sample_id"]
        client.post(
            f"/api/samples/{sample_id}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        )
        response = client.post(
            "/api/pipelines/resolve",
            json={
                "workspace_id": str(workspace.id),
                "hints": [
                    {"material_code": "SECC", "specimen": "MD_01"},
                    {"material_code": "SECC", "orientation": "MD"},
                    {"material_code": "SECC", "lot": "LOT-A"},
                    {},
                ],
            },
            headers=pat,
        )
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        assert [r["outcome"] for r in results] == ["unique", "multiple", "none", "none"]
        assert results[0]["candidate"]["specimen_name"] == specimen["record_name"]
        assert len(results[1]["candidates"]) == 2
        assert "LOT-A" in results[2]["reason"]
        assert "재료 코드" in results[3]["reason"]

    def test_쉰_개를_넘으면_거절한다(
        self, client: TestClient, pat: dict[str, str], workspace: Any
    ) -> None:
        response = client.post(
            "/api/pipelines/resolve",
            json={"workspace_id": str(workspace.id), "hints": [{}] * 51},
            headers=pat,
        )
        assert response.status_code == 422

    def test_참조_트리는_이름과_별칭을_준다(
        self,
        client: TestClient,
        pat: dict[str, str],
        workspace: Any,
        specimen: dict[str, Any],
    ) -> None:
        tree = client.get(
            f"/api/pipelines/reference?workspace_id={workspace.id}", headers=pat
        ).json()
        assert len(tree["materials"]) == 1
        material = tree["materials"][0]
        assert material["name"] == "SECC_MDOI_1.0"
        # 워커가 `material_code` 를 맞출 때 보는 집합과 같다.
        assert material["aliases"] == ["SECC_MDOI_1.0", "SECC"]
        leaf = material["samples"][0]["specimens"][0]
        assert leaf["name"] == specimen["record_name"] and leaf["short"] == "MD_01"


def test_후보_조회는_파일이_힌트를_이긴다(
    db: Session, workspace: Any, specimen: dict[str, Any]
) -> None:
    """파일은 장비가 적은 증거고, 이름은 사람이 붙인 이름표다."""
    found = services.find_candidates(
        db,
        workspace_id=workspace.id,
        identity={"material_grade": "SECC"},
        hints={"material_code": "NOPE"},
    )
    assert found and found[0]["specimen_name"] == specimen["record_name"]
