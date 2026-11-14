"""MCP 의 만들기 도구가 보내는 **그 모양 그대로** API 가 받는가.

`create_material` · `create_sample` · `create_specimen` 은 인자 이름에 단위를
박아 두고(`spec_thickness_mm` · `density_kg_m3` · `thickness_mm`) 서버에는 값과
단위를 함께 보낸다. 화면과 다른 단위로 보내는 자리라, 서버가 그 단위 문자열을
모르면 **만들기가 통째로 실패한다** — 그런데 MCP 로 불러 보기 전에는 안 드러난다.

여기서 지키는 것은 그 계약이다: 밀도는 `kg/m3` 로, 길이는 `mm` 로 보내면
받아 주고, 저장은 SI 로 된다.

`mcp_server` 자체는 이 스위트가 부를 수 없다(mcp SDK 가 backend 가상환경에
없다). 그래서 **도구가 만드는 본문을 여기 그대로 적고**, 어긋나면 이 시험이
물게 한다. 판단 쪽은 `tests/unit/test_mcp_term_gate.py` 가 본다.

손으로 적은 본문은 도구가 인자를 **싣는지**는 못 본다(VOC 42). 그래서 아래 「도구가 실제로
싣는 것」 은 `server.py` 에서 도구 함수만 떼어 가짜 백엔드 위에서 돌린다.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

#: `create_material` 이 만드는 본문(ADR 0032 문을 이미 지난 값들).
MATERIAL: dict[str, Any] = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": None,
    "spec_thickness": 1.2,
    "spec_thickness_unit": "mm",
    "alias": None,
    "note": None,
    "workspace_slug": None,
}

#: `create_sample` 이 만드는 본문.
SAMPLE: dict[str, Any] = {
    "lot_no": "L-2026-09",
    "alias": None,
    "manufacturer": None,
    "distributor": None,
    "primary_vendor": None,
    "sales_type": None,
    "production_date": "2026-09-01",
    "density": 7850.0,
    "density_unit": "kg/m3",
    "note": None,
}

#: `create_specimen` 이 만드는 본문.
SPECIMEN: dict[str, Any] = {
    "orientation": "MD",
    "standard": None,
    "thickness": 1.2,
    "width": 12.5,
    "gauge_length": 50.0,
    "length_unit": "mm",
    "note": None,
}


def test_재료_시료_시편을_그_본문으로_만든다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    material = client.post("/api/materials", json=MATERIAL, headers=admin_headers)
    assert material.status_code == 201, material.text
    material_id = material.json()["id"]

    sample = client.post(
        f"/api/materials/{material_id}/samples", json=SAMPLE, headers=admin_headers
    )
    assert sample.status_code == 201, sample.text
    # **응답은 SI(kg/m³)다**(2026-09-24). 도구가 `kg/m3` 을 적어 보낸 7850 이 그대로 돌아와야
    # 한다 — 7.85e-9 가 오면 서버가 단위를 무시하고 화면 단위로 읽은 것이다(1e12 배, 밀도는
    # 응력을 나누는 데 쓰이지 않아 한참 뒤에야 드러난다).
    assert sample.json()["density"] == pytest.approx(7850.0)
    assert sample.json()["density_unit"] == "kg/m3"

    specimen = client.post(
        f"/api/samples/{sample.json()['id']}/specimens",
        json=SPECIMEN,
        headers=admin_headers,
    )
    assert specimen.status_code == 201, specimen.text
    made = specimen.json()
    assert made["orientation"] == "MD"
    # **응답은 SI(m)다**(2026-09-24). 도구가 mm 로 적어 보낸 1.2 · 50 이 0.0012 · 0.05 로
    # 돌아와야 한다 — `length_unit` 이 안 읽히면 1.2 m · 50 m 가 되어 울타리(1 m)가 거절한다.
    assert made["length_unit"] == "m"
    assert made["thickness"] == pytest.approx(0.0012)
    assert made["gauge_length"] == pytest.approx(0.05)


def test_미리보기는_이름과_닮은_이름을_준다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """`create_material(dry_run=True)` 가 사람에게 보여 주는 것. **이름은 서버가
    짓는다** — 여기서 화면·MCP 가 각자 조립하면 세 이름이 갈라진다."""
    made = client.post("/api/materials", json=MATERIAL, headers=admin_headers)
    assert made.status_code == 201, made.text

    preview = client.post(
        "/api/materials/preview-name",
        json={
            "grade": "SECC",
            "details": None,
            "spec_thickness": 1.2,
            "spec_thickness_unit": "mm",
        },
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["record_name"] == made.json()["record_name"]
    # 같은 이름이 이미 있다 — 도구는 이것을 「그 재료를 쓰세요」 로 옮긴다.
    assert body["taken"] is True


def test_부서를_지정한_미리보기도_같은_길로_간다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """부서는 **쿼리**로 간다(본문이 아니다). MCP 는 경로에 붙여 보내므로, 그
    자리가 바뀌면 조용히 남의 부서 이름과 대조하게 된다."""
    got = client.post(
        "/api/materials/preview-name?workspace_slug=metal",
        json={"grade": "SECC", "spec_thickness": 1.2, "spec_thickness_unit": "mm"},
        headers=admin_headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["taken"] is False


# ── 도구가 실제로 싣는 것 (VOC 42, 2026-11-14) ─────────────────────────────────
#
# API 는 `extrapolate_to` 를 받는데 `create_card_from_tests` 가 그 인자를 안 받아, 외삽 카드를
# MCP 로 못 만들었다. 같은 꼴이 카드 · 처리 · 덱 쪽에 14곳 있었다. 위처럼 본문을 손으로 적으면
# 도구가 인자를 빠뜨려도 안 문다 — 여기서는 **도구의 진짜 코드**를 돌린다. 준 인자는 실리고, 안
# 준 인자는 **안 실린다**(전과 같은 요청이다).

SERVER = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"

#: 도구와 함께 떼어 오는 순수 도우미.
_HELPERS = ("_curve_basis", "_complete")
#: 함께 읽는 상수 — 인자 기본값이 정의할 때 읽힌다(`units=DEFAULT_DECK_UNITS`).
_CONSTANTS = ("DEFAULT_DECK_UNITS", "MAX_LIMIT")


@cache
def _server() -> ast.Module:
    return ast.parse(SERVER.read_text(encoding="utf-8"))


class _Backend:
    """가짜 백엔드 — 부른 것을 적어 둔다. 쿼리는 `_get` · `_send` 처럼 `None` 을 뺀다."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    def _record(self, method: str, path: str, body: Any, query: dict[str, Any] | None) -> Any:
        given = {key: value for key, value in (query or {}).items() if value is not None}
        self.calls.append({"method": method, "path": path, "body": body, "query": given})
        return self.answers.get(path, {"id": "made"})

    async def get(self, ctx: object, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._record("GET", path, None, params)

    async def send(
        self,
        ctx: object,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
        files: object = None,
    ) -> Any:
        return self._record(method, path, body, params)

    def sent(self, path: str) -> dict[str, Any]:
        """그 경로로 보낸 마지막 호출."""
        found = [one for one in self.calls if one["path"] == path]
        assert found, f"{path} 를 안 불렀다: {self.calls}"
        return found[-1]


def _tool(name: str, backend: _Backend) -> Callable[..., Any]:
    """`server.py` 에서 그 도구만 떼어(데코레이터는 뗀다) 가짜 백엔드 위에 올린다."""
    tree = _server()
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in (name, *_HELPERS)
    ]
    assert name in {node.name for node in nodes}, f"server.py 에 {name} 이 없다"
    for node in nodes:
        node.decorator_list = []
    constants = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in _CONSTANTS
    }
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    scope: dict[str, Any] = {
        "Any": Any,
        **constants,
        "_get": backend.get,
        "_get_text": backend.get,
        "_send": backend.send,
    }
    exec(compile(module, str(SERVER), "exec"), scope)
    tool = scope[name]
    return lambda **kwargs: asyncio.run(tool(None, **kwargs))


