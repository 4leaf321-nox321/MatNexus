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
import json
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
from app.modules.commissions.models import Commission
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


class Test홈에_알린다:
    """**수집함은 안쪽에 있어 매일 여는 자리가 아니다.** 장비는 매일 파일을 보내는데
    아무도 안 열면 쌓인 줄도 모른다 — 메뉴 위치를 바꾸면 「찾기」 는 쉬워지지만
    「봐야 한다」 는 신호는 안 생긴다. 홈의 남은 일 줄이 그 신호를 내는 자리다."""

    def test_사람이_붙여야_하는_것을_홈이_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        db: Session,
        tensile: None,
    ) -> None:
        """**받은 직후가 아니라 워커가 훑고 난 뒤에 센다.** 갓 들어온 파일은
        아직 `received` 라 사람이 할 일이 없다 — 서버가 후보를 좁혀 봐야 「붙여야
        하는가」 가 정해진다."""
        before = client.get("/api/statistics/overview", headers=admin_headers).json()
        _send(client, pat, connector["id"], filename="a.tra")
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        after = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert after["inbox_waiting"] == before["inbox_waiting"] + 1

    def test_끝난_것은_안_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        db: Session,
        tensile: None,
    ) -> None:
        """**버린 것까지 세면 그 수는 영영 안 줄고, 그러면 아무도 안 본다.**"""
        item = _send(client, pat, connector["id"], filename="b.tra").json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        waiting = client.get("/api/statistics/overview", headers=admin_headers).json()[
            "inbox_waiting"
        ]
        client.post(
            f"/api/pipelines/inbox/{item['id']}/discard",
            json={"reason": "시험 파일이 아니다"},
            headers=admin_headers,
        )
        after = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert after["inbox_waiting"] == waiting - 1

    def test_커넥터를_치우면_그_파일도_안_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        db: Session,
        tensile: None,
    ) -> None:
        """**목록에서 사라진 커넥터의 파일을 홈이 세면 갈 데가 없다** — 눌러도
        그 커넥터가 없다. 수집함 행은 남지만 세지는 않는다."""
        _send(client, pat, connector["id"], filename="c.tra")
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        before = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert before["inbox_waiting"] > 0
        client.delete(f"/api/pipelines/connectors/{connector['id']}", headers=admin_headers)
        after = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert after["inbox_waiting"] == 0


class Test커넥터_치우기:
    """**끄기와 지우기는 다르다.** 끈 것은 목록에 남아 「저건 뭐지」 를 계속 묻게
    만든다 — 바꾼 장비, 반납한 PC, 시험 삼아 붙였다 만 것이 쌓이면 살아 있는
    커넥터를 그 사이에서 골라내야 한다."""

    def test_지우면_목록에서_빠진다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        connector: dict[str, Any],
    ) -> None:
        gone = client.delete(
            f"/api/pipelines/connectors/{connector['id']}", headers=admin_headers
        )
        assert gone.status_code == 204, gone.text
        rows = client.get("/api/pipelines/connectors", headers=admin_headers).json()
        assert connector["id"] not in [one["id"] for one in rows]

    def test_같은_PC_를_다시_붙일_수_있다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        workspace: Any,
    ) -> None:
        """**여기가 재료에서 터진 자리다.** 유니크가 지운 행까지 세면 그 PC 를
        영영 다시 못 붙이는데, 화면 어디에도 그 커넥터가 없다."""
        client.delete(f"/api/pipelines/connectors/{connector['id']}", headers=admin_headers)
        again = client.post(
            "/api/pipelines/connectors",
            json={
                "name": "인장기-1",
                "hostname": "ZWICK-PC",
                "workspace_id": str(workspace.id),
            },
            headers=pat,
        )
        assert again.status_code == 201, again.text
        # **새 커넥터다.** 옛 것을 되살리려면 휴지통에서 한다.
        assert again.json()["id"] != connector["id"]

    def test_수집함은_함께_안_지운다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
    ) -> None:
        """장비를 치웠다고 그 장비가 낸 데이터가 없던 일이 되면 안 된다."""
        _send(client, pat, connector["id"], filename="a.tra")
        before = client.get("/api/pipelines/inbox", headers=admin_headers).json()["total"]
        client.delete(f"/api/pipelines/connectors/{connector['id']}", headers=admin_headers)
        after = client.get("/api/pipelines/inbox", headers=admin_headers).json()["total"]
        assert after == before

    def test_휴지통에서_되살아난다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        connector: dict[str, Any],
    ) -> None:
        client.delete(f"/api/pipelines/connectors/{connector['id']}", headers=admin_headers)
        item = client.get("/api/trash?kind=connector", headers=admin_headers).json()[0]
        assert item["kind_label"] == "장비 커넥터"
        assert item["name"] == "인장기-1"
        back = client.post(f"/api/trash/connector/{item['id']}/restore", headers=admin_headers)
        assert back.status_code == 200, back.text
        rows = client.get("/api/pipelines/connectors", headers=admin_headers).json()
        assert connector["id"] in [one["id"] for one in rows]

    def test_그_PC_가_이미_다시_붙어_있으면_못_되살린다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        workspace: Any,
    ) -> None:
        """**DB 에 맡기면 500 이다.** 부분 인덱스가 막긴 하는데 화면에는
        "서버 오류" 만 뜬다."""
        client.delete(f"/api/pipelines/connectors/{connector['id']}", headers=admin_headers)
        client.post(
            "/api/pipelines/connectors",
            json={
                "name": "인장기-1",
                "hostname": "ZWICK-PC",
                "workspace_id": str(workspace.id),
            },
            headers=pat,
        )
        item = client.get("/api/trash?kind=connector", headers=admin_headers).json()[0]
        blocked = client.post(
            f"/api/trash/connector/{item['id']}/restore", headers=admin_headers
        )
        assert blocked.status_code == 409, blocked.text


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

    def test_스스로_붙인_시험은_커넥터_부서가_고친다(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
        workspace: Any,
    ) -> None:
        """커넥터는 등록할 때 부서를 고른다(ADR 0035). 스스로 붙인 시험은 등록자가
        없으니, 그 부서가 편집을 받지 않으면 자료 관리자만 고칠 수 있다."""
        client.patch(
            f"/api/pipelines/connectors/{connector['id']}",
            json={"auto_register": True},
            headers=pat,
        )
        received = _send(client, pat, connector["id"]).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None and item.status == "registered", item and item.error
        run = db.get(TestRun, item.test_run_id)
        assert run is not None
        assert run.registered_by_id is None
        assert run.edit_workspace_id == workspace.id

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


