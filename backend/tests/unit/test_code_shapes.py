"""번호 꼴 맞추기(ADR 0043) — **사람은 번호를 여러 꼴로 친다.**

`T-000203` · `T-203` · `t203` 은 같은 번호다. 맞추지 않으면 패딩 없이 친 사람은 0건을 보고,
번호가 없다고 읽는다.
"""

from __future__ import annotations

import pytest

from app.shared import codes


@pytest.mark.parametrize(
    ("typed", "kind", "value"),
    [
        ("T-000203", "test_run", "T-000203"),
        ("T-203", "test_run", "T-000203"),
        ("t203", "test_run", "T-000203"),
        (" P-12 ", "specimen", "P-000012"),  # 복사해 붙이면 공백이 붙어 온다
        ("s1", "sample", "S-000001"),
        ("M-82", "material", "M-000082"),
    ],
)
def test_여러_꼴이_한_꼴로_맞춰진다(typed: str, kind: str, value: str) -> None:
    code = codes.parse(typed)
    assert code is not None
    assert (code.kind, code.value) == (kind, value)


@pytest.mark.parametrize("typed", ["X-1", "T-1234567", "SECC", "T-", "TT-1", "T 203", ""])
def test_번호가_아닌_것은_번호로_안_읽는다(typed: str) -> None:
    # 일곱 자리는 없는 번호다 — 잘라서 맞추면 엉뚱한 번호에 닿는다.
    assert codes.parse(typed) is None


def test_종류가_다르면_그_종류의_번호가_아니다() -> None:
    assert codes.of_kind("P-12", "specimen") == "P-000012"
    assert codes.of_kind("P-12", "test_run") is None
