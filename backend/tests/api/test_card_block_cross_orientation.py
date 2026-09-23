"""화면에서 만든 항목란도 **방향을 가로지른다고 말할 수 있다** (ADR 0034).

카드 한 장은 방향 하나다. 세 방향을 함께 써야 나오는 값(r̄ 같은)은 그 규칙의
예외인데, 예외를 켜는 선언을 **코드로 만든 블록만** 할 수 있었다. 그래서 관리자가
화면에서 「세 방향을 합친 값」 항목란을 만들면 만들기는 되고, **그걸 든 카드를
저장할 때 422 로 막혔다** — 왜 막히는지는 화면 어디에도 없었다.

여기서 지키는 것:

    켜면 방향 검사를 면제받는다      세 방향이 섞인 묶음에서 카드가 만들어진다
    그 카드에는 방향이 없다          셋 중 하나를 적으면 그 방향의 물성으로 읽힌다
    끄면 그대로 막힌다               예외는 선언한 것에만 열린다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types
from matcore import cards, registry

#: 시험이 만드는 항목란 키. 내장·확장과 겹치지 않는 이름이라야 한다 — 겹치면
#: 내장 보호에 걸려 이 시험이 무엇을 재는지와 무관한 이유로 빨개진다.
BLOCK = "block_under_test"

#: 이 시험만 쓰는 묶음. **화면에서 만든 항목란에 값을 넣는다** — 카드로 가는 길이
#: 묶음뿐이라 그 길을 그대로 지나가 본다.
PLUGIN = "test_only.cross_block"

HEADER = "시편\t방향\tr_value"
R_OF = {"MD": 1.8, "DD": 1.4, "TD": 2.1}


@pytest.fixture(autouse=True)
def _plugin() -> Any:
    """세 방향을 받아 화면 항목란 하나를 채우는 묶음."""

    def card(
        values: dict[str, float], detail: dict[str, Any], warnings: list[str]
    ) -> dict[str, Any]:
        return {BLOCK: {"values": {"first_value": float(values.get("mean") or 0.0)}}}

    registry.register(
        id=PLUGIN,
        kind="grouping",
        label="시험용 세 방향 묶음",
        applies_to=("tensile",),
        makes_values=(),
        members={
            "from": "measured_or_stated",
            "values": ["r_value"],
            "specimen": ["orientation"],
        },
        card=card,
        version="1",
    )(lambda members, **options: _mean(members))
    yield
    # **레지스트리는 프로세스에 하나뿐이다.** 남겨 두면 다음 시험의 묶음 목록에
    # 이것이 끼어 든다 — `registry.clear()` 는 내장까지 지우므로 이것만 뺀다.
    registry._REGISTRY.pop(PLUGIN, None)
    cards.load_builtin()
    for key in cards.installed():
        cards.uninstall(key)


def _mean(members: list[Any]) -> Any:
    from matcore.groups import GroupOutcome

    values = [float(one.values["r_value"]) for one in members]
    return GroupOutcome(
        values={"mean": sum(values) / len(values)},
        detail={},
        warnings=[],
        used=[one.label for one in members],
    )


def _block(client: TestClient, headers: dict[str, str], *, crosses: bool) -> dict[str, Any]:
    made = client.post(
        "/api/fitting/block-definitions",
        json={
            "key": BLOCK,
            "label": "세 방향을 합친 값",
            "produces": [{"key": "first_value", "label": "첫 값", "si_unit": "1"}],
            "measured": True,
            "cross_orientation": crosses,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _runs(client: TestClient, db: Session, headers: dict[str, str]) -> list[str]:
    """방향이 다른 시험 셋. 표로 적은 r값으로 들어온다(폭 채널 없는 장비)."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"XOR-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
        },
        headers=headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    rows = [HEADER] + [
        f"{index}\t{orientation}\t{value}"
        for index, (orientation, value) in enumerate(R_OF.items(), start=1)
    ]
    made = client.post(
        "/api/test-runs/import",
        json={
            "sample_id": sample["id"],
            "test_type": "tensile",
            "values": rows,
            "create_missing": True,
        },
        headers=headers,
    )
    assert made.status_code == 200, made.text
    listed = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=headers
    ).json()["items"]
    return [one["id"] for one in listed]


def _group(client: TestClient, headers: dict[str, str], run_ids: list[str]) -> str:
    made = client.post(
        "/api/groups",
        json={"plugin_id": PLUGIN, "run_ids": run_ids, "options": {}},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def test_켜면_방향이_섞여도_카드가_된다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """**선언이 예외를 연다.** 카드를 만드는 쪽의 판단이 아니라 항목란의 선언이다."""
    made = _block(client, admin_headers, crosses=True)
    assert made["cross_orientation"] is True
    # 레지스트리에 그대로 얹혔나 — 카드 만드는 쪽이 읽는 것이 이 자리다.
    assert cards.block(BLOCK).meta["cross_orientation"] is True

    group_id = _group(client, admin_headers, _runs(client, db, admin_headers))
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": group_id, "label": "세 방향"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    # **방향이 비어 있다.** 셋 중 하나를 적으면 그 방향의 물성으로 읽힌다.
    assert card.json()["orientation"] is None


def test_안_켜면_그대로_막힌다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """예외는 선언한 것에만 열린다 — 안 그러면 방향 하나의 물성이 조용히 섞인다."""
    _block(client, admin_headers, crosses=False)
    group_id = _group(client, admin_headers, _runs(client, db, admin_headers))
    got = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": group_id, "label": "세 방향"},
        headers=admin_headers,
    )
    assert got.status_code == 422, got.text
    assert "방향" in got.json()["error"]["message"]


def test_켜고_끄면_판이_오른다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """값의 모양은 안 바뀌지만 **그 카드가 무엇의 카드인지**가 바뀐다 — 경계가
    보이려면 판이 올라야 한다."""
    made = _block(client, admin_headers, crosses=False)
    got = client.patch(
        f"/api/fitting/block-definitions/{made['id']}",
        json={"cross_orientation": True},
        headers=admin_headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["cross_orientation"] is True
    assert got.json()["version"] == made["version"] + 1
    assert cards.block(BLOCK).meta["cross_orientation"] is True
