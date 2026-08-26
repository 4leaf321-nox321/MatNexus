"""프로파일이 가리킬 수 있는 **칸 목록**이 프론트와 서버에서 갈리면 실패한다.

편집 화면의 ⑤ 에서 「시험 칸에 채움」·「어느 재료·시료·시편인지」 를 고를 때,
드롭다운의 항목은 프론트가 들고 있고 **거절 판정은 서버가 한다.**

  - 서버에 있는 칸이 프론트에 없으면 **화면에서 고를 수 없다.** 오류가 아니라
    '목록에 없음' 이라 원인을 찾기 어렵다 — `angular_frequency` 때 실제로
    겪은 종류의 고장이다(`test_frontend_units.py`).
  - 프론트에만 있는 칸을 고르면 저장이 422 로 거절된다. 이쪽은 시끄러워서
    낫지만, 사람이 화면에서 막히는 것은 마찬가지다.

이 표는 **값**이라 OpenAPI 생성 대상이 아니다. 그래서 검사로 묶는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.tests.schemas import IDENTITY_FIELDS, RECORD_FIELDS

EDITOR = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "modules"
    / "tests"
    / "FormatProfileEditorPage.tsx"
)

_ENTRY = re.compile(r"^\s*([A-Za-z_]+):\s*'([^']*)'", re.MULTILINE)


def _table(name: str) -> dict[str, str]:
    text = EDITOR.read_text(encoding="utf-8")
    block = re.search(
        rf"const {name}: Record<string, string> = \{{(.*?)\n\}}", text, re.DOTALL
    )
    assert block, f"{EDITOR.name} 에서 {name} 을 찾지 못했습니다."
    return dict(_ENTRY.findall(block.group(1)))


def test_시험_칸_목록이_서버와_같다() -> None:
    assert _table("RECORD_FIELD_LABEL") == RECORD_FIELDS


def test_식별자_목록이_서버와_같다() -> None:
    assert _table("IDENTITY_FIELD_LABEL") == IDENTITY_FIELDS


def test_메모는_파일이_못_채운다() -> None:
    """메모는 사람이 쓰는 자리다. 파일이 거기에 무언가 적으면 사람이 쓴 것과
    구별이 안 되고, 그러면 그 칸의 뜻이 없어진다."""
    assert "note" not in RECORD_FIELDS
