"""여러 사람이 같은 순간에 만들 때 — **데이터는 안전한가, 사람은 뭘 보는가.**

번호를 `max(seq_no) + 1` 로 받는 자리가 셋이다(시료·시편·시험 회차). 두 사람이
같은 순간에 만들면 **둘 다 같은 번호를 읽는다.** 실측으로 확인했다(2026-08-28):

    두 세션이 읽은 다음 번호: A=1 B=1
    A 커밋: 성공
    B 커밋: IntegrityError — 중복된 키 "uq_samples_material_seq_no"

**데이터는 안전했다** — 유니크 제약이 막으므로 같은 번호가 둘 생기지는 않는다.
문제는 두 번째 사람이 **500 을 본다**는 것이었다. 자기가 뭘 잘못했는지 알 수 없고
다시 눌러 보는 것 말고 할 수 있는 일이 없다.

## 시험하기 어려운 자리다

진짜 동시 요청은 시험에서 재현하기 번거롭다(스레드·별도 커넥션·타이밍). 대신
**부딪히는 순간을 만들어 준다** — 번호를 읽는 함수가 한 번은 남이 이미 쓴 번호를
돌려주게 해서, 그 뒤가 어떻게 되는지 본다. 재현이 아니라 **그 상황에서의 행동**을
보는 것이다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.modules.materials import services as materials_services
from app.modules.tests import services as test_services

SECC: dict[str, Any] = {
    "family": "Metal",
    "category": "Steel",
    "grade": "RACE",
    "details": "동시",
    "spec_thickness": 1.0,
}


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    made = client.post("/api/materials", json=SECC, headers=admin_headers)
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


class Test시료_번호가_부딪힐_때:
    def test_한_번_부딪혀도_만들어진다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """**번호는 사람이 고른 값이 아니다.** 다시 받아도 기대와 다르지 않으니
        조용히 다시 하는 것이 맞다 — 사람에게 「다시 눌러 주세요」 를 시키지 않는다."""
        client.post(f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers)

        real = materials_services.next_sample_seq
        state = {"first": True}

        def stale(*args: Any, **kwargs: Any) -> int:
            # 첫 번은 이미 쓰인 번호를 준다 — 남이 방금 가져간 상황.
            if state["first"]:
                state["first"] = False
                return 1
            return real(*args, **kwargs)

        monkeypatch.setattr(materials_services, "next_sample_seq", stale)
        again = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        )
        assert again.status_code == 201, again.text
        assert again.json()["seq_no"] == 2

    def test_계속_부딪히면_읽을_수_있는_말로_막는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """**500 이 아니어야 한다.** 서버 오류는 사람에게 할 일을 안 알려 준다."""
        client.post(f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers)
        monkeypatch.setattr(materials_services, "next_sample_seq", lambda *a, **k: 1)

        response = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        )
        assert response.status_code == 409, response.text
        assert "다시 시도" in response.json()["error"]["message"]

    def test_같은_번호가_둘_생기지는_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """**여기가 진짜 지키는 것이다.** 재시도가 없어도 유니크가 막는다 —
        번호가 겹친 시료 둘은 이름도 같아서 나중에 어느 것이 어느 것인지 모른다."""
        first = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        real = materials_services.next_sample_seq
        state = {"first": True}

        def stale(*args: Any, **kwargs: Any) -> int:
            if state["first"]:
                state["first"] = False
                return int(first["seq_no"])
            return real(*args, **kwargs)

        monkeypatch.setattr(materials_services, "next_sample_seq", stale)
        client.post(f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers)

        rows = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        numbers = [one["seq_no"] for one in rows]
        assert len(numbers) == len(set(numbers)), numbers


class Test재료_이름이_부딪힐_때:
    def test_이름은_다시_안_받고_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """**이름은 사람이 정한 값이다.** 번호처럼 말없이 바꾸면 안 된다 —
        `SECC_A` 를 만들려던 사람에게 `SECC_A_2` 를 주면 그건 다른 재료다.

        검사(`ensure_name_free`)를 지나왔어도 부딪힌다. 그 사이에 남이 같은
        이름을 넣을 수 있다.
        """
        monkeypatch.setattr(materials_services, "name_taken", lambda *a, **k: False)
        response = client.post("/api/materials", json=SECC, headers=admin_headers)
        assert response.status_code == 409, response.text
        assert "같은 이름의 재료가 이미 있습니다" in response.json()["error"]["message"]


class Test시험_회차가_부딪힐_때:
    """**일괄 등록이 이 자리를 특히 많이 지난다.**"""

    def _specimen(
        self, client: TestClient, headers: dict[str, str], material: dict[str, Any]
    ) -> dict[str, Any]:
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=headers
        ).json()
        made: dict[str, Any] = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=headers,
        ).json()
        return made

    def test_한_번_부딪혀도_올라간다(
        self,
        client: TestClient,
        db: Any,
        admin_headers: dict[str, str],
        material: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.modules.tests.definitions import ensure_builtin_test_types

        ensure_builtin_test_types(db)
        db.commit()
        specimen = self._specimen(client, admin_headers, material)

        def upload() -> Any:
            return client.post(
                "/api/test-runs",
                data={
                    "specimen_id": specimen["id"],
                    "test_type": "tensile",
                    "conditions": "{}",
                },
                files={"file": ("a.csv", b"x,y\n1,2\n")},
                headers=admin_headers,
            )

        assert upload().status_code == 202
        real = test_services.next_run_seq
        state = {"first": True}

        def stale(*args: Any, **kwargs: Any) -> int:
            if state["first"]:
                state["first"] = False
                return 1
            return real(*args, **kwargs)

        monkeypatch.setattr(test_services, "next_run_seq", stale)
        again = upload()
        # **파일을 저장하기 전에 부딪힌다** — 다시 해도 저장한 파일이 안 남는다.
        assert again.status_code == 202, again.text
        assert again.json()["seq_no"] == 2
