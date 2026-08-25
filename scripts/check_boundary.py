"""PR 이 **경계를 넘었는가**. CI 가 부른다.

## 왜 필요한가

지침(`AGENTS.md`)과 소유(`CODEOWNERS`)는 사람과 에이전트의 선의에 기댄다.
에이전트는 규칙을 읽고도 「스코프 안에서 바로잡는다」 를 넓게 해석할 수 있고,
사람도 급하면 남의 파일을 고친다. **그때 막는 것은 CI 뿐이다.**

## 무엇을 보는가

**확장만 건드리는 변경**인지, **중심까지 건드리는 변경**인지를 가른다. 확장
폴더를 건드리면서 중심 코드도 함께 건드렸으면 막는다 — 그것은 두 사람의 일이
한 PR 에 섞인 것이고, 리뷰도 되돌리기도 어려워진다.

**막지 않는 경우도 분명히 한다.** 중심만 건드리는 변경은 플랫폼 개발자의 일이라
그대로 통과한다. 확장이 정말로 중심을 바꿔야 하면 PR 을 나눈다.

## 왜 CODEOWNERS 를 다시 읽지 않는가

여기서 필요한 것은 「누가 리뷰하나」 가 아니라 **「한 PR 이 두 영역에 걸쳤나」**
하나다. 소유자 이름은 GitHub 이 이미 본다.

    python scripts/check_boundary.py <base-ref>
"""

from __future__ import annotations

import subprocess
import sys

#: 확장 개발자의 것. 이 아래는 자유롭게 고친다.
EXTENSION = "backend/extensions/"

#: 확장 PR 이 함께 건드리면 안 되는 곳. **왜 안 되는지 함께 적는다** —
#: 이유 없는 금지는 우회된다.
CENTRAL = {
    "backend/matcore/": "중심 계산. 확장은 등록 함수로만 붙는다",
    "backend/app/": "서버. 확장은 DB 도 HTTP 도 모른다",
    "backend/migrations/": "확장은 마이그레이션을 쓰지 않는다 — 필요하면 요청한다",
    "frontend/": "화면. 확장이 전용 화면을 원하면 그때는 협의한다",
    "frontend/package.json": "버전을 올리는 것이 곧 배포 결정이다",
    "docs/개발계획.md": "같은 자리에 서로 덧붙이면 매번 충돌한다",
}


def changed(base: str) -> list[str]:
    """`base` 이후 바뀐 파일들."""
    got = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in got.stdout.splitlines() if line.strip()]


def crossings(files: list[str]) -> list[tuple[str, str]]:
    """확장과 함께 건드린 중심 파일들. (파일, 왜 안 되는지)"""
    if not any(one.startswith(EXTENSION) for one in files):
        return []  # 확장을 안 건드렸다 — 플랫폼 쪽 변경이다.
    found: list[tuple[str, str]] = []
    for one in files:
        if one.startswith(EXTENSION):
            continue
        for prefix, why in CENTRAL.items():
            if one.startswith(prefix):
                found.append((one, why))
                break
    return found


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    files = changed(base)
    crossed = crossings(files)
    if not crossed:
        print(f"경계 검사 통과 ({len(files)}개 파일)")
        return 0

    print("확장과 중심을 **한 PR 에서 함께** 고쳤습니다.\n")
    for path, why in crossed:
        print(f"  {path}\n      — {why}")
    print(
        "\n두 사람의 일이 한 PR 에 섞이면 리뷰도 되돌리기도 어려워집니다."
        "\n확장 변경과 중심 변경을 **PR 두 개로 나누세요.**"
        "\n중심이 정말 바뀌어야 하면 그 PR 은 플랫폼 개발자가 봅니다."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
