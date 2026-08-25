"""지침이 **한 벌**이고, 소유 경계가 실제로 적혀 있는가.

## 왜 기계가 검사하는가

셋이 함께 고치는 저장소에서 규칙을 지키게 하는 힘은 세 층이다.

    기계   CI + 브랜치 보호        막힌다
    사람   CODEOWNERS + 리뷰       대체로 막힌다
    선의   AGENTS.md / CLAUDE.md   안 막힌다 — 사고를 줄일 뿐

**3층만 두면 장식이다.** 에이전트는 지침을 읽고도 안 지킬 수 있고, 사람도 그렇다.
그래서 지침 자체가 성립하는지(한 벌인가·경계가 적혀 있는가)를 여기서 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: 지침 짝. 정본과, 그것을 가리키기만 해야 하는 쪽.
PAIRS = [
    (ROOT / "AGENTS.md", ROOT / "CLAUDE.md"),
    (
        ROOT / "backend" / "extensions" / "AGENTS.md",
        ROOT / "backend" / "extensions" / "CLAUDE.md",
    ),
]


@pytest.mark.parametrize(("canonical", "pointer"), PAIRS, ids=lambda p: p.name)
def test_지침은_한_벌이다(canonical: Path, pointer: Path) -> None:
    """`CLAUDE.md` 는 `AGENTS.md` 를 가리키기만 한다.

    **두 벌로 두면 한쪽만 고쳐진다.** Codex 를 쓰는 사람은 `CLAUDE.md` 를 안
    읽고, Claude 를 쓰는 사람은 `AGENTS.md` 를 안 읽을 수 있다 — 그때 둘은
    같은 저장소에서 다른 규칙을 따르게 되고, 그 사실은 충돌이 나야 드러난다.
    """
    assert canonical.exists(), f"{canonical.name} 이 없습니다 — 규칙의 정본입니다."
    assert pointer.exists(), f"{pointer.name} 이 없습니다."

    body = pointer.read_text(encoding="utf-8")
    assert "AGENTS.md" in body, (
        f"{pointer} 가 AGENTS.md 를 안 가리킵니다. 규칙을 여기 적지 말고 "
        f"`@AGENTS.md` 로 가져오세요."
    )
    # **짧아야 한다.** 길어졌다는 것은 규칙을 베끼기 시작했다는 뜻이다.
    assert len(body.splitlines()) < 20, (
        f"{pointer} 가 길어졌습니다({len(body.splitlines())}줄). 규칙은 "
        f"{canonical.name} 에만 적습니다 — 두 벌이 되면 한쪽만 고쳐집니다."
    )


def test_소유_경계가_적혀_있다() -> None:
    """`CODEOWNERS` 가 확장 폴더와 규칙 파일을 덮는가.

    **경계를 파일로 적어 두는 것이 목적이다.** GitHub 이 리뷰를 요청해 주는 것은
    덤이고, 그보다 「누가 어디를 만지는가」 에 답이 하나뿐이라는 것이 중요하다.
    """
    owners = ROOT / ".github" / "CODEOWNERS"
    assert owners.exists(), "CODEOWNERS 가 없습니다 — 소유가 어디에도 안 적혀 있습니다."
    body = owners.read_text(encoding="utf-8")

    for path in ("/backend/extensions/", "/AGENTS.md", "/.github/CODEOWNERS"):
        assert path in body, (
            f"CODEOWNERS 에 {path} 가 없습니다. 규칙과 소유를 바꾸는 파일은 "
            f"**둘 다 봐야 한다** — 한 사람이 조용히 경계를 옮길 수 있으면 "
            f"경계를 둔 뜻이 없습니다."
        )


def test_확장_폴더에도_지침이_있다() -> None:
    """하위 폴더의 지침을 두 도구가 다 읽는다.

    Claude Code 와 Codex 둘 다 **작업하는 폴더까지 내려오며** 지침을 합친다.
    확장 폴더에 좁은 규칙을 두면, 그 폴더에서 일하는 사람의 도구가 그것을 읽는다.
    """
    narrow = (ROOT / "backend" / "extensions" / "AGENTS.md").read_text(encoding="utf-8")
    assert "이 폴더 밖은 고치지 않는다" in narrow
    # **막는 이유까지 적혀 있어야 한다.** 이유 없는 금지는 우회된다.
    assert "다른 사람이 같은 시간에" in narrow


def test_범위_예외가_소유_경로로_한정된다() -> None:
    """「스코프 안에서 바로잡는다」 가 남의 파일까지 열어 주면 안 된다.

    65의 부채를 막으려고 둔 예외인데(§8.3), 셋이 함께 고치는 저장소에서는
    **남의 파일을 「규칙에 맞게」 고치는 것이 정당해진다** — 그것은 충돌이다.
    """
    rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "자기 소유 경로 안에서만" in rules, (
        "범위 예외에 소유 경로 단서가 없습니다. 그대로 두면 남의 코드를 "
        "고치는 것이 규율상 정당해집니다."
    )
