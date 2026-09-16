"""부서 정보 내보내기 — **가져오기와 짝이다.**

무는 것이 셋이다.

    낸 파일이 그대로 들어간다        열·순서가 RA·TestScope 와 같아 양쪽으로 오간다
    트리 순서·상위·부서장이 맞다     평면으로 풀리거나 부서장이 빠지면 조직도가 아니다
    시스템 관리자만 받는다           부서장 이름·멤버 수는 조직 정보다
"""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_workspace_import import HEADER  # 같은 폴더 — pytest·mypy 가 같은 이름으로 본다
from test_workspaces import headers_for, make_active_user

from app.modules.workspaces.models import Workspace


def fetch(client: TestClient, headers: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    response = client.get("/api/workspaces/export.csv", headers=headers)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8")
    assert text.startswith("﻿"), "BOM 이 없으면 Excel 이 한글을 깬다"
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    return text, rows


def test_열과_순서가_RA_와_같고_트리대로_나온다(
    client: TestClient, db: Session, admin_headers: dict[str, str], workspace: Workspace
) -> None:
    child = Workspace(
        slug="metal-alloy", name="합금파트", parent_id=workspace.id, sort_order=1
    )
    first = Workspace(
        slug="metal-steel", name="철강파트", parent_id=workspace.id, sort_order=0
    )
    db.add_all([child, first])
    db.commit()

    text, rows = fetch(client, admin_headers)
    assert text.lstrip("﻿").splitlines()[0] == HEADER
    # 트리 순서 — 부모 다음에 자식, 형제는 sort_order 순.
    assert [row["slug"] for row in rows] == ["metal", "metal-steel", "metal-alloy"]
    alloy = rows[2]
    assert alloy["parent_slug"] == "metal"
    assert alloy["parent_name"] == "금속재료팀"
    assert alloy["depth"] == "1"
    assert alloy["path"] == "금속재료팀 > 합금파트"  # 받는 쪽 규약(" > ")
    assert alloy["kind"] == "org"
    assert alloy["status"] == "active"
    assert alloy["sort_order"] == "1"
    # 관리자 fixture 가 metal 의 부서장이다.
    assert rows[0]["managers"] == "시스템 관리자"
    assert rows[0]["member_count"] == "1"


def test_낸_파일이_그대로_가져오기에_들어간다(
    client: TestClient, db: Session, admin_headers: dict[str, str], workspace: Workspace
) -> None:
    """양쪽으로 오가야 호환이다 — 한쪽으로만 들어가는 것은 이사다."""
    db.add(Workspace(slug="metal-steel", name="철강파트", parent_id=workspace.id))
    db.commit()
    text, _ = fetch(client, admin_headers)

    preview = client.post(
        "/api/workspaces/import/preview",
        files={"file": ("부서정보.csv", text.encode("utf-8"), "text/csv")},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["errors"] == 0
    # 이미 있으니 전부 「이미 있음」 — 오류가 하나라도 있으면 형식이 어긋난 것이다.
    assert {row["action"] for row in body["rows"]} == {"skip_exists"}


def test_시스템_관리자만_받는다(client: TestClient, db: Session, workspace: Workspace) -> None:
    make_active_user(db, "member")
    response = client.get("/api/workspaces/export.csv", headers=headers_for(client, "member"))
    assert response.status_code == 403
