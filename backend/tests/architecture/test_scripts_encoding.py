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


#: 빌드 산출물(deploy/)은 원본을 복사한 것이라 따로 검사하지 않는다.
_SKIP_DIRS = {"node_modules", ".venv", "deploy"}


def _scripts() -> list[Path]:
    return [p for p in REPO.rglob("*.ps1") if not _SKIP_DIRS & set(p.parts)]


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_powershell_scripts_have_utf8_bom(path: Path) -> None:
    head = path.read_bytes()[:3]
    assert head == BOM, (
        f"{path.relative_to(REPO)} 에 UTF-8 BOM 이 없습니다. "
        f"Windows PowerShell 5.1 이 CP949 로 읽어 한글이 깨지고 구문 오류가 납니다."
    )
