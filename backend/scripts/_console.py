"""출력이 콘솔이 아닐 때 스크립트가 마지막 줄에서 죽지 않게 한다.

**실측(2026-09-06)**: `import_materialtwin.py` 가 카탈로그 42,209건을 다 읽고
검산까지 끝낸 뒤 **성공 줄에서** 터졌다.

    UnicodeEncodeError: 'cp949' codec can't encode character '\\u2014'

한글은 CP949 로 멀쩡히 나간다. 못 나가는 것은 `—`(em dash) 하나인데, 우리
`scripts/` 스무 개가 하나도 빠짐없이 그것을 쓴다 — 출력에도, 설명문에도.
argparse 가 모듈 docstring 을 그대로 `--help` 로 찍으므로 `--help` 조차 같은
자리에서 죽는다.

**터지는 조건은 출력이 콘솔이 아닐 때다.** 콘솔에 직접 찍을 때 파이썬은 콘솔
API 로 쓰기 때문에 멀쩡하다. 파이프나 파일로 가면 그때만 locale(CP949)로
떨어진다 — 그래서 사람이 손으로 돌릴 때는 안 보이고, `deploy.ps1` 이 출력을
받아 갈 때만 난다. 다 끝난 작업이 traceback 으로 끝나면 사람은 그것을 실패로
읽고 되돌리려 든다.

**인코딩을 UTF-8 로 바꾸지 않는다.** 바꾸면 CP949 로 읽는 PowerShell 이 배포
로그 전체를 깨진 글자로 받는다. 못 쓰는 글자 하나가 `?` 로 나가는 편이 낫다 —
문장은 그대로 읽힌다.
"""

from __future__ import annotations

import contextlib
import sys


def survive_cp949() -> None:
    """못 쓰는 글자를 만나도 출력이 죽지 않게 한다.

    인코딩은 그대로 두고 `errors` 만 푼다. 스크립트는 무엇이든 찍기 **전에**
    이것을 부른다 — `--help` 도 출력이다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # 파이썬이 만든 텍스트 스트림이 아니다(테스트가 갈아 끼운 StringIO 등).
            # 그런 자리는 애초에 인코딩을 거치지 않으므로 죽지 않는다.
            continue
        with contextlib.suppress(ValueError, OSError):  # 이미 닫혔거나 detach 된 스트림
            reconfigure(errors="replace")
