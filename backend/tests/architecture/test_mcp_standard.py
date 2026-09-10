"""MCP 가 AI 에게 일러 주는 **표준 순서**가 화면의 것과 같은가.

## 왜 두 벌인가

표준 단계의 정본은 프론트의 `standard.ts` 다 — 사람이 처리 화면에서 쓰는 그
목록이다. MCP 는 백엔드를 거쳐 그것을 읽을 길이 없다(그 목록은 서버에 없다).
그래서 `mcp_server/server.py` 와 안내서가 같은 순서를 **한 번 더 적는다.**

두 벌이 되는 것을 알고 두는 대신, 여기서 묶는다. 단위표(`test_frontend_units.py`)
와 같은 자리다 — 생성할 수 없는 값이면 검사로 묶는다.

## 어긋나면 무슨 일이 나나 (실측 2026-09-11)

화면 쪽 순서를 고쳤을 때(재샘플을 재는 단계 뒤로) **MCP 쪽에는 한 글자도 안
건너갔다.** AI 는 옛 순서대로 단계를 짜고, 탄성계수가 안 나오고, 그 이유를
모른다 — 사람은 화면에서 이미 고쳐진 것을 보고 있으므로 그 차이를 눈치채지
못한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
STANDARD_TS = ROOT / "frontend" / "src" / "modules" / "processing" / "standard.ts"
SERVER = ROOT / "mcp_server" / "server.py"
GUIDE = ROOT / "mcp_server" / "guide" / "GUIDE.md"

pytestmark = pytest.mark.skipif(not SERVER.exists(), reason="mcp_server 가 없는 배포본")


def frontend_order() -> list[str]:
    """`standard.ts` 의 `TENSILE_STANDARD` 가 든 단계를 **적힌 차례대로.**"""
    text = STANDARD_TS.read_text(encoding="utf-8")
    block = re.search(
        r"export const TENSILE_STANDARD: RecipeStep\[\] = \[(.*?)\n\]", text, re.DOTALL
    )
    assert block, "standard.ts 에서 TENSILE_STANDARD 를 못 찾았다"
    return re.findall(r"plugin:\s*'([^']+)'", block.group(1))


def mcp_order() -> list[str]:
    """`server.py` 의 `TENSILE_STANDARD` 가 든 차례."""
    text = SERVER.read_text(encoding="utf-8")
    block = re.search(r"TENSILE_STANDARD: tuple\[str, \.\.\.\] = \((.*?)\n\)", text, re.DOTALL)
    assert block, "server.py 에서 TENSILE_STANDARD 를 못 찾았다"
    return re.findall(r'"([^"]+)"', block.group(1))


def guide_order() -> list[str]:
    """안내서의 표 — 번호가 붙은 줄에서 단계 이름만."""
    text = GUIDE.read_text(encoding="utf-8")
    return re.findall(r"^\s+\d+\s+([a-z_]+\.[a-z_]+)\s", text, re.MULTILINE)


def test_MCP_가_같은_순서를_안다() -> None:
    assert mcp_order() == frontend_order(), (
        "화면과 MCP 의 표준 순서가 다릅니다 — AI 가 옛 순서로 단계를 짭니다.\n"
        f"  화면: {frontend_order()}\n  MCP : {mcp_order()}"
    )


def test_안내서도_같은_순서를_적는다() -> None:
    """사람이 읽는 것과 도구가 주는 것이 다르면 어느 쪽을 믿을지 알 수 없다."""
    assert guide_order() == frontend_order(), (
        "안내서의 표준 순서가 화면과 다릅니다.\n"
        f"  화면  : {frontend_order()}\n  안내서: {guide_order()}"
    )


def test_재는_단계가_재샘플보다_앞이다() -> None:
    """**이 순서의 핵심이다.** 뒤집히면 탄성계수가 격자점으로 계산돼 안 나온다."""
    order = mcp_order()
    resample = order.index("curve.resample")
    for measuring in ("tensile.strength", "tensile.elastic_modulus", "tensile.proof_stress"):
        assert order.index(measuring) < resample, f"{measuring} 이 재샘플 뒤에 있다"
