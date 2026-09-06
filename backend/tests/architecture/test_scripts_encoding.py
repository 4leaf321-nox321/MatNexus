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

#: 저장소가 관리하지 않는 최상위 폴더. `materialtwin-*` 는 이관 원본 스냅샷이라
#: `.gitignore` 에 있다 — **우리가 쓴 파일이 아니다.** 남의 파일을 우리 규칙으로
#: 검사하면 CI 가 우리 잘못이 아닌 것으로 실패한다(venv 에서 같은 일이 있었다).
_SKIP_TOP_PREFIX = ("materialtwin-",)


def _outside(path: Path) -> bool:
    """검사 대상 밖인가."""
    parts = path.relative_to(REPO).parts
    if _SKIP_ANYWHERE & set(parts):
        return True
    if parts[0] in _SKIP_TOP_LEVEL or parts[0].startswith(_SKIP_TOP_PREFIX):
        return True
    return _in_venv(path)


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
    return [path for path in REPO.rglob("*.ps1") if not _outside(path)]


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
        if path.relative_to(REPO).parts[0] in {".git", "dist", "filestore", "logs"}:
            continue
        if _outside(path):
            continue
        found.append(path)
    return found


#: `scripts/` 의 공통 부품 자신. 스스로를 부를 이유가 없다.
_CONSOLE = "_console.py"


def _python_scripts() -> list[Path]:
    found = REPO / "backend" / "scripts"
    return sorted(path for path in found.glob("*.py") if path.name != _CONSOLE)


@pytest.mark.parametrize("path", _python_scripts(), ids=lambda p: p.name)
def test_스크립트는_출력_인코딩을_먼저_푼다(path: Path) -> None:
    """`survive_cp949()` 를 부르는가.

    **네 번 따로 밟고 네 번 따로 고친 함정이다**(2026-08-31 셋, 2026-09-02 하나).
    운영은 Windows 이고, 출력이 콘솔이 아니라 파이프로 가면 파이썬이 CP949 로
    인코딩한다. 한글은 멀쩡히 나가는데 `—`(em dash)·`≈` 가 안 나가고, 우리
    스크립트는 그 글자를 **전부** 쓴다.

    실측(2026-09-06): `import_materialtwin.py` 가 카탈로그 42,209건을 다 읽고
    검산까지 끝낸 뒤 마지막 성공 줄에서 `UnicodeEncodeError` 로 죽었다. 화면에는
    수가 다 찍히고 그 아래 traceback 이 붙으며 exit 1 이 된다 — **성공을 실패로
    읽게 만드는 모양**이고, 그때 사람은 되돌리려 든다.

    argparse 가 모듈 docstring 을 그대로 `--help` 로 찍으므로, 아무것도 출력하지
    않는 것처럼 보이는 스크립트도 예외가 아니다.
    """
    source = path.read_text(encoding="utf-8")
    assert "survive_cp949()" in source, (
        f"{path.name} 이 `survive_cp949()` 를 부르지 않습니다. "
        f"`from _console import survive_cp949` 한 뒤 import 블록 다음에서 부르세요 — "
        f"출력이 파이프로 갈 때 `—` 한 글자에 UnicodeEncodeError 로 죽습니다."
    )


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


#: 텍스트에 있어서는 안 되는 제어문자. 탭(09)·LF(0a)·CR(0d)만 뺀다.
_CONTROL = bytes(range(0x00, 0x09)) + b"\x0b\x0c" + bytes(range(0x0E, 0x20))


def test_보이지_않는_제어문자가_없다() -> None:
    """CR 말고도 **이스케이프가 먹혀 진짜 바이트가 되는** 자리가 있다.

    실측(2026-09-06): `deploy.ps1` 의 안내 문구에 `$AppPath\\backend` 를 적으려다
    `\\b` 가 **백스페이스 한 바이트(0x08)** 로 들어갔다. 파일에서는 안 보이고,
    문법 검사도 통과하고, 화면에는 `C:\\Server\\MatNexuackend` 로 나온다 — 사람은
    그 경로로 옮겨 가려다 실패하고 무엇이 틀렸는지 모른다.

    같은 사고가 CR 로 두 번, 백스페이스로 한 번 났다. 셋 다 눈에 안 보이는
    바이트가 소스에 앉은 것이라 한 가지로 검사한다.

    바이트를 16진수로 적는 이유는 위와 같다 — 소스에 이스케이프로 적으면 이
    파일을 고치는 다음 도구가 또 진짜 제어문자로 바꿔 놓는다.
    """
    offenders = []
    for path in _text_files():
        found = {f"0x{byte:02x}" for byte in path.read_bytes() if byte in _CONTROL}
        if found:
            offenders.append(f"{path.relative_to(REPO)} ({', '.join(sorted(found))})")
    assert not offenders, (
        "보이지 않는 제어문자가 든 파일: "
        + ", ".join(offenders)
        + ". 이스케이프(`\\b`·`\\f` 등)를 적으려다 진짜 바이트가 된 자리입니다 — "
        "파일에서는 안 보이고 화면에서만 글자가 사라집니다."
    )
