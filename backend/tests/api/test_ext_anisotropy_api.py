"""이방성 — 세 방향 r값이 **묶음을 지나 카드까지** 간다.

이 파일이 지키는 것은 확장의 계산이 아니라(그쪽은 `tests/unit/test_ext_anisotropy.py`)
**길이 실제로 뚫려 있는가**다. 세 가지가 이 길에서 처음 일어난다:

    값이 두 곳에서 온다      채택된 결과(폭 채널이 있는 장비) · 표로 적은 요약값(없는 장비)
    방향이 시편에서 온다      조건에도 결과 스칼라에도 없는 값을 구성원이 든다
    카드에 방향이 없다        r̄ 는 세 방향을 함께 써서 나오므로 방향이 없는 물성이다

셋 중 어느 하나라도 막히면 이방성은 화면에서 카드가 안 된다.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting import card_tiers
from app.modules.fitting.models import PropertyCard
from app.modules.processing.models import ProcessingResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun

#: 표의 첫 줄. 요약값 열은 **키를 그대로** 적는다 — 묶음이 `r_value` 로 찾는다.
HEADER = "시편\t방향\tr_value"

#: 방향마다 답을 아는 r값. r̄ = (1.8 + 2·1.4 + 2.1)/4 = 1.675, Δr = 0.55.
R_OF = {"MD": 1.8, "DD": 1.4, "TD": 2.1}


def _rows() -> list[str]:
    return [HEADER] + [
        f"{index}\t{orientation}\t{value}"
        for index, (orientation, value) in enumerate(R_OF.items(), start=1)
    ]


@pytest.fixture
def imported(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    """폭 채널이 없는 장비의 시험 셋 — **사람이 표로 적은 r값**으로 들어온다."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"ANI-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "poisson_ratio": 0.3,
            "density": 7850,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    made = client.post(
        "/api/test-runs/import",
        json={
            "sample_id": sample["id"],
            "test_type": "tensile",
            "values": _rows(),
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert made.status_code == 200, made.text
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]
    assert len(runs) == 3
    return {"material_id": material["id"], "run_ids": [run["id"] for run in runs]}


def _adopt_measured(db: Session, run_id: str, value: float) -> None:
    """폭 채널이 있는 장비를 흉내 낸다 — 채택된 결과에 `r_value` 가 있는 상태.

    곡선 파일은 안 만든다. 구성원 수집기는 스칼라만 읽고 이 시험의 곡선은 안 연다 —
    여기서 재려는 것은 「어느 쪽에서 값을 집어 오나」 이지 처리 자체가 아니다.
    """
    run = db.get(TestRun, uuid.UUID(run_id))
    assert run is not None
    result = ProcessingResult(
        test_run_id=run.id,
        source_curve_key="main",
        steps_snapshot=[{"plugin": "anisotropy.r_value", "options": {}}],
        stages=[],
        scalars=[{"key": "r_value", "label": "소성 변형비 r", "value": value, "si_unit": "1"}],
        storage_path="none",
        row_count=0,
        sha256="0" * 64,
        byte_size=0,
        columns=[],
    )
    db.add(result)
    db.flush()
    run.adopted_result_id = result.id
    db.commit()


def _group(client: TestClient, headers: dict[str, str], run_ids: list[str]) -> dict[str, Any]:
    made = client.post(
        "/api/groups",
        json={"plugin_id": "anisotropy.r_family", "run_ids": run_ids, "options": {}},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def test_후보를_안_거른다(client: TestClient, admin_headers: dict[str, str]) -> None:
    """채택된 결과가 없어도 사람이 적었을 수 있다 — 화면에서 미리 빼면 고를 길이 없다."""
    kinds = client.get("/api/groups/kinds?applies_to=tensile", headers=admin_headers).json()
    found = next(one for one in kinds if one["id"] == "anisotropy.r_family")
    assert found["needs"] == "summary"
    assert found["makes_card"] is True


def _tiers(db: Session, card_id: str) -> dict[str, int]:
    """값마다 매겨진 등급. **응답에 없다** — 덱 각주로 나가는 값이라 여기서 직접 잰다."""
    row = db.get(PropertyCard, uuid.UUID(card_id))
    assert row is not None
    return card_tiers.value_tiers(row)


def test_표로_적은_r값이_묶음과_카드가_된다(
    client: TestClient, db: Session, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    body = _group(client, admin_headers, imported["run_ids"])

    # ① 방향은 **시편에서** 왔다 — 조건에도 결과에도 없는 값이다.
    assert body["values"]["r_0"] == pytest.approx(1.8)
    assert body["values"]["r_45"] == pytest.approx(1.4)
    assert body["values"]["r_90"] == pytest.approx(2.1)
    assert body["values"]["r_bar"] == pytest.approx(1.675)
    assert body["values"]["stated_count"] == 3

    # ② 카드 — **방향이 비어 있다.** 셋 중 하나를 적으면 그 방향의 물성으로 읽힌다.
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": body["id"], "label": "이방성"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    made = card.json()
    assert made["orientation"] is None
    assert "anisotropy" in made["blocks"]
    values = made["blocks"]["anisotropy"]["values"]
    assert values["r_bar"] == pytest.approx(1.675)
    assert values["hill_g"] == pytest.approx(1 / (1 + 1.8))

    # ③ 사람이 적은 값이라 **잰 값으로 안 센다.** 등급이 거기서 갈린다.
    assert values["r_bar_source"] == "manual"
    assert _tiers(db, made["id"])["anisotropy.r_bar"] == 4


def test_잰_값이_있으면_그쪽을_쓴다(
    client: TestClient, db: Session, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    """폭 신율계가 달린 장비의 시험은 채택된 결과에 r값이 있다. 같은 묶음이 둘을
    가리지 않고 받되, 카드의 출처는 **가장 약한 쪽**을 따른다."""
    runs = {
        row.record_name: str(row.id)
        for row in db.scalars(
            select(TestRun).where(
                TestRun.id.in_([uuid.UUID(one) for one in imported["run_ids"]])
            )
        )
    }
    # 세 시험 모두 곡선에서 잰 것으로 바꾼다 — 표의 값과 다른 숫자를 넣어 **어느
    # 쪽을 집었는지** 값으로 드러나게 한다.
    for name, run_id in runs.items():
        measured = 1.9 if "_MD_" in name else 1.5 if "_DD_" in name else 2.2
        _adopt_measured(db, run_id, measured)

    body = _group(client, admin_headers, list(runs.values()))
    assert body["values"]["r_0"] == pytest.approx(1.9)
    assert body["values"]["stated_count"] == 0

    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": body["id"], "label": "이방성(잰 값)"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    values = card.json()["blocks"]["anisotropy"]["values"]
    assert values["r_bar_source"] == "measured"
    # 표본 셋이면 1등급이다(ADR 0008 과 같은 문턱).
    assert _tiers(db, card.json()["id"])["anisotropy.r_bar"] == 1


def test_한_방향이_빠지면_묶지_않는다(
    client: TestClient, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    """**옆 방향으로 대신하지 않는다.** 그렇게 나온 r̄ 에는 그 사실이 어디에도 없다."""
    got = client.post(
        "/api/groups",
        json={
            "plugin_id": "anisotropy.r_family",
            "run_ids": imported["run_ids"][:2],
            "options": {},
        },
        headers=admin_headers,
    )
    assert got.status_code == 422, got.text
    assert "방향" in got.json()["error"]["message"]


def test_r값이_아무_데도_없으면_어느_시험인지_말한다(
    client: TestClient, db: Session, admin_headers: dict[str, str], admin: Any
) -> None:
    """채택된 결과도 없고 표에도 안 적혔다 — 사람이 다음에 무엇을 할지 알아야 한다."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"ANI-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    blank = client.post(
        "/api/test-runs/import",
        json={
            "sample_id": sample["id"],
            "test_type": "tensile",
            # r값 열이 아예 없는 표 — 시험만 생긴다.
            "values": ["시편\t방향", "1\tMD", "2\tDD", "3\tTD"],
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert blank.status_code == 200, blank.text
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]

    got = client.post(
        "/api/groups",
        json={
            "plugin_id": "anisotropy.r_family",
            "run_ids": [one["id"] for one in runs],
            "options": {},
        },
        headers=admin_headers,
    )
    assert got.status_code == 422, got.text
    message = got.json()["error"]["message"]
    assert "r_value" in message and "표로 시험 입력" in message
