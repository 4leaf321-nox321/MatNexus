"""배포 패키지 — **문서가 쓰라는 스크립트가 실제로 들어 있는가.**

`deploy_package.zip` 은 폐쇄망 서버가 받는 **유일한 반입물**이다. 배포 스크립트가
거기 없으면 서버에서는 손에 넣을 방법이 없다.

실제로 빠진 적이 있다. `backup.ps1` 이 패키징 목록에 없어서, 배포 문서는 백업을
먼저 받으라고 적었는데 **복사할 파일이 서버에 없었다.** 백업은 업데이트 배포의
전제라 그 순서가 통째로 막힌다.

빠졌다는 것은 zip 을 풀어 보기 전에는 안 보인다 — 빌드는 성공하고, 릴리스도
발행되고, 서버에서 파일을 찾을 때 처음 드러난다.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGER = ROOT / "scripts" / "ci" / "package_deploy.ps1"
DEPLOY_SCRIPTS = ROOT / "scripts" / "deploy"


def test_배포_스크립트가_전부_패키지에_들어간다() -> None:
    """`scripts/deploy/` 의 `.ps1` 은 하나도 빠짐없이 zip 에 담겨야 한다.

    새 스크립트를 만들고 패키징에 추가하는 것을 잊는 것이 실제 실패 경로다.
    """
    # **주석이 아니라 실제 복사 줄을 본다.** 처음에는 파일 전체에서 이름을
    # 찾았는데, 머리말 주석이 스크립트를 나열하고 있어서 `Copy-Item` 을 지워도
    # 통과했다 — 시험이 있으나 마나였다.
    copied = chr(10).join(
        line
        for line in PACKAGER.read_text(encoding="utf-8-sig").splitlines()
        if line.strip().startswith("Copy-Item")
    )
    missing = [
        script.name
        for script in sorted(DEPLOY_SCRIPTS.glob("*.ps1"))
        if script.name not in copied
    ]
    assert not missing, (
        f"{', '.join(missing)} 이(가) package_deploy.ps1 에 없습니다. "
        f"zip 에 안 들어가면 폐쇄망 서버는 그 스크립트를 손에 넣을 방법이 없습니다 — "
        f"실제로 backup.ps1 이 빠져 백업 절차가 막힌 적이 있습니다."
    )


def test_배포_문서가_패키지에_들어간다() -> None:
    """폐쇄망 서버는 zip 하나만 받는다.

    문서가 저장소에만 있으면 **정작 설치하는 자리에서 볼 수 없다.** 절차를
    외우고 가거나 따로 챙겨야 하는데, 따로 챙기는 것은 잊는다.
    """
    packager = PACKAGER.read_text(encoding="utf-8-sig")
    guide = ROOT / "배포.md"
    assert guide.exists(), "배포.md 가 저장소에 없습니다."
    assert guide.name in packager, (
        "배포.md 가 package_deploy.ps1 에 없습니다. zip 에 안 들어가면 서버에서 "
        "절차를 볼 방법이 없습니다."
    )


def test_확장_폴더가_패키지에_남는다() -> None:
    """물성 확장은 **폴더로 배포된다**(ADR 0013).

    `pip install` 이 아니라 폴더로 둔 이유가 폐쇄망이다 — 반입물이 zip 하나이고
    `Copy-Item -Recurse .\backend` 가 통째로 담으므로 저절로 따라간다.

    그런데 그 아래 **걷어내는 목록**이 있다(`.venv`·`__pycache__`·`logs`…).
    거기에 `extensions` 가 들어가면 확장이 조용히 사라지고, **서버에서 그 물성만
    목록에 안 뜬다.** 빌드는 성공하고 릴리스도 발행되므로 알아챌 길이 없다.
    """
    packager = PACKAGER.read_text(encoding="utf-8-sig")
    stripped = [
        line
        for line in packager.splitlines()
        if "foreach ($junk" in line and "extensions" in line
    ]
    assert not stripped, (
        "package_deploy.ps1 이 extensions 를 걷어냅니다. 그러면 확장 물성이 "
        "서버에서 조용히 사라집니다 — 빌드는 성공하고 릴리스도 발행됩니다."
    )
    assert (ROOT / "backend" / "extensions").is_dir(), (
        "backend/extensions 폴더가 없습니다. 비어 있어도 README 로 남겨 둡니다 — "
        "폴더가 없으면 어디에 확장을 넣어야 하는지 알 길이 없습니다."
    )
