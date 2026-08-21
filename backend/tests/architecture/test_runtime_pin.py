"""런타임 버전 선언이 갈리지 않는가.

**실제로 갈려 있었다.** 2026-08-21 에 재 보니 이랬다.

    pyproject requires-python   >=3.13,<3.14
    mypy python_version         3.13
    CI · 릴리스 · precheck      3.13
    개발 PC 의 backend/.venv    3.12.6      ← 여기만 달랐다

배포 경로는 전부 3.13 인데 로컬만 3.12 였다. 그래서 같은 코드를 서로 다른 런타임
두 개가 검사하고 있었다 — 테스트와 mypy 는 3.12 위에서, CI 는 3.13 위에서. 통과했으니
안 보였을 뿐이다. 릴리스가 만드는 wheel 은 **ABI 태그가 마이너 버전에 묶여**
있어서(`cp313`), 이게 어긋나면 서버에서 설치가 안 된다.

65 도 같은 문제를 겪고 `#284` 로 환경 고정 장치를 넣었다(`.python-version` +
`.node-version` + 검사 스크립트 235줄). 여기서는 **선언끼리 맞는지**를 검사한다.

돌고 있는 인터프리터까지 강제하지는 않는다 — 그러면 파이썬을 다시 깔기 전까지
아무 테스트도 못 돌린다. 사람이 venv 를 다시 만드는 것은 사람의 일이고, 선언이
갈리는 것을 막는 것은 기계의 일이다.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
BACKEND = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _pinned(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8").strip()


def test_파이썬_선언이_전부_같은_마이너를_가리킨다() -> None:
    pinned = _pinned(".python-version")

    config = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    requires = config["project"]["requires-python"]
    assert requires == f">={pinned},<{pinned.split('.')[0]}.{int(pinned.split('.')[1]) + 1}", (
        f"pyproject 의 requires-python({requires})이 .python-version({pinned})과 다릅니다."
    )

    mypy_version = config["tool"]["mypy"]["python_version"]
    assert mypy_version == pinned, (
        f"mypy 가 {mypy_version} 를 가정하는데 런타임은 {pinned} 입니다. "
        f"타입 검사와 실행이 다른 파이썬을 보면 통과가 보증이 아닙니다."
    )

    # 설치 전 점검이 서버 파이썬을 보는 자리. wheel ABI 가 여기 묶인다.
    precheck = (ROOT / "scripts" / "deploy" / "precheck.ps1").read_text(encoding="utf-8")
    found = re.search(r"\$PythonVersion\s*=\s*'([\d.]+)'", precheck)
    assert found is not None, "precheck.ps1 에서 PythonVersion 기본값을 못 찾았습니다."
    assert found.group(1) == pinned, (
        f"precheck.ps1 이 서버에 {found.group(1)} 를 요구하는데 빌드는 {pinned} 입니다. "
        f"wheel 의 ABI 태그가 마이너 버전에 묶이므로 설치가 실패합니다."
    )


def test_CI_와_릴리스가_고정_파일을_읽는다() -> None:
    """**버전을 워크플로에 직접 적지 않는다.** 두 곳에 적히면 한 곳만 고쳐진다."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for tool in ("python", "node"):
            literal = re.search(rf"^\s*{tool}-version:\s*'", text, re.M)
            assert literal is None, (
                f"{path.name} 이 {tool} 버전을 직접 적고 있습니다. "
                f"`{tool}-version-file` 로 .{tool}-version 을 읽으세요."
            )


def test_node_고정_파일이_있다() -> None:
    assert _pinned(".node-version"), ".node-version 이 비어 있습니다."