class Test의뢰_귀띔:
    """**「이 시험, 누가 재 달라고 한 건가」** 를 수집함이 말한다(2026-09-18).

    전에는 파일을 시편에 붙이고 나서 의뢰 화면으로 건너가, 어느 건인지 스스로
    떠올려 시험을 이어야 했다. 그 왕복을 안 하면 의뢰는 「시험 중」 인 채로 서 있고
    진행률은 0 으로 남는다 — 낸 부서에는 아무 일도 안 일어난 것으로 보인다.

    **잇지는 않는다.** 잘못 이으면 의뢰가 재지도 않은 것을 잰 것으로 적는다.
    """

    def _commission(
        self,
        client: TestClient,
        db: Session,
        headers: dict[str, str],
        workspace: Any,
        sample_id: str,
        *,
        status: str,
    ) -> dict[str, Any]:
        made = client.post(
            "/api/commissions",
            json={
                "title": "SECC 인장",
                "purpose": "성형 해석용",
                "sample_id": sample_id,
                "lab_workspace_slug": workspace.slug,
                "items": [{"test_type_key": "tensile", "count": 3}],
                "submit": True,
            },
            headers=headers,
        )
        assert made.status_code == 201, made.text
        body: dict[str, Any] = made.json()
        # 상태 전이는 여기서 볼 것이 아니다 — 귀띔이 어느 상태에서 뜨는지만 본다.
        row = db.get(Commission, uuid.UUID(body["id"]))
        assert row is not None
        row.status = status
        db.commit()
        return body

    def _detail(
        self, client: TestClient, headers: dict[str, str], item_id: str
    ) -> dict[str, Any]:
        got: dict[str, Any] = client.get(
            f"/api/pipelines/inbox/{item_id}", headers=headers
        ).json()
        return got

    @pytest.fixture
    def suggested(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> dict[str, Any]:
        received: dict[str, Any] = _send(client, pat, connector["id"]).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        return received

    def test_후보에_의뢰가_붙는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Any,
        specimen: dict[str, Any],
        suggested: dict[str, Any],
    ) -> None:
        made = self._commission(
            client, db, admin_headers, workspace, specimen["sample_id"], status="accepted"
        )
        detail = self._detail(client, admin_headers, suggested["id"])
        hint = detail["candidates"][0]["commission"]
        assert hint is not None, detail["candidates"]
        assert hint["commission_id"] == made["id"]
        assert hint["seq"] == made["seq"]
        # 시험 종류가 맞은 항목까지 짚는다 — 사람이 어느 줄에 이을지 안다.
        assert hint["item_position"] == 0

    def test_아직_접수_전이면_안_뜬다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Any,
        specimen: dict[str, Any],
        suggested: dict[str, Any],
    ) -> None:
        """**접수 전에 붙이면 받지도 않은 일이 진행되는 셈이다**(`LINKABLE`).

        귀띔이 붙을 수 없는 건을 가리키면, 눌러 본 사람이 거절당하고 이유를 모른다.
        """
        self._commission(
            client, db, admin_headers, workspace, specimen["sample_id"], status="submitted"
        )
        detail = self._detail(client, admin_headers, suggested["id"])
        assert detail["candidates"][0]["commission"] is None

    def test_의뢰가_없으면_아무_말도_안_한다(
        self, client: TestClient, admin_headers: dict[str, str], suggested: dict[str, Any]
    ) -> None:
        detail = self._detail(client, admin_headers, suggested["id"])
        assert detail["candidates"] and detail["candidates"][0]["commission"] is None


