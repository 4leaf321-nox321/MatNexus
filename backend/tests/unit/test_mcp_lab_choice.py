"""MCP 가 받는 부서 추천을 옮길 때 **「모름」 을 「없음」 으로 바꾸지 않는다**(ADR 0069 C).

판단은 `mcp_server/lab_choice.py` 에 있다 — `server.py` 는 mcp SDK 를 불러 이 스위트가 못 연다.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server"))

import lab_choice  # noqa: E402

ANSWER = {
    "state": "ok",
    "message": "",
    "labs": [
        {
            "workspace_slug": "mech-lab",
            "workspace_name": "기계시험팀",
            "items": [0],
            "equipment": [{"name": f"UTM {n}"} for n in range(7)],
        },
        # TestScope 부서와 이름이 같은 MatNexus 부서가 없으면 slug 가 비어 고를 수 없다.
        {
            "workspace_slug": None,
            "workspace_name": "외부 시험소",
            "items": [0],
            "equipment": [],
        },
    ],
    "unresolved": [
        {"item": 1, "text": "점착력", "reason": "물성으로 못 풂", "candidates": []}
    ],
}


def test_추천을_읽을_모양으로_옮기고_장비는_앞의_다섯만() -> None:
    got = lab_choice.shaped(ANSWER)
    assert got["state"] == "ok"
    assert [(one["slug"], one["name"], one["items"]) for one in got["labs"]] == [
        ("mech-lab", "기계시험팀", [0]),
        (None, "외부 시험소", [0]),
    ]
    assert got["labs"][0]["equipment"] == [f"UTM {n}" for n in range(5)]
    assert got["unresolved"] == [{"item": 1, "text": "점착력", "reason": "물성으로 못 풂"}]


def test_물었을_때만_있다_없다를_말하고_못_물었으면_모름() -> None:
    shown = lab_choice.shaped(ANSWER)
    assert lab_choice.is_suggested("mech-lab", shown) is True
    assert lab_choice.is_suggested("chem-lab", shown) is False
    # 연결 없음 · 못 닿음 · 답을 못 읽음 — 셋 다 「모름」 이다(거짓이 아니다).
    for state in ("off", "error"):
        assert lab_choice.is_suggested("mech-lab", {"state": state, "labs": []}) is None
    broken = lab_choice.shaped({"error": "502"})
    assert broken["state"] == "error"
    assert lab_choice.is_suggested("mech-lab", broken) is None
    # slug 없는 부서(고를 수 없는 것)가 빈 slug 와 맞아떨어지지 않는다.
    assert lab_choice.is_suggested("", shown) is False


def test_서버가_막는_길이는_미리_자른다() -> None:
    items = [{"property_hint": "가" * 300, "count": 2}] * 25 + ["줄이 아님"]
    body = lab_choice.asked(items)
    assert len(body["items"]) == lab_choice.MAX_ITEMS
    assert len(body["items"][0]["property_hint"]) == lab_choice.MAX_HINT
    assert body["items"][0] == {
        "test_type_key": None,
        "property_hint": "가" * lab_choice.MAX_HINT,
    }
