"""경계 검사가 **무엇을 막고 무엇을 통과시키는가.**

이 검사가 이 분업의 마지막 층이다(`test_agent_docs.py` 머리말의 3층 중 1층).
그래서 **너무 세게 막는 것도 문제다** — 플랫폼 개발자의 평범한 변경까지 막으면
사람들은 검사를 끄는 방법부터 찾는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

# 저장소 루트의 `scripts/` 는 백엔드 패키지 밖이라 mypy 가 못 찾는다 — 경로를
# 넣어 주는 것이 이 시험의 일부다(CI 도 같은 자리에서 부른다).
from check_boundary import crossings  # type: ignore[import-not-found]  # noqa: E402


def test_확장만_고치면_통과한다() -> None:
    assert crossings(["backend/extensions/ghosh_hardening/equation.py"]) == []


def test_중심만_고치면_통과한다() -> None:
    """**플랫폼 개발자의 일은 막지 않는다.** 여기서 막으면 검사를 끄게 된다."""
    assert crossings(["backend/app/main.py", "frontend/src/App.tsx"]) == []


def test_확장과_중심을_함께_고치면_막는다() -> None:
    """두 사람의 일이 한 PR 에 섞이면 리뷰도 되돌리기도 어려워진다."""
    found = crossings(
        [
            "backend/extensions/x/__init__.py",
            "backend/matcore/fitting/__init__.py",
        ]
    )
    assert [path for path, _ in found] == ["backend/matcore/fitting/__init__.py"]


def test_왜_막는지_함께_말한다() -> None:
    """**이유 없는 금지는 우회된다.** 무엇을 하면 되는지도 함께 나와야 한다."""
    found = crossings(["backend/extensions/x/__init__.py", "backend/migrations/versions/a.py"])
    assert found, "마이그레이션을 안 막았습니다"
    _, why = found[0]
    assert "요청" in why, why


def test_확장의_시험은_막지_않는다() -> None:
    """확장 개발자가 자기 시험을 못 쓰면 확장을 못 만든다 — `tests/` 는 중심
    목록에 없다."""
    assert (
        crossings(
            [
                "backend/extensions/x/__init__.py",
                "backend/tests/unit/test_ext_x.py",
            ]
        )
        == []
    )