class Test파일_밖의_힌트:
    """**파일 밖(폴더·파일명)에 있는 정보를 받는다**(2026-09-20).

    일곱 키만 받던 때, 같은 등급 다른 두께가 흔한데 `material_code` 만으로는 후보가 여럿이라
    `needs_specimen` 으로 떨어졌다. 재료·시료·시편 모델의 칸과 하나씩 맞는 키를 열어 두고,
    있으면 그대로 저장하고 좁히는 데 쓴다.

    무는 것:

        두께가 재료를 가른다          SECC 1.0 과 0.8 — thickness=0.8 이면 하나
        통째 이름이 한 번에 푼다      record_name 하나로 시편까지
        조건이 시험에 실린다          temperature=80C → 시험 조건 353.15 K
        시험일의 마지막 보루          파일이 안 적었으면 mtime
        의뢰 번호는 먼저 보일 뿐      commission=12 — 잇지는 않는다
    """

    @pytest.fixture
    def two_thicknesses(
        self, client: TestClient, admin_headers: dict[str, str], specimen: dict[str, Any]
    ) -> dict[str, Any]:
        """SECC 1.0(기본 fixture) 옆에 SECC 0.8 을 하나 더 — 시료·시편까지."""
        thin = client.post(
            "/api/materials", json={**SECC, "spec_thickness": 0.8}, headers=admin_headers
        ).json()
        sample = client.post(
            f"/api/materials/{thin['id']}/samples", json={}, headers=admin_headers
        ).json()
        made: dict[str, Any] = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()
        return made

    def test_두께가_재료를_가른다(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        two_thicknesses: dict[str, Any],
        tensile: None,
    ) -> None:
        # 두께 없이 — 같은 등급이 둘이라 후보가 여럿이다.
        vague = _send(
            client,
            pat,
            connector["id"],
            hints='{"material_code": "SECC", "orientation": "MD"}',
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(vague["id"]))
        assert item is not None and item.status == "needs_specimen"
        assert len(item.candidates) == 2

        # 두께를 주면 하나로 좁혀 승인 대기까지 간다. `0.8t` 처럼 폴더식 표기도 읽는다.
        sharp = _send(
            client,
            pat,
            connector["id"],
            content=TRA.read_bytes() + b"\n",  # 내용 해시가 달라야 두 번째 파일로 받는다
            hints='{"material_code": "SECC", "orientation": "MD", "thickness": "0.8t"}',
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(sharp["id"]))
        assert item is not None
        assert item.status == "suggested", item.error
        assert item.candidates[0]["specimen_id"] == two_thicknesses["id"]
        assert "두께 0.8t" in item.candidates[0]["reason"]
        # 받은 힌트는 **그대로** 저장된다 — 나중에 사람이 왜 이렇게 붙었는지 본다.
        assert item.hints["thickness"] == "0.8t"

    def test_통째_이름이_한_번에_푼다(
        self,
        client: TestClient,
        db: Session,
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        two_thicknesses: dict[str, Any],
        tensile: None,
    ) -> None:
        """시험 토막(`__TEN_02`)이 붙어 있어도 뗀다 — 장비가 시험 이름을 파일명으로 낸다."""
        name = str(two_thicknesses["record_name"]) + "__TEN_02"
        received = _send(
            client, pat, connector["id"], hints=json.dumps({"record_name": name})
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        item = db.get(PipelineInboxItem, uuid.UUID(received["id"]))
        assert item is not None
        assert item.status == "suggested", item.error
        assert item.candidates[0]["specimen_id"] == two_thicknesses["id"]
        assert "이름 통째" in item.candidates[0]["reason"]

    def test_조건과_부서가_시험에_실리고_시험일은_mtime_이_보루다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        pat: dict[str, str],
        connector: dict[str, Any],
        specimen: dict[str, Any],
        tensile: None,
    ) -> None:
        received = _send(
            client,
            pat,
            connector["id"],
            hints=json.dumps(
                {
                    "material_code": "SECC",
                    "orientation": "MD",
                    "specimen": "1",
                    "temperature": "80C",
                    "division": "MX",
                    "repeat": "r2",
                    "commission": "12",
                }
            ),
        ).json()
        _run_worker(db, kinds.PIPELINES_PARSE_INBOX)
        done = client.post(
            f"/api/pipelines/inbox/{received['id']}/approve", headers=admin_headers
        )
        assert done.status_code == 200, done.text
        run = db.scalar(select(TestRun).order_by(TestRun.created_at.desc()))
        assert run is not None
        # 80 °C → 353.15 K, 입력 단위는 남는다.
        assert run.conditions.get("temperature") == pytest.approx(353.15)
        assert run.input_units.get("temperature") == "degC"
        assert run.division == "MX"
        # 칸이 없는 힌트(재시험·의뢰 번호)는 메모로 남는다 — 잇지는 않는다.
        assert "재시험 표시: r2" in (run.note or "")
        assert "의뢰 #12" in (run.note or "")
        assert run.commission_item_id is None
        # 파일도 힌트도 시험일을 안 줬다 — 봉투의 mtime 이 시험일이다.
        assert run.tested_at is not None and run.tested_at.year == 2026


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
