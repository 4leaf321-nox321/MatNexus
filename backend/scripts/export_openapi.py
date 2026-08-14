"""OpenAPI 문서를 파일로 내보낸다.

두 가지 목적이 있다.

1. **프론트 타입 생성의 입력**(D13). 서버를 띄우지 않고도 타입을 다시 만들 수
   있어야 CI에서 쓸 수 있다.
2. **계약 baseline**. 파일이 저장소에 있으므로 스키마가 바뀌면 diff에 드러난다.
   65의 contracts 호환성 검사가 하던 역할을 가장 싼 형태로 가져온 것이다.

키를 정렬해 출력하므로 같은 코드에서는 항상 같은 파일이 나온다 — 정렬하지
않으면 무관한 순서 변경이 diff로 잡혀 baseline이 무의미해진다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))  # `python scripts/export_openapi.py` 로도 돌게

from app.main import create_app  # noqa: E402

OUTPUT = BACKEND_DIR / "openapi.json"


def main() -> None:
    schema = create_app().openapi()
    OUTPUT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"내보냄: {OUTPUT} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
