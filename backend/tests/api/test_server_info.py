"""서버 현황 — **모르는 것을 0 이라고 말하지 않는가.**

무는 자리를 「응답이 온다」 보다 **「못 읽은 값이 `null` 인가」**·「관리자만 보는가」
에 둔다. 앞엣것이 틀리면 화면이 「메모리 0 바이트」·「부팅 직후」 라고 적고, 그것은
값이 아니라 거짓말이다 — 그 화면을 보는 이유가 통째로 사라진다.

이 모듈은 OS 마다 읽는 데가 다르다(리눅스는 `/proc`, Windows 는 kernel32). CI 와
개발 PC 가 같은 OS 라는 보장이 없으므로 **실제 수치를 단언하지 않는다** — 대신
「있으면 말이 되는가, 없으면 없다고 하는가」 를 본다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def member_headers(client: TestClient, db: Session, workspace: Any) -> dict[str, str]:
    """관리자가 아닌 사람. 이 화면이 막아야 하는 쪽이다."""
    from app.modules.accounts.models import User
    from app.modules.auth import security
    from app.modules.workspaces.models import WorkspaceMember

    user = User(
        email="server-member",
        password_hash=security.hash_password("pw12345678"),
        display_name="구성원",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.commit()
    login = client.post(
        "/api/auth/login", json={"email": "server-member", "password": "pw12345678"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class Test권한:
    def test_시스템_관리자만_본다(
        self, client: TestClient, member_headers: dict[str, str]
    ) -> None:
        """호스트 이름과 경로가 담긴다 — 사내라도 모두에게 보일 것은 아니다."""
        assert client.get("/api/server/info", headers=member_headers).status_code == 403

    def test_로그인_없이는_못_본다(self, client: TestClient) -> None:
        assert client.get("/api/server/info").status_code == 401


class Test값의_정직함:
    def test_모르는_값은_0_이_아니라_null(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**Windows 에는 load average 가 없다.** 0 으로 채우면 「한가하다」 로 읽힌다.

        리눅스에서는 값이 오고 Windows 에서는 `null` 이 온다 — 둘 다 옳다. 틀린
        것은 「없는데 0」 이다. 그래서 여기서는 **`null` 이거나 실수**만 허용한다.
        """
        body = client.get("/api/server/info", headers=admin_headers).json()
        for key in ("load_avg_1m", "load_avg_5m", "load_avg_15m"):
            value = body["cpu"][key]
            assert value is None or isinstance(value, float), (key, value)

    def test_메모리는_전부_있거나_전부_없다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """반쯤 읽은 값을 내면 화면이 「68GB 중 0 사용」 같은 것을 그린다."""
        memory = client.get("/api/server/info", headers=admin_headers).json()["memory"]
        keys = ("total_bytes", "available_bytes", "used_bytes", "percent_used")
        filled = [memory[key] is not None for key in keys]
        assert all(filled) or not any(filled), memory
        if memory["total_bytes"]:
            assert memory["used_bytes"] + memory["available_bytes"] == memory["total_bytes"]

    def test_디스크는_적어도_하나_나오고_합이_맞는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """파일 저장소가 어느 드라이브에 있든 그 드라이브는 읽힌다."""
        disks = client.get("/api/server/info", headers=admin_headers).json()["disks"]
        assert disks, "파일 저장소가 있는 드라이브는 언제나 읽혀야 한다"
        for disk in disks:
            assert disk["total_bytes"] > 0
            # 예약 블록 때문에 used + free 는 total 보다 작을 수 있다. 넘지만 않으면 된다.
            assert disk["used_bytes"] + disk["free_bytes"] <= disk["total_bytes"]
            assert 0 <= disk["percent_used"] <= 100

    def test_같은_드라이브는_한_줄로_합친다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**같은 수를 두 번 보이면 사람은 둘을 더해서 읽는다.** 개발 PC 는 저장소와
        프로그램이 한 드라이브에 있어 한 줄이어야 한다."""
        disks = client.get("/api/server/info", headers=admin_headers).json()["disks"]
        sizes = [(disk["total_bytes"], disk["free_bytes"]) for disk in disks]
        assert len(sizes) == len(set(sizes))

    def test_DB_는_버전과_크기를_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """디스크가 찰 때 **어느 쪽이 먹고 있는지**를 가르는 수다."""
        database = client.get("/api/server/info", headers=admin_headers).json()["database"]
        assert database["version"] != "알 수 없음"
        assert database["size_bytes"] and database["size_bytes"] > 0
