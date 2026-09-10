"""자료를 **파일로** 내려주는 한 곳.

## 왜 공용인가

재료와 문헌이 각자 응답을 만들면 한쪽만 고쳐진다 — 파일 이름 규칙이 달라지거나,
한쪽만 봉투를 씌우거나, 한쪽만 UTF-8 을 안 밝힌다. 받는 쪽에서는 그 차이가
「왜 이 파일만 엑셀에서 깨지나」 로 나타나고, 그때 원인을 찾기가 어렵다.

## 맨 배열로 주지 않는다

`[{...}, {...}]` 만 주면 받은 사람은 **이게 무엇의 어느 시점 자료인지, 무슨
조건으로 거른 것인지** 알 방법이 없다. 반년 뒤 그 파일이 폴더에서 나왔을 때
설명할 수 있어야 한다 — 그래서 봉투(`kind`·`exported_at`·`filters`)를 씌운다.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Response


def json_file(payload: dict[str, Any], filename: str, *, pretty: bool = True) -> Response:
    """JSON 하나를 내려받게 한다.

    **`ensure_ascii=False` 다.** 한글을 `\\uXXXX` 로 굽으면 파일이 두 배로 커지고
    사람이 열어 봤을 때 못 읽는다 — 이 파일은 기계도 읽지만 사람도 연다.

    **charset 을 밝힌다.** 안 밝히면 브라우저·엑셀이 CP949 로 읽어 한글이 깨진다.

    `pretty` 는 **열어 볼 크기인가**로 정한다. 재료(수백 KB)는 사람이 편집기로
    열어 보므로 들여쓴다. 문헌 전체는 아무도 안 여는데 들여쓰기만으로 24MB 가
    는다(실측 2026-09-10: 88MB → 112MB) — 그때는 압축하고, 보고 싶으면 한 줄로
    편다(`python -m json.tool`).
    """
    body = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        default=str,
    )
    return Response(
        content=body.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
