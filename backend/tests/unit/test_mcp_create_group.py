"""MCP `create_group` — **묶음을 만드는 쓰기 도구의 미리보기**(2026-11-15, ADR 0087 후속).

`server.py` 는 mcp SDK 를 불러 이 스위트가 못 연다 — `test_mcp_server_pure.py` 처럼 그 함수들만
소스에서 꺼내, 백엔드 응답을 흉내 낸 `_get` · `_send` 로 돌린다.

    모르는 묶음      고를 수 있는 묶음(`kinds` — 구성원 조건 · 옵션)을 대며 거절한다
    구성원 조건      시험 종류마다(`needs_by_type`) 채택 결과 · 대표 마스터커브 · 보류 ·
                     재료 하나 · 최소 수 · 모르는 옵션을 미리 본다 — 계산은 안 한다
    만들기           막히는 것이 있으면 보내지 않는다. 없으면 `POST /groups` 하나
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

SERVER = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"
WANTED = ("_group_kind", "_group_member", "create_group")

COUPLED = {
    "id": "relaxation.dma_coupled",
    "label": "응력완화 + DMA 마스터커브(짧은 시간 메우기)",
    "applies_to": ["dma_sweep", "stress_relaxation"],
    "needs": "master_curve",
    "needs_by_type": {"stress_relaxation": "adopted_result", "dma_sweep": "master_curve"},
    "min_members": 2,
    "makes_card": True,
    "params": [
        {"name": "poisson_ratio", "label": "푸아송비", "type": "float", "default": None}
    ],
}
RATE = {
    "id": "tensile.rate_family",
    "label": "속도별",
    "applies_to": ["tensile"],
    "needs": "adopted_result",
    "needs_by_type": {},
    "min_members": 2,
    "makes_card": True,
    "params": [],
}


def _run(run_id: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": run_id,
        "record_name": f"{kind}-{run_id}",
        "test_type_key": kind,
        "material_id": "M1",
        "adopted_result_id": None,
        "hold_reason": None,
        "conditions": {"temperature": 296.15},
        **extra,
    }


class _Backend:
    """흉내 낸 백엔드 — GET 경로 → 응답, 보낸 쓰기를 적어 둔다."""

    def __init__(self, runs: list[dict[str, Any]], curves: dict[str, list[Any]]) -> None:
        self.answers: dict[str, Any] = {"/groups/kinds": [COUPLED, RATE]}
        for run in runs:
            self.answers[f"/test-runs/{run['id']}"] = run
        for run_id, rows in curves.items():
            self.answers[f"/viscoelastic/runs/{run_id}/master-curves"] = rows
        self.sent: list[tuple[str, str, Any]] = []

    async def get(self, ctx: Any, path: str, params: Any = None) -> Any:
        return self.answers.get(path, {"error": f"없는 경로: {path}"})

    async def send(self, ctx: Any, method: str, path: str, body: Any = None) -> Any:
        self.sent.append((method, path, body))
        return {
            "id": "G1",
            "plugin_id": body["plugin_id"],
            "plugin_version": "2",
            "members": [],
        }


def _tool(backend: _Backend) -> Any:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    picked = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in WANTED
    ]
    assert sorted(node.name for node in picked) == sorted(WANTED), "server.py 에 없는 함수"
    future = ast.parse("from __future__ import annotations").body
    module = ast.Module(body=[*future, *picked], type_ignores=[])

    class _Mcp:
        @staticmethod
        def tool() -> Any:
            return lambda fn: fn

    async def resolve(ctx: Any, one: str, *, write: bool = False) -> str:
        assert write, "쓰기 도구는 이름을 쓰기로 해소한다"
        return one

    space: dict[str, Any] = {
        "Any": Any,
        "mcp": _Mcp,
        "_get": backend.get,
        "_send": backend.send,
        "_resolve_run": resolve,
    }
    exec(compile(module, str(SERVER), "exec", dont_inherit=True), space)
    return space["create_group"]


def _call(backend: _Backend, **kwargs: Any) -> dict[str, Any]:
    out: dict[str, Any] = asyncio.run(_tool(backend)(None, **kwargs))
    return out


def test_모르는_묶음이면_고를_수_있는_묶음을_대며_거절한다() -> None:
    backend = _Backend([], {})
    out = _call(backend, plugin_id="없는.묶음", test_run_ids=["R1"])
    assert "error" in out
    coupled = next(one for one in out["kinds"] if one["id"] == "relaxation.dma_coupled")
    assert coupled["needs_by_type"] == COUPLED["needs_by_type"]
    assert coupled["params"][0]["name"] == "poisson_ratio"
    assert "needs_by_type" not in next(one for one in out["kinds"] if one["id"] == RATE["id"])


def test_응력완화와_DMA_가_조건을_갖추면_만들_것을_보이고_쓰지_않는다() -> None:
    runs = [
        _run("R1", "stress_relaxation", adopted_result_id="P1"),
        _run("D1", "dma_sweep", conditions={"deformation_mode": "비틀림"}),
    ]
    backend = _Backend(runs, {"D1": [{"id": "C1", "is_primary": True}]})
    out = _call(
        backend,
        plugin_id="relaxation.dma_coupled",
        test_run_ids=["R1", "D1", "R1"],
        options={"poisson_ratio": 0.4},
    )
    assert out["dry_run"] is True and not backend.sent
    assert out["problems"] == [] and out["cautions"] == []
    assert [one["needs"] for one in out["members"]] == ["adopted_result", "master_curve"]
    assert out["members"][1]["deformation_mode"] == "비틀림"
    assert out["will_create"] == {
        "plugin_id": "relaxation.dma_coupled",
        "run_ids": ["R1", "D1"],  # 같은 시험은 한 번만
        "options": {"poisson_ratio": 0.4},
        "note": None,
    }
    assert "확인받은 뒤 dry_run=False" in out["note"]


def test_구성원_조건이_안_맞으면_까닭을_대고_보내지_않는다() -> None:
    runs = [
        _run("R1", "stress_relaxation"),  # 채택 없음
        _run("D1", "dma_sweep"),  # 대표 없음
        _run("C1", "creep", adopted_result_id="P3"),  # 받지 않는 종류
        _run("R2", "stress_relaxation", adopted_result_id="P2", hold_reason="시편 파손"),
        _run("R3", "stress_relaxation", adopted_result_id="P4", material_id="M2"),
    ]
    backend = _Backend(runs, {"D1": [{"id": "X", "is_primary": False}]})
    args = {
        "plugin_id": "relaxation.dma_coupled",
        "test_run_ids": ["R1", "D1", "C1", "R2", "R3"],
        "options": {"nu": 0.4},
    }
    out = _call(backend, **args)
    said = " / ".join(out["problems"])
    for expected in (
        "채택된 처리 결과가 없습니다",
        "대표 마스터커브가 없습니다",
        "받지 않는 시험 종류입니다(creep)",
        "물성 사용 보류 — 시편 파손",
        "재료가 2가지",
        "모르는 옵션입니다: nu — 받는 것: poisson_ratio",
    ):
        assert expected in said, (expected, said)
    refused = _call(backend, **args, dry_run=False)
    assert "error" in refused and refused["problems"] and not backend.sent


def test_시험_종류가_빠지면_말하고_최소_수를_본다() -> None:
    backend = _Backend([_run("R1", "stress_relaxation", adopted_result_id="P1")], {})
    out = _call(backend, plugin_id="relaxation.dma_coupled", test_run_ids=["R1"])
    assert any("dma_sweep 이(가) 없습니다" in one for one in out["cautions"])
    assert any("2건 이상" in one for one in out["problems"])


def test_조건을_갖추면_POST_groups_하나를_보내고_카드로_잇는다() -> None:
    runs = [
        _run("R1", "stress_relaxation", adopted_result_id="P1"),
        _run("D1", "dma_sweep"),
    ]
    backend = _Backend(runs, {"D1": [{"id": "C1", "is_primary": True}]})
    out = _call(
        backend, plugin_id="relaxation.dma_coupled", test_run_ids=["R1", "D1"], dry_run=False
    )
    assert [(method, path) for method, path, _ in backend.sent] == [("POST", "/groups")]
    assert backend.sent[0][2]["run_ids"] == ["R1", "D1"]
    assert out["id"] == "G1"
    assert 'create_card_from_group(group_result_id="G1"' in out["next"]
