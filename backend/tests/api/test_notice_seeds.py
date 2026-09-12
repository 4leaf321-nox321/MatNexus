"""배포에 실려 온 안내 — **초안으로 들어오고, 같은 키는 두 번 안 들어온다.**

새 기능은 코드와 함께 도착하는데 알리는 글은 사람이 따로 써야 했다. 씨앗이 초안으로
들어오면 관리자가 읽고 발행한다 — 자동 발행하지 않는다(배포한 사람이 첫 독자다).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.notices.models import Notice
from app.modules.workspaces.models import Workspace

BACKEND = Path(__file__).resolve().parents[2]


def _script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "import_notices", BACKEND / "scripts" / "import_notices.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_notices"] = module
    spec.loader.exec_module(module)
    return module


def test_씨앗이_초안으로_한_번만_들어오고_관리자만_본다(
    client: TestClient,
    db: Session,
    workspace: Workspace,
    admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    script = _script()
    (tmp_path / "2026-09-12-시험.md").write_text(
        "# 새로 생긴 것\n\n- 물성 매핑\n- 값 넣기\n", encoding="utf-8"
    )
    (tmp_path / "빈-것.md").write_text("# 제목만\n", encoding="utf-8")  # 본문 없음 — 건너뛴다

    assert script.run(db, tmp_path) == ["2026-09-12-시험"]
    assert script.run(db, tmp_path) == []  # 두 번째는 아무것도 안 넣는다
    assert script.plan(db, tmp_path) == []

    rows = db.scalars(select(Notice).where(Notice.seed_key.is_not(None))).all()
    assert len(rows) == 1
    assert rows[0].title == "새로 생긴 것"
    assert rows[0].body == "- 물성 매핑\n- 값 넣기"
    assert rows[0].is_published is False and rows[0].is_popup is False

    # 관리자는 초안을 보고, 일반 사용자는 못 본다.
    titles = [one["title"] for one in client.get("/api/notices", headers=admin_headers).json()]
    assert "새로 생긴 것" in titles
    member = User(
        email="hong",
        password_hash=security.hash_password("member-password-1"),
        display_name="홍길동",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(member)
    db.commit()
    login = client.post(
        "/api/auth/login", json={"email": "hong", "password": "member-password-1"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert "새로 생긴 것" not in [
        one["title"] for one in client.get("/api/notices", headers=headers).json()
    ]

    # 운영에서 고친 글은 안 덮인다 — 같은 키의 파일 내용이 바뀌어도.
    (tmp_path / "2026-09-12-시험.md").write_text(
        "# 바뀐 제목\n\n다른 본문\n", encoding="utf-8"
    )
    assert script.run(db, tmp_path) == []
    db.expire_all()
    kept = db.scalar(select(Notice).where(Notice.seed_key == "2026-09-12-시험"))
    assert kept is not None and kept.title == "새로 생긴 것"


def test_실린_씨앗은_전부_읽힌다() -> None:
    """저장소의 씨앗 파일이 제목·본문을 갖는다 — 배포에서 처음 터지면 늦다."""
    script = _script()
    files = sorted((BACKEND / "seeds" / "notices").glob("*.md"))
    assert files, "안내 씨앗이 하나도 없다"
    for path in files:
        title, body = script.read_seed(path)
        assert title and body, path.name