#: `create_card_from_tests` 를 실제로 만들게(dry_run=False) 부르는 인자.
_CARD = {
    "material_id": "m-1",
    "test_type": "tensile",
    "orientation": "MD",
    "label": "충돌용",
    "family": "swift",
    "dry_run": False,
}
_FAMILIES = {"/fitting/families": [{"key": "swift", "block": "hardening"}]}


def test_시험_카드는_외삽과_혼합을_준_때만_싣는다() -> None:
    given = _Backend(_FAMILIES)
    _tool("create_card_from_tests", given)(
        **_CARD, extrapolate_to=1.0, blend_with="voce", blend_weight=0.6, note="외삽 1.0"
    )
    body = given.sent("/fitting/cards")["body"]
    assert body["extrapolate_to"] == 1.0
    assert (body["blend_with"], body["blend_weight"]) == ("voce", 0.6)
    assert body["note"] == "외삽 1.0"

    omitted = _Backend(_FAMILIES)
    _tool("create_card_from_tests", omitted)(**_CARD)
    body = omitted.sent("/fitting/cards")["body"]
    assert not {"extrapolate_to", "blend_with", "blend_weight", "note"} & set(body)
    # 소성 표 줄이기(기본 곡률 50점)는 그대로다.
    assert (body["resample_method"], body["resample_points"]) == ("curvature", 50)


