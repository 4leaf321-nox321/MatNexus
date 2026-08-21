"""PowerShell 스크립트는 UTF-8 BOM 이어야 한다.

**운영 서버에서 그대로 터지는 문제였다.** Windows PowerShell 5.1(운영 서버의
기본 셸)은 BOM 이 없는 `.ps1` 을 ANSI(한국어 환경은 CP949)로 읽는다. 우리
스크립트는 주석과 메시지가 한글이라, BOM 이 없으면 문자열이 깨지면서 따옴표가
어긋나 **파싱 자체가 실패한다**(실측: package_deploy.ps1 이 구문 오류로 멈췄다).

편집기나 도구가 BOM 을 떼어내는 일이 흔해서 사람이 지키기 어렵다. 그래서 검사한다.

고치는 법:
    $bom = New-Object System.Text.UTF8Encoding $true
    $text = [System.IO.File]::ReadAllText($path, (New-Object System.Text.UTF8Encoding $false))
    [System.IO.File]::WriteAllText($path, $text, $bom)
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BOM = b"\xef\xbb\xbf"


_SKIP_ANYWHERE = {"node_modules"}

#: 저장소 루트의 `deploy/` 는 빌드 산출물(원본 복사본)이라 검사하지 않는다.
#: 이름만으로 거르면 `scripts/deploy/` 까지 함께 빠져 정작 검사해야 할 배포
#: 스크립트 5개가 조용히 제외된다(실측). 그래서 최상위 경로로 판정한다.
_SKIP_TOP_LEVEL = {"deploy"}


def _in_venv(path: Path) -> bool:
    """venv 안인가. **이름이 아니라 `pyvenv.cfg` 로 판정한다.**

    전에는 `.venv` 라는 이름 하나만 뺐다. 그런데 파이썬을 3.12 → 3.13 으로 옮기면서
    옆에 `.venv313` 을 만들었더니 거기 `Activate.ps1`(파이썬이 만든 것, BOM 없음)이
    검사 대상으로 잡혀 실패했다. 우리가 안 쓴 파일을 우리 규칙으로 검사한 것이다.

    이름을 하나 더 적는 것으로 고치면 `venv`·`env`·`.venv312` 에서 또 난다.
    디렉터리를 venv 로 만드는 것은 이름이 아니라 `pyvenv.cfg` 다.
    """
    for parent in path.parents:
        if (parent / "pyvenv.cfg").exists():
            return True
        if parent == REPO:
            break
    return False


def _scripts() -> list[Path]:
    found = []
    for path in REPO.rglob("*.ps1"):
        parts = path.relative_to(REPO).parts
        if _SKIP_ANYWHERE & set(parts):
            continue
        if parts[0] in _SKIP_TOP_LEVEL:
            continue
        if _in_venv(path):
            continue
        found.append(path)
    return found


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_powershell_scripts_have_utf8_bom(path: Path) -> None:
    head = path.read_bytes()[:3]
    assert head == BOM, (
        f"{path.relative_to(REPO)} 에 UTF-8 BOM 이 없습니다. "
        f"Windows PowerShell 5.1 이 CP949 로 읽어 한글이 깨지고 구문 오류가 납니다."
    )


#: 줄바꿈을 검사할 텍스트 확장자. 바이너리(png·parquet·tra)는 뺀다.
_TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".json",
    ".yml",
    ".yaml",
    ".css",
    ".html",
    ".txt",
}


def _text_files() -> list[Path]:
    found = []
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        parts = path.relative_to(REPO).parts
        if _SKIP_ANYWHERE & set(parts):
            continue
        if parts[0] in _SKIP_TOP_LEVEL or parts[0] in {".git", "dist", "filestore", "logs"}:
            continue
        if _in_venv(path):
            continue
        found.append(path)
    return found


CR = b"\x0d"
LF = b"\x0a"


def test_홀로_있는_CR_이_없다() -> None:
    """CR 하나가 텍스트 파일을 **바이너리로 바꾼다.**

    실측(2026-08-21): 문서에 윈도우 경로를 적다가 백슬래시가 이스케이프로 먹혀
    진짜 CR 한 바이트가 들어갔다. 눈에는 안 보인다. 그런데 git 이 그 파일을
    `-text`(바이너리)로 판정하면서 `.gitattributes` 의 `eol=lf` 정규화를 건너뛰었고,
    이후 **한 줄만 고쳐도 890줄 전체가 바뀐 diff** 가 나왔다. 그러면 `git blame` 도
    `git log -p` 도 그 파일에서 쓸모가 없어진다.

    CRLF 자체는 괜찮다 — `.ps1` 은 CRLF 여야 한다. 문제는 LF 가 안 따라오는 CR 이다.

    바이트를 16진수로 적는 이유도 같다. 소스에 이스케이프로 적으면 이 파일을
    고치는 다음 도구가 또 진짜 CR 로 바꿔 놓는다. 실제로 두 번 그랬다.
    """
    offenders = []
    for path in _text_files():
        data = path.read_bytes()
        lone = data.replace(CR + LF, b"").count(CR)
        if lone:
            offenders.append(f"{path.relative_to(REPO)} ({lone}개)")
    assert not offenders, (
        "홀로 있는 CR 이 든 파일: "
        + ", ".join(offenders)
        + ". git 이 바이너리로 보아 줄바꿈 정규화가 꺼지고, 이후 diff 가 파일 전체가 됩니다."
    )
