"""시험 요약표 흡수 — **곡선 없이 값만 들어온다.**

기존 앱이 내보낸 표는 한 줄이 시험 하나이고 곡선이 없다. 곡선이 없다고 못 쓰는
데이터가 아니다 — **낼 수 있는 물성의 범위가 다를 뿐이다.** 통계도 되고 카드의
근거도 된다.

지키는 것:

    없는 시편을 만들지 말지는 옵션    오타 하나가 유령 시편을 만든다
    같은 표를 두 번 붙여도 안 는다    시험은 한 시편에 여러 번 있을 수 있다
    저장은 SI                        헤더가 MPa 여도 담기는 것은 Pa 다
    미리보기는 아무것도 안 쓴다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

HEADER = "시편\t방향\t원본 파일명\t항복강도 (MPa)\t최대하중 (kN)"


@pytest.fixture
def sample_id(client: TestClient, admin_headers: dict[str, str], db: Session) -> str:
    """시편 하나가 든 시료. 표는 이 시료 안에서 시편을 가리킨다."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "IMPORT",
            "details": "T",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD", "seq_no": 1},
        headers=admin_headers,
    )
    return str(sample["id"])


def send(
    client: TestClient,
    headers: dict[str, str],
    sample_id: str,
    lines: list[str],
    *,
    preview: bool = False,
    create_missing: bool = False,
) -> Any:
    return client.post(
        "/api/test-runs/import/preview" if preview else "/api/test-runs/import",
        json={
            "sample_id": sample_id,
            "test_type": "tensile",
            "values": lines,
            "create_missing": create_missing,
        },
        headers=headers,
    )


class TestStrict:
    """**기본은 끔이다.** 만들면 편하지만 오타 하나가 유령 시편을 만든다."""

    def test_있는_시편에_붙인다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        made = send(
            client,
            admin_headers,
            sample_id,
            [HEADER, "MD-1\tMD\ta.tra\t320\t12.5"],
        )
        assert made.status_code == 200, made.text
        (item,) = made.json()["items"]
        assert item["status"] == "new"
        assert item["creates_specimen"] is False
        assert item["run"]
        # **저장은 SI 다.** 헤더가 MPa 여도 담기는 것은 Pa 다.
        assert item["summaries"]["항복강도"] == pytest.approx(320e6)

    def test_없는_시편은_거절하고_이유를_말한다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        seen = send(
            client,
            admin_headers,
            sample_id,
            [HEADER, "MD-9\tMD\tb.tra\t320\t12.5"],
            preview=True,
        )
        (item,) = seen.json()["items"]
        assert item["status"] == "rejected"
        assert "없습니다" in item["reason"]


class TestCreateMissing:
    def test_켜면_시편을_만든다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        made = send(
            client,
            admin_headers,
            sample_id,
            [HEADER, "MD-2\tMD\tc.tra\t300\t11"],
            create_missing=True,
        )
        assert made.status_code == 200, made.text
        body = made.json()
        assert body["specimens_created"] == 1
        (item,) = body["items"]
        assert item["creates_specimen"] is True

        listed = client.get(f"/api/samples/{sample_id}/specimens", headers=admin_headers)
        assert {one["record_name"] for one in listed.json()} >= {item["specimen"]}

    def test_미리보기가_시편을_만드는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        """**켜 두면 표가 시편을 늘린다** — 누르기 전에 보여야 한다."""
        seen = send(
            client,
            admin_headers,
            sample_id,
            [HEADER, "MD-3\tMD\td.tra\t300\t11"],
            preview=True,
            create_missing=True,
        )
        (item,) = seen.json()["items"]
        assert item["status"] == "new" and item["creates_specimen"] is True

        # 미리보기는 아무것도 안 쓴다.
        listed = client.get(f"/api/samples/{sample_id}/specimens", headers=admin_headers)
        assert len(listed.json()) == 1


class TestTwice:
    def test_같은_표를_두_번_붙여도_안_는다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        """**시편만으로는 중복을 알 수 없다** — 시험은 한 시편에 여러 번 있다."""
        rows = [HEADER, "MD-1\tMD\te.tra\t320\t12.5"]
        send(client, admin_headers, sample_id, rows)
        again = send(client, admin_headers, sample_id, rows, preview=True)
        (item,) = again.json()["items"]
        assert item["status"] == "existing"
        assert "이미 들어왔습니다" in item["reason"]

    def test_원본_파일명이_없으면_막을_길이_없다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        """그 사실을 숨기지 않는다 — 두 번 붙이면 두 개가 된다."""
        rows = ["시편\t항복강도 (MPa)", "MD-1\t320"]
        send(client, admin_headers, sample_id, rows)
        again = send(client, admin_headers, sample_id, rows, preview=True)
        assert again.json()["items"][0]["status"] == "new"


class TestColumns:
    def test_조건은_시험_종류가_선언한_것만(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        """나머지 숫자 열은 요약값이다 — 표마다 열이 다르고 미리 알 수 없다."""
        made = send(
            client,
            admin_headers,
            sample_id,
            ["시편\t탄성역 속도 (mm/min)\tn값", "MD-1\t10\t0.21"],
        )
        (item,) = made.json()["items"]
        assert item["conditions"]  # 속도는 조건이다
        assert "n" in " ".join(item["summaries"])

    def test_숫자가_아닌_값도_버리지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], sample_id: str
    ) -> None:
        """장비가 `Unknown` 을 적기도 하고 시험자 이름 같은 글자 열도 섞인다."""
        made = send(
            client,
            admin_headers,
            sample_id,
            ["시편\toperator", "MD-1\t홍길동"],
        )
        (item,) = made.json()["items"]
        assert item["summaries"]["operator"] == "홍길동"