def test_식_없이_외삽을_주면_보내기_전에_멈춘다() -> None:
    """서버는 식 없는 외삽을 거절하지만 식 없는 혼합은 **조용히 뺀다** — 도구가 먼저 말한다."""
    extras: list[dict[str, Any]] = [
        {"extrapolate_to": 1.0},
        {"blend_with": "voce", "blend_weight": 0.5},
    ]
    for extra in extras:
        backend = _Backend({})
        got = _tool("create_card_from_tests", backend)(**{**_CARD, "family": None, **extra})
        assert "error" in got
        assert not [one for one in backend.calls if one["method"] == "POST"]


def test_덱_뽑기는_짝_카드와_파단을_준_때만_싣는다() -> None:
    answers = {"/fitting/cards/c-1/export": "*MAT_024", "/fitting/formats": []}
    given = _Backend(answers)
    _tool("render_card_deck", given)(
        card_id="c-1", format="dyna", with_card="c-2", fail_from_elongation=True
    )
    query = given.sent("/fitting/cards/c-1/export")["query"]
    assert (query["with_card"], query["fail_from_elongation"]) == ("c-2", "true")

    omitted = _Backend(answers)
    _tool("render_card_deck", omitted)(card_id="c-1", format="dyna")
    # **전과 같은 요청** — 단위계 기본(mm·N·tonne)까지.
    assert omitted.sent("/fitting/cards/c-1/export")["query"] == {
        "format": "dyna",
        "units": "mm_n_tonne",
    }


def test_카드_목록은_offset_과_거르기를_준_때만_싣는다() -> None:
    answers = {"/fitting/cards": {"items": [], "total": 0}}
    given = _Backend(answers)
    _tool("list_cards", given)(offset=40, test_type="none", owner="none")
    query = given.sent("/fitting/cards")["query"]
    assert (query["offset"], query["test_type_key"], query["owner"]) == (40, "none", "none")

    omitted = _Backend(answers)
    _tool("list_cards", omitted)()
    assert omitted.sent("/fitting/cards")["query"] == {"limit": 20}


def test_처리_미리보기는_축과_단계를_쿼리로_싣는다() -> None:
    """`x` · `y` · `stage` 는 본문이 아니라 **쿼리**다(`POST /processing/preview?x=…`)."""
    steps = [{"plugin": "tensile.elastic_modulus", "options": {}}]
    given = _Backend({})
    _tool("run_processing", given)(
        test_run_id="r-1", steps=steps, x="strain", y="stress_true", stage=0
    )
    sent = given.sent("/processing/preview")
    assert sent["query"] == {"x": "strain", "y": "stress_true", "stage": 0}
    assert not {"x", "y", "stage"} & set(sent["body"])

    omitted = _Backend({})
    _tool("run_processing", omitted)(test_run_id="r-1", steps=steps)
    assert omitted.sent("/processing/preview")["query"] == {}


def test_일괄_처리는_레시피_키만_보내_서버가_단계를_채우고_미리보기도_서버가_돈다() -> None:
    """VOC 45(2026-11-14) — 전에는 MCP 가 레시피를 읽어 단계를 채워 보냈고(그 사이에 레시피가
    바뀌면 다른 판), 미리보기는 서버를 안 부르고 건수만 셌다."""
    backend = _Backend({"/processing/batch": {"items": [], "failed": 0}})
    run = _tool("run_batch_processing", backend)
    answer = run(test_run_ids=["t1", "t2"], recipe_key="proc_line")
    sent = backend.sent("/processing/batch")["body"]
    assert "steps" not in sent  # 서버가 채운다
    assert sent["recipe_key"] == "proc_line" and sent["dry_run"] is True
    assert sent["curves"] == "first"
    # 레시피를 따로 읽지 않는다.
    assert [one["path"] for one in backend.calls] == ["/processing/batch"]
    assert answer["dry_run"] is True

    steps = [{"plugin": "tensile.strength", "options": {}}]
    run(test_run_ids=["t1"], steps=steps, dry_run=False)
    sent = backend.sent("/processing/batch")["body"]
    assert sent["steps"] and sent["dry_run"] is False
