"""MCP 서버의 **순수 도우미** — 이름 해소 · 기본 칸의 근거 · 문헌 연결 교체(2026-11-15).

`server.py` 는 mcp SDK 를 불러 이 스위트가 못 연다. 다른 판단(`lab_choice` ·
`retry_plan`)은 이웃 모듈로 떼어 뒀지만 이 셋은 `server.py` 안에 있다 — 그래서 **그
함수들만 소스에서 꺼내** 따로 돌린다. 꺼낼 이름이 없어지면(이름을 바꾸거나 옮기면) 여기서
먼저 멈춘다.

    이름 해소       포함 검색에 하나만 걸려도 이름이 정확히 같지 않으면 쓰기는 되묻는다
                    (「SUS304」 에 `SUS304L 0.5t` 하나만 걸리면 묻지 않고 그 재료에 적었다)
    기본 칸 근거    밀도 · 푸아송비가 서버의 `column_sources`(출처 · 근거 · 문헌 등급)를 싣는다
                    (문헌 등급 4 의 밀도가 등급 없이 `declared:material` 로 나갔다)
    연결 교체       미리보기가 지금 연결을 갈아 끼우는지 말한다(`PUT` 은 재료당 하나라 교체다)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

SERVER = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"

#: 꺼내 돌리는 것 — 표준 라이브러리 밖을 부르지 않는 것만.
WANTED = (
    "_CODE_SHAPE",
    "_NEAR_NOTE",
    "_code_form",
    "_exact_rows",
    "_name_choice",
    "_with_resolution",
    "_basic_value",
    "_link_change",
)


def _name_of(node: ast.stmt) -> str | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _load() -> dict[str, Any]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    picked = [node for node in tree.body if _name_of(node) in WANTED]
    missing = sorted(set(WANTED) - {_name_of(node) for node in picked})
    assert not missing, f"server.py 에 없는 도우미: {missing}"
    # 표기는 server.py 처럼 문자열로 둔다 — `Context` 같은 이름을 여기서 풀 수 없다.
    future = ast.parse("from __future__ import annotations").body
    module = ast.Module(body=[*future, *picked], type_ignores=[])
    code = compile(module, str(SERVER), "exec", dont_inherit=True)
    space: dict[str, Any] = {"re": re, "Any": Any}
    exec(code, space)
    return space


S = _load()

ROWS = [{"id": "a", "code": "M-000012", "record_name": "SUS304L 0.5t", "alias": None}]


# ── 이름 해소 ──────────────────────────────────────────────────────────────────


def test_정확히_같지_않은_하나는_읽기만_그것으로_보고_쓰기는_되묻는다() -> None:
    fields = ("record_name", "alias")
    assert S["_name_choice"]("SUS304", ROWS, fields, write=False) == ("near", ROWS)
    # 쓰기 — 걸린 것이 하나여도 이름이 다르면 고르게 한다.
    assert S["_name_choice"]("SUS304", ROWS, fields, write=True) == ("ask", ROWS)


@pytest.mark.parametrize(
    "asked", ["SUS304L 0.5t", "  sus304l 0.5T ", "M-000012", "m12", "M-12"]
)
def test_이름_번호가_정확히_같으면_쓰기도_그것으로_본다(asked: str) -> None:
    got = S["_name_choice"](asked, ROWS, ("record_name", "alias"), write=True)
    assert got == ("exact", ROWS)


def test_별칭이_정확히_같아도_같은_것이다() -> None:
    rows = [{"id": "a", "code": "M-000001", "record_name": "STS304_1.0", "alias": "SUS304"}]
    assert (
        S["_name_choice"]("sus304", rows, ("record_name", "alias"), write=True)[0] == "exact"
    )


def test_여럿_중_정확히_같은_것_하나를_고른다() -> None:
    rows = [
        {"id": "a", "code": "M-000001", "record_name": "SUS304"},
        {"id": "b", "code": "M-000002", "record_name": "SUS304L"},
    ]
    verdict, picked = S["_name_choice"]("SUS304", rows, ("record_name",), write=True)
    assert (verdict, [one["id"] for one in picked]) == ("exact", ["a"])


def test_정확히_같은_것이_여럿이면_그것들만_후보로_되묻는다() -> None:
    rows = [
        {"id": "a", "code": "M-000001", "record_name": "DP600", "alias": None},
        {"id": "b", "code": "M-000002", "record_name": "DP600_1.2", "alias": "DP600"},
        {"id": "c", "code": "M-000003", "record_name": "DP600_1.6", "alias": None},
    ]
    verdict, picked = S["_name_choice"]("DP600", rows, ("record_name", "alias"), write=False)
    assert (verdict, [one["id"] for one in picked]) == ("ask", ["a", "b"])


def test_여럿이_걸리고_같은_것이_없으면_읽기도_되묻고_없으면_없다() -> None:
    rows = [{"id": "a", "record_name": "SUS304L"}, {"id": "b", "record_name": "SUS304H"}]
    assert S["_name_choice"]("SUS304", rows, ("record_name",), write=False)[0] == "ask"
    assert S["_name_choice"]("SUS304", [], ("record_name",), write=False) == ("none", [])


def test_번호_꼴은_다른_종류의_번호와_섞이지_않는다() -> None:
    # 시편 번호(P-…)로 시험 목록이 그 시편의 시험 하나를 주면 — 그 시험의 번호가 아니다.
    rows = [{"id": "r", "code": "T-000007", "record_name": "RUN_01"}]
    assert S["_code_form"]("p7") == "P-000007"
    assert S["_name_choice"]("P-000007", rows, ("record_name",), write=True)[0] == "ask"
    assert S["_code_form"]("SUS304") is None


def test_해소_메모는_답에_붙고_여럿이면_목록이다() -> None:
    one = [{"resolved_from": "SUS304", "matched": {"id": "a"}}]
    got = S["_with_resolution"]({"id": "a", "name": "x"}, one)
    assert got["resolved_from"] == "SUS304"
    assert got["matched"] == {"id": "a"}
    assert got["name"] == "x"
    two = [*one, {"resolved_from": "RUN", "matched": {"id": "r"}}]
    got = S["_with_resolution"]({"plan": []}, two)
    assert got["resolved_from"] == ["SUS304", "RUN"]
    # 도구가 같은 이름의 칸을 이미 쓰면 덮지 않고 한 칸에 담는다.
    got = S["_with_resolution"]({"matched": "contains"}, one)
    assert got["matched"] == "contains"
    assert got["resolution"]["resolved_from"] == "SUS304"
    # 메모가 없거나 dict 가 아니면 그대로.
    assert S["_with_resolution"]({"a": 1}, []) == {"a": 1}
    assert S["_with_resolution"]("text", one) == "text"


# ── 기본 칸의 근거 ─────────────────────────────────────────────────────────────


def test_문헌_등급_4의_밀도는_등급과_추정_표지를_든다() -> None:
    sources = {
        "density": {"source": "literature", "reference": "ASM v1", "catalog_tier": 4},
    }
    got = S["_basic_value"]("density", 7900.0, "kg/m3", sources, note="공칭값")
    assert got["origin"] == "declared:literature+catalog4"
    assert got["source_document"] == "ASM v1"
    assert got["catalog_tier"] == 4
    assert "tier 4" in got["caveat"]
    assert got["caveat"].endswith("공칭값")
    assert (got["value"], got["unit"]) == (7900.0, "kg/m3")


def test_근거가_없으면_출처_모름이다() -> None:
    for sources in ({}, None, {"density": {"source": "", "reference": ""}}):
        got = S["_basic_value"]("density", 7850.0, "kg/m3", sources)
        assert got["origin"] == "declared:material"
        assert got["source_document"] is None
        assert "출처 모름" in got["caveat"]


def test_추정_출처는_받아_온_문헌_등급이_없을_때만_tier_4다() -> None:
    estimate = {"poisson_ratio": {"source": "estimate", "reference": "사내 가정"}}
    got = S["_basic_value"]("poisson_ratio", 0.3, "1", estimate)
    assert got["origin"] == "declared:estimate"
    assert "tier 4" in got["caveat"]
    # 받아 온 문헌 등급이 있으면 그것이 등급이다(백엔드 `tiers.declared_tier`).
    graded = {"poisson_ratio": {"source": "estimate", "reference": "x", "catalog_tier": 2}}
    got = S["_basic_value"]("poisson_ratio", 0.3, "1", graded)
    assert "tier 4" not in got["caveat"]
    standard = {"poisson_ratio": {"source": "standard", "reference": "KS D 3698"}}
    got = S["_basic_value"]("poisson_ratio", 0.3, "1", standard)
    assert got["origin"] == "declared:standard"
    assert "catalog_tier" not in got
    assert got["caveat"] == ""


# ── 문헌 연결 교체 ─────────────────────────────────────────────────────────────


def test_다른_문헌_재료에_이어져_있으면_갈아_끼운다고_말한다() -> None:
    current = {"catalog_material_id": "old", "name": "SUS304 (A)", "value_count": 12}
    got = S["_link_change"](current, "new")
    assert got == {
        "replaces": {"catalog_material_id": "old", "name": "SUS304 (A)", "value_count": 12}
    }


def test_안_이어져_있거나_같은_것이면_바뀌는_것이_없다() -> None:
    empty = {"catalog_material_id": None, "name": None, "value_count": None}
    assert S["_link_change"](empty, "new") == {"replaces": None}
    same = {"catalog_material_id": "new", "name": "x"}
    assert S["_link_change"](same, "new") == {"replaces": None, "already_linked": True}


def test_지금_연결을_못_읽었으면_없음으로_단정하지_않는다() -> None:
    got = S["_link_change"]({"error": "권한이 없습니다"}, "new")
    assert "replaces" not in got
    assert "권한이 없습니다" in got["replaces_unknown"]
    assert "replaces_unknown" in S["_link_change"](None, "new")
