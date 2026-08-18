"""이 설치가 어느 버전인가.

**전에는 답할 데가 없었다.** `/api/health` 는 `{"status": "ok"}` 만 주고, OpenAPI
버전은 `0.1.0` 에 하드코딩돼 있었고, 배포 로그도 버전을 안 남겼다. 그래서 태그를
지정하지 않고 배포하면 **나중에 무엇이 깔렸는지 되짚을 수 없었다** — 문제가 났을
때 "지금 서버 버전이 뭐냐" 를 못 답하면 원인 찾기가 크게 어려워진다.

값은 배포 패키지가 들고 온다(`BUILD_INFO.txt` 의 `version=`). 릴리스 워크플로가
태그를 거기 박으므로, **깔린 파일 자신이 자기 버전을 안다** — 서버에 따로 적어
두는 방식이면 그 기록과 실제 코드가 어긋날 수 있다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

#: 어디서도 못 찾았을 때. 개발 중이거나 패키지가 아닌 경로에서 돈다는 뜻이다.
UNKNOWN = "unknown"

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _from_build_info() -> str | None:
    """배포 패키지가 넣어 준 값. `<설치폴더>/BUILD_INFO.txt` 다."""
    path = BACKEND_DIR.parent / "BUILD_INFO.txt"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("version="):
            return line.split("=", 1)[1].strip() or None
    return None


def _from_package_json() -> str | None:
    """개발 중에는 저장소의 `frontend/package.json` 이 정본이다(auto-tag 도 이것을 본다)."""
    path = BACKEND_DIR.parent / "frontend" / "package.json"
    if not path.exists():
        return None
    try:
        return "v" + str(json.loads(path.read_text(encoding="utf-8"))["version"])
    except (ValueError, KeyError):
        return None


@lru_cache(maxsize=1)
def current() -> str:
    """이 설치의 버전. 배포본이면 태그, 개발이면 package.json, 아니면 `unknown`."""
    return _from_build_info() or _from_package_json() or UNKNOWN
