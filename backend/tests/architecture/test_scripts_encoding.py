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


_SKIP_ANYWHERE = {"node_modules", ".venv"}

#: 저장소 루트의 `deploy/` 는 빌드 산출물(원본 복사본)이라 검사하지 않는다.
#: 이름만으로 거르면 `scripts/deploy/` 까지 함께 빠져 정작 검사해야 할 배포
#: 스크립트 5개가 조용히 제외된다(실측). 그래서 최상위 경로로 판정한다.
_SKIP_TOP_LEVEL = {"deploy"}


def _scripts() -> list[Path]:
    found = []
    for path in REPO.rglob("*.ps1"):
        parts = path.relative_to(REPO).parts
        if _SKIP_ANYWHERE & set(parts):
            continue
        if parts[0] in _SKIP_TOP_LEVEL:
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
